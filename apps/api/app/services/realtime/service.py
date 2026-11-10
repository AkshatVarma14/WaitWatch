"""GTFS-Realtime Vehicle Position Ingestion Service."""

import logging
import os
from datetime import UTC, datetime

from geoalchemy2.elements import WKTElement
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feed import TransitFeed
from app.models.vehicle_position import VehiclePosition
from app.services.realtime.downloader import download_realtime_feed
from app.services.realtime.exceptions import (
    RealtimeDownloadError,
    RealtimePersistenceError,
)
from app.services.realtime.parser import parse_vehicle_positions

logger = logging.getLogger(__name__)


class VehiclePositionIngestionService:
    """Orchestrates download, parsing, and atomic replacement of vehicle positions."""

    async def ingest_for_feed(
        self,
        session: AsyncSession,
        feed: TransitFeed,
        *,
        raw_bytes: bytes | None = None,
    ) -> int:
        """Fetch, validate, and replace vehicle positions snapshot for a feed.

        Treats vehicle positions as a current-state snapshot table:
        replaces all positions for this feed atomically on success;
        rolls back and preserves previous positions on any failure.

        Args:
            session: Active database session.
            feed: TransitFeed model instance.
            raw_bytes: Optional pre-loaded protobuf bytes (for testing or CLI imports).

        Returns:
            int: Number of vehicle positions ingested.

        Raises:
            RealtimeDownloadError: If download fails or URL is not configured.
            RealtimeParseError: If protobuf payload is malformed or invalid.
            UnsupportedIncrementalityError: If feed uses DIFFERENTIAL incrementality.
            RealtimePersistenceError: If database persistence fails.
        """
        feed_id = feed.id
        feed_slug = feed.slug

        # 1. Fetch raw bytes if not provided
        if raw_bytes is None:
            if not feed.realtime_vehicle_positions_url:
                raise RealtimeDownloadError(
                    f"Feed '{feed_slug}' has no realtime_vehicle_positions_url"
                )

            api_key: str | None = None
            if feed.api_key_env_var:
                api_key = os.environ.get(feed.api_key_env_var)
                if not api_key:
                    logger.warning(
                        "Environment variable %s for feed %s is not set",
                        feed.api_key_env_var,
                        feed_slug,
                    )

            raw_bytes = await download_realtime_feed(
                feed.realtime_vehicle_positions_url,
                api_key=api_key,
            )

        # 2. Parse and validate protobuf message
        parsed_feed = parse_vehicle_positions(raw_bytes)

        # 3. Atomically replace the current vehicle position snapshot for this feed
        try:
            # Delete previous snapshot rows for this feed only
            await session.execute(
                delete(VehiclePosition).where(VehiclePosition.feed_id == feed_id)
            )

            # Insert new snapshot rows
            entities = [
                VehiclePosition(
                    feed_id=feed_id,
                    entity_id=vp.entity_id,
                    vehicle_id=vp.vehicle_id,
                    vehicle_label=vp.vehicle_label,
                    license_plate=vp.license_plate,
                    trip_id=vp.trip_id,
                    route_id=vp.route_id,
                    direction_id=vp.direction_id,
                    start_time=vp.start_time,
                    start_date=vp.start_date,
                    schedule_relationship=vp.schedule_relationship,
                    stop_id=vp.stop_id,
                    current_stop_sequence=vp.current_stop_sequence,
                    current_status=vp.current_status,
                    latitude=vp.latitude,
                    longitude=vp.longitude,
                    point=WKTElement(f"POINT({vp.longitude} {vp.latitude})", srid=4326),
                    bearing=vp.bearing,
                    odometer=vp.odometer,
                    speed=vp.speed,
                    congestion_level=vp.congestion_level,
                    occupancy_status=vp.occupancy_status,
                    occupancy_percentage=vp.occupancy_percentage,
                    feed_timestamp=parsed_feed.feed_timestamp,
                    vehicle_timestamp=vp.vehicle_timestamp,
                )
                for vp in parsed_feed.vehicles
            ]
            session.add_all(entities)

            # Update feed last_realtime_poll_at after validation and additions
            feed.last_realtime_poll_at = datetime.now(UTC)
            session.add(feed)

            # Commit transaction atomically
            await session.commit()
            logger.info(
                "Ingested %d vehicle positions for feed '%s' (feed time: %s)",
                len(entities),
                feed_slug,
                parsed_feed.feed_timestamp,
            )
            return len(entities)
        except Exception as exc:
            await session.rollback()
            logger.error(
                "Failed to commit vehicle position snapshot for feed '%s': %s",
                feed_slug,
                exc,
            )
            raise RealtimePersistenceError(
                f"Failed to persist vehicle positions snapshot for '{feed_slug}': {exc}"
            ) from exc

    async def ingest_for_feed_slug(
        self,
        session: AsyncSession,
        feed_slug: str,
        *,
        raw_bytes: bytes | None = None,
    ) -> int:
        """Ingest vehicle positions for a feed looked up by slug."""
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
        """Ingest vehicle positions for a feed looked up by primary key ID."""
        stmt = select(TransitFeed).where(TransitFeed.id == feed_id)
        result = await session.execute(stmt)
        feed = result.scalar_one_or_none()
        if not feed:
            raise ValueError(f"Transit feed with ID {feed_id} not found")
        return await self.ingest_for_feed(session, feed, raw_bytes=raw_bytes)
