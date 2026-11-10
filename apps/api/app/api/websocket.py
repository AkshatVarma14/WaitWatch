"""WaitWatch API — Feed-scoped WebSocket endpoint for live updates."""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.models.feed import TransitFeed
from app.services.realtime.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/feeds/{feed_slug}/ws")
async def feed_live_updates_ws(
    websocket: WebSocket,
    feed_slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Feed-scoped WebSocket endpoint for receiving live transit update notifications.

    Riders connect to this endpoint to receive real-time notifications whenever
    new vehicle positions or trip updates are ingested for the selected feed.
    Unknown or invalid feeds are safely rejected with error messages and policy
    violation close codes.
    """
    clean_slug = feed_slug.strip().lower()

    # Verify that the requested feed exists in the database
    stmt = select(TransitFeed).where(TransitFeed.slug == clean_slug)
    result = await session.execute(stmt)
    feed = result.scalar_one_or_none()

    if feed is None:
        logger.warning(
            "Rejecting WebSocket connection: feed '%s' does not exist", clean_slug
        )
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "error",
                "message": f"Feed '{clean_slug}' not found",
            }
        )
        await websocket.close(code=1008, reason="Feed not found")
        return

    # Accept connection and register with connection manager
    await websocket.accept()
    accepted = await ws_manager.connect(feed.slug, websocket)
    if not accepted:
        await websocket.send_json(
            {
                "type": "error",
                "message": "Connection capacity reached for this feed",
            }
        )
        await websocket.close(code=1013, reason="Try again later")
        return

    # Send initial connection acknowledgment
    await websocket.send_json(
        {
            "type": "connected",
            "feed_slug": feed.slug,
            "feed_id": feed.id,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )

    try:
        while True:
            # Keep socket open and process client heartbeats or messages
            message = await websocket.receive_text()
            if message.strip().lower() in ("ping", '{"type":"ping"}'):
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WebSocket closed unexpectedly for feed '%s': %s", feed.slug, exc)
    finally:
        await ws_manager.disconnect(feed.slug, websocket)
