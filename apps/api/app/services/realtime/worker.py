"""Periodic polling worker for enabled GTFS-Realtime feeds."""

import asyncio
import logging

from sqlalchemy import select

from app.database.session import async_session_factory
from app.models.feed import TransitFeed
from app.services.realtime.service import VehiclePositionIngestionService

logger = logging.getLogger(__name__)

REALTIME_POLL_INTERVAL_SECONDS = 30


async def poll_enabled_feeds_once() -> None:
    """Poll each active feed with live vehicle tracking enabled once."""
    async with async_session_factory() as session:
        stmt = (
            select(TransitFeed.id)
            .where(
                TransitFeed.feed_status == "active",
                TransitFeed.is_live_tracking_enabled.is_(True),
                TransitFeed.realtime_vehicle_positions_url.is_not(None),
            )
            .order_by(TransitFeed.id.asc())
        )
        feed_ids = (await session.execute(stmt)).scalars().all()

    for feed_id in feed_ids:
        async with async_session_factory() as session:
            feed_stmt = select(TransitFeed).where(TransitFeed.id == feed_id)
            feed = (await session.execute(feed_stmt)).scalar_one_or_none()
            if feed is None:
                continue

            try:
                count = await VehiclePositionIngestionService().ingest_for_feed(
                    session, feed
                )
                logger.info(
                    "Realtime poll completed for feed %s with %d vehicles",
                    feed.slug,
                    count,
                )
            except Exception as exc:
                await session.rollback()
                logger.warning(
                    "Realtime poll failed for feed %s (%s)",
                    feed.slug,
                    type(exc).__name__,
                )


async def run_realtime_poll_loop(
    stop_event: asyncio.Event,
    *,
    interval_seconds: int = REALTIME_POLL_INTERVAL_SECONDS,
) -> None:
    """Poll live feeds periodically until the application shuts down."""
    while not stop_event.is_set():
        try:
            await poll_enabled_feeds_once()
        except Exception as exc:
            logger.warning("Realtime polling cycle failed (%s)", type(exc).__name__)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
