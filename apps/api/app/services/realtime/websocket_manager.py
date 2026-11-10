"""WaitWatch API — WebSocket connection manager and fanout."""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.services.realtime.events import FeedUpdateEvent

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active feed-scoped WebSocket connections and message fanout."""

    def __init__(self, max_connections_per_feed: int = 500) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._max_per_feed = max_connections_per_feed

    async def connect(self, feed_slug: str, websocket: WebSocket) -> bool:
        """Register an accepted WebSocket connection under a feed slug.

        Returns True if accepted and registered, False if capacity exceeded.
        """
        async with self._lock:
            feed_set = self._connections.setdefault(feed_slug, set())
            if len(feed_set) >= self._max_per_feed:
                logger.warning(
                    "Connection limit reached (%d) for feed '%s'",
                    self._max_per_feed,
                    feed_slug,
                )
                return False
            feed_set.add(websocket)
            logger.info(
                "WebSocket connected for feed '%s' (active for feed: %d)",
                feed_slug,
                len(feed_set),
            )
            return True

    async def disconnect(self, feed_slug: str, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        async with self._lock:
            if feed_slug in self._connections:
                self._connections[feed_slug].discard(websocket)
                if not self._connections[feed_slug]:
                    del self._connections[feed_slug]
                logger.info("WebSocket disconnected for feed '%s'", feed_slug)

    async def broadcast_to_feed(self, feed_slug: str, message: dict[str, Any]) -> int:
        """Broadcast a JSON message to all active WebSockets subscribed to a feed.

        Automatically cleans up closed or broken connections.
        Returns the number of successful deliveries.
        """
        async with self._lock:
            sockets = list(self._connections.get(feed_slug, set()))

        if not sockets:
            return 0

        dead_sockets: list[WebSocket] = []
        delivered = 0

        async def _send(ws: WebSocket) -> None:
            nonlocal delivered
            if ws.client_state != WebSocketState.CONNECTED:
                dead_sockets.append(ws)
                return
            try:
                await ws.send_json(message)
                delivered += 1
            except Exception:
                dead_sockets.append(ws)

        await asyncio.gather(*[_send(ws) for ws in sockets], return_exceptions=True)

        if dead_sockets:
            async with self._lock:
                feed_set = self._connections.get(feed_slug)
                if feed_set is not None:
                    for dead in dead_sockets:
                        feed_set.discard(dead)
                    if not feed_set:
                        del self._connections[feed_slug]

        return delivered

    async def handle_db_notification(self, payload: str) -> None:
        """Handle raw JSON notification payload from database listener."""
        try:
            data = json.loads(payload)
            event = FeedUpdateEvent.model_validate(data)
            await self.broadcast_to_feed(event.feed_slug, event.model_dump())
        except Exception as exc:
            logger.warning(
                "Discarding malformed or invalid database notification payload: %s",
                exc,
            )

    async def close_all(
        self, code: int = 1001, reason: str = "Server shutting down"
    ) -> None:
        """Close all active connections across all feeds gracefully."""
        async with self._lock:
            all_sockets = [
                ws for sockets in self._connections.values() for ws in sockets
            ]
            self._connections.clear()

        for ws in all_sockets:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.close(code=code, reason=reason)
            except Exception:
                pass

    def active_connection_count(self, feed_slug: str | None = None) -> int:
        """Return the current number of active connections."""
        if feed_slug is not None:
            return len(self._connections.get(feed_slug, set()))
        return sum(len(sockets) for sockets in self._connections.values())


ws_manager = ConnectionManager()
