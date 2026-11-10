"""GTFS-Realtime TripUpdates Ingestion Service."""

import logging
import os
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feed import TransitFeed
from app.models.trip_update import TripUpdate
from app.services.realtime.downloader import download_realtime_feed
from app.services.realtime.exceptions import (
    RealtimeDownloadError,
    RealtimePersistenceError,
)
from app.services.realtime.parser import (
    ParsedTripUpdatesFeed,
    parse_trip_updates,
)

logger = logging.getLogger(__name__)


class TripUpdateIngestionService:
    """Orchestrates download, parsing, and replacement for trip updates."""

    async def ingest_for_feed(
        self,
        session: AsyncSession,
        feed: TransitFeed,
        *,
        raw_bytes: bytes | None = None,
    ) -> int:
        """Fetch, validate, and atomically ingest GTFS-RT TripUpdates.

        Treats trip updates and constituent stop-time predictions as a
        current-state snapshot table for each transit feed. Atomically replaces
        the feed-scoped snapshot, preserving the previous snapshot on any failure.

        Args:
            session: Active database session.
            feed: TransitFeed model instance.
            raw_bytes: Optional pre-loaded protobuf bytes (for testing or CLI imports).

        Returns:
            int: Number of trip update / stop time update rows persisted.

        Raises:
            RealtimeDownloadError: If download fails and URL is configured.
            RealtimeParseError: If protobuf payload is malformed or invalid.
            UnsupportedIncrementalityError: If feed uses DIFFERENTIAL incrementality.
            RealtimePersistenceError: If database persistence fails.
        """
        feed_id = feed.id
        feed_slug = feed.slug
        receipt_time = datetime.now(UTC)

        # 1. Fetch raw bytes if not provided; skip gracefully if URL is not configured
        if raw_bytes is None:
            if not feed.realtime_trip_updates_url:
                logger.info(
                    "Feed '%s' has no realtime_trip_updates_url configured; skipping",
                    feed_slug,
                )
                return 0

            api_key: str | None = None
            if feed.api_key_env_var:
                api_key = os.environ.get(feed.api_key_env_var)
                if not api_key:
                    logger.warning(
                        "Environment variable %s for feed %s is not set",
                        feed.api_key_env_var,
                        feed_slug,
                    )

            try:
                raw_bytes = await download_realtime_feed(
                    feed.realtime_trip_updates_url,
                    api_key=api_key,
                )
            except RealtimeDownloadError:
                raise
            except Exception as exc:
                raise RealtimeDownloadError(
                    f"Failed to download trip updates for '{feed_slug}': {exc}"
                ) from exc

        # 2. Parse and validate protobuf message
        parsed_feed: ParsedTripUpdatesFeed = parse_trip_updates(raw_bytes)

        # 3. Atomically replace snapshot for this feed
        try:
            # Delete previous trip update snapshot rows for this feed only
            await session.execute(
                delete(TripUpdate).where(TripUpdate.feed_id == feed_id)
            )

            # Build new snapshot rows
            snapshot_entities: list[TripUpdate] = []
            for tu in parsed_feed.trip_updates:
                if tu.stop_time_updates:
                    for stu in tu.stop_time_updates:
                        snapshot_entities.append(
                            TripUpdate(
                                feed_id=feed_id,
                                entity_id=tu.entity_id,
                                trip_id=tu.trip_id,
                                route_id=tu.route_id,
                                direction_id=tu.direction_id,
                                start_time=tu.start_time,
                                start_date=tu.start_date,
                                schedule_relationship=tu.schedule_relationship,
                                vehicle_id=tu.vehicle_id,
                                vehicle_label=tu.vehicle_label,
                                vehicle_license_plate=tu.vehicle_license_plate,
                                stop_sequence=stu.stop_sequence,
                                stop_id=stu.stop_id,
                                arrival_time=(
                                    stu.arrival.time if stu.arrival else None
                                ),
                                arrival_delay=(
                                    stu.arrival.delay if stu.arrival else None
                                ),
                                arrival_uncertainty=(
                                    stu.arrival.uncertainty if stu.arrival else None
                                ),
                                departure_time=(
                                    stu.departure.time if stu.departure else None
                                ),
                                departure_delay=(
                                    stu.departure.delay if stu.departure else None
                                ),
                                departure_uncertainty=(
                                    stu.departure.uncertainty if stu.departure else None
                                ),
                                stop_schedule_relationship=stu.schedule_relationship,
                                trip_delay=tu.delay,
                                update_timestamp=tu.timestamp,
                                feed_timestamp=parsed_feed.feed_timestamp,
                            )
                        )
                else:
                    # Trip-level update without constituent stop-time updates
                    # (e.g. whole-trip cancellation or general trip delay)
                    snapshot_entities.append(
                        TripUpdate(
                            feed_id=feed_id,
                            entity_id=tu.entity_id,
                            trip_id=tu.trip_id,
                            route_id=tu.route_id,
                            direction_id=tu.direction_id,
                            start_time=tu.start_time,
                            start_date=tu.start_date,
                            schedule_relationship=tu.schedule_relationship,
                            vehicle_id=tu.vehicle_id,
                            vehicle_label=tu.vehicle_label,
                            vehicle_license_plate=tu.vehicle_license_plate,
                            stop_sequence=None,
                            stop_id=None,
                            arrival_time=None,
                            arrival_delay=None,
                            arrival_uncertainty=None,
                            departure_time=None,
                            departure_delay=None,
                            departure_uncertainty=None,
                            stop_schedule_relationship=None,
                            trip_delay=tu.delay,
                            update_timestamp=tu.timestamp,
                            feed_timestamp=parsed_feed.feed_timestamp,
                        )
                    )

            session.add_all(snapshot_entities)

            # Update feed last_realtime_poll_at timestamp
            feed.last_realtime_poll_at = receipt_time
            session.add(feed)

            # Commit transaction atomically
            await session.commit()
            logger.info(
                "Ingested %d trip update records across %d trips for feed '%s'",
                len(snapshot_entities),
                len(parsed_feed.trip_updates),
                feed_slug,
            )
            return len(snapshot_entities)
        except Exception as exc:
            await session.rollback()
            logger.error(
                "Failed to commit trip updates snapshot for feed '%s': %s",
                feed_slug,
                exc,
            )
            raise RealtimePersistenceError(
                f"Failed to persist trip updates snapshot for '{feed_slug}': {exc}"
            ) from exc

    async def ingest_for_feed_slug(
        self,
        session: AsyncSession,
        feed_slug: str,
        *,
        raw_bytes: bytes | None = None,
    ) -> int:
        """Ingest trip updates for a feed looked up by slug."""
        stmt = select(TransitFeed).where(TransitFeed.slug == feed_slug)
        result = await session.execute(stmt)
        feed = result.scalar_one_or_none()
        if not feed:
            raise ValueError(f"Transit feed with slug '{feed_slug}' not found")
        return await self.ingest_for_feed(session, feed, raw_bytes=raw_bytes)

    async def ingest_for_feed_id(
        self,
        session: AsyncSession,
        feed_id: int,
        *,
        raw_bytes: bytes | None = None,
    ) -> int:
        """Ingest trip updates for a feed looked up by primary key ID."""
        stmt = select(TransitFeed).where(TransitFeed.id == feed_id)
        result = await session.execute(stmt)
        feed = result.scalar_one_or_none()
        if not feed:
            raise ValueError(f"Transit feed with ID {feed_id} not found")
        return await self.ingest_for_feed(session, feed, raw_bytes=raw_bytes)
