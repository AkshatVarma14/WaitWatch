"""WaitWatch API — Real-time feed update events and pub/sub utilities."""

import logging
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CHANNEL_NAME = "waitwatch_feed_updates"


class FeedUpdateEvent(BaseModel):
    """Small bounded event payload published when a feed snapshot is updated.

    Must never contain sensitive credentials, tokens, or raw feed data.
    """

    model_config = ConfigDict(extra="ignore")

    type: Literal["feed_update"] = "feed_update"
    event_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Globally unique identifier for this update event",
    )
    feed_id: int = Field(..., description="Internal database ID of the feed")
    feed_slug: str = Field(..., description="Unique slug of the transit feed")
    update_type: Literal["vehicles", "trip_updates", "all"] = Field(
        ..., description="Category of realtime data updated"
    )
    timestamp: str = Field(
        ..., description="ISO 8601 UTC timestamp of update ingestion"
    )
    vehicle_count: int | None = Field(
        default=None, description="Count of vehicles in snapshot"
    )
    trip_update_count: int | None = Field(
        default=None, description="Count of trip updates in snapshot"
    )


async def publish_feed_update(session: AsyncSession, event: FeedUpdateEvent) -> None:
    """Stage a feed update notification within the active database transaction.

    On PostgreSQL, executes `pg_notify` within the open transaction. PostgreSQL
    guarantees that if the transaction commits, the notification is delivered;
    if the transaction rolls back or fails, the notification is dropped.

    Also records the event in `session.info` for post-commit in-process dispatch
    (enabling zero-broker operation in SQLite tests or standalone execution).
    """
    # Track event on session for post-commit dispatch
    pending: list[FeedUpdateEvent] = session.info.setdefault("_pending_feed_events", [])
    pending.append(event)

    # Check database dialect
    try:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            payload_json = event.model_dump_json()
            await session.execute(
                text("SELECT pg_notify(:channel, :payload)"),
                {"channel": CHANNEL_NAME, "payload": payload_json},
            )
            logger.debug(
                "Staged pg_notify on channel '%s' for feed '%s' (%s)",
                CHANNEL_NAME,
                event.feed_slug,
                event.update_type,
            )
    except Exception as exc:
        logger.warning(
            "Could not stage pg_notify on session: %s. "
            "Relying on post-commit fallback.",
            exc,
        )


async def dispatch_pending_feed_events(
    session: AsyncSession, ws_manager: Any | None = None
) -> list[FeedUpdateEvent]:
    """Dispatch staged events after successful transaction commit.

    Called only when `session.commit()` completes successfully.
    """
    events: list[FeedUpdateEvent] = session.info.pop("_pending_feed_events", [])
    if not events:
        return []

    if ws_manager is not None:
        for event in events:
            try:
                await ws_manager.handle_db_notification(event.model_dump_json())
            except Exception as exc:
                logger.warning(
                    "Error in post-commit in-process dispatch for '%s': %s",
                    event.feed_slug,
                    exc,
                )

    return events


def clear_pending_feed_events(session: AsyncSession) -> None:
    """Clear staged events on transaction failure or rollback."""
    session.info.pop("_pending_feed_events", None)
