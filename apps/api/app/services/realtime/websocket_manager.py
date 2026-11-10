"""WaitWatch API — WebSocket connection manager and fanout."""

import asyncio
import json
import logging
from collections import OrderedDict
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.services.realtime.events import FeedUpdateEvent

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active feed-scoped WebSocket connections, deduplication, and fanout."""

    def __init__(
        self,
        max_connections_per_feed: int = 500,
        max_recent_events: int = 1000,
    ) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._max_per_feed = max_connections_per_feed
        self._recent_events: OrderedDict[str, float] = OrderedDict()
        self._max_recent_events = max_recent_events

    def _deduplicate_event(self, event_key: str) -> bool:
        """Check if event_key was recently processed; if not, record it.

        Maintains true bounded LRU (Least Recently Used) semantics:
        duplicate hits move the key to the most-recently-used end.
        Returns True if duplicate (should be dropped), False if new (recorded).
        Caller should hold self._lock.
        """
        if not event_key:
            return False
        now = asyncio.get_event_loop().time()
        if event_key in self._recent_events:
            self._recent_events.move_to_end(event_key)
            return True
        self._recent_events[event_key] = now
        while len(self._recent_events) > self._max_recent_events:
            self._recent_events.popitem(last=False)
        return False

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

    async def handle_db_notification(self, payload: str) -> int:
        """Handle raw JSON notification from database listener or local dispatch.

        Guarantees that duplicate events (e.g. from both PostgreSQL NOTIFY and
        in-process commit dispatch) are broadcast to clients only once.
        Returns the number of clients to which the event was broadcast.
        """
        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                logger.warning(
                    "Discarding malformed or invalid database notification "
                    "payload (error_type=TypeError)"
                )
                return 0

            # Derive dedup key from raw decoded payload before model validation
            # so default_factory does not synthesize unique IDs for legacy payloads
            raw_event_id = data.get("event_id")
            if raw_event_id and isinstance(raw_event_id, str) and raw_event_id.strip():
                dedup_key = raw_event_id.strip()
            else:
                slug = str(data.get("feed_slug") or "").strip()
                utype = str(data.get("update_type") or "").strip()
                ts = str(data.get("timestamp") or "").strip()
                dedup_key = f"{slug}:{utype}:{ts}" if (slug and utype and ts) else ""

            async with self._lock:
                if dedup_key and self._deduplicate_event(dedup_key):
                    logger.debug("Dropping duplicate feed update notification")
                    return 0

            event = FeedUpdateEvent.model_validate(data)
            return await self.broadcast_to_feed(event.feed_slug, event.model_dump())
        except Exception as exc:
            logger.warning(
                "Discarding malformed or invalid database notification "
                "payload (error_type=%s)",
                type(exc).__name__,
            )
            return 0

    async def close_all(
        self, code: int = 1001, reason: str = "Server shutting down"
    ) -> None:
        """Close all active connections across all feeds gracefully."""
        async with self._lock:
            all_sockets = [
                ws for sockets in self._connections.values() for ws in sockets
            ]
            self._connections.clear()
            self._recent_events.clear()

        for ws in all_sockets:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.close(code=code, reason=reason)
            except Exception:
                pass

    def clear_recent_events(self) -> None:
        """Clear recent event cache (primarily for unit tests)."""
        self._recent_events.clear()

    def active_connection_count(self, feed_slug: str | None = None) -> int:
        """Return the current number of active connections."""
        if feed_slug is not None:
            return len(self._connections.get(feed_slug, set()))
        return sum(len(sockets) for sockets in self._connections.values())


ws_manager = ConnectionManager()
