"""GTFS-Realtime Vehicle Position Ingestion Service."""

import logging
import os
from datetime import UTC, datetime

from geoalchemy2.elements import WKTElement
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feed import TransitFeed
from app.models.vehicle_observation import VehicleObservation
from app.models.vehicle_position import VehiclePosition
from app.services.realtime.downloader import download_realtime_feed
from app.services.realtime.events import (
    FeedUpdateEvent,
    clear_pending_feed_events,
    dispatch_pending_feed_events,
    publish_feed_update,
)
from app.services.realtime.exceptions import (
    RealtimeDownloadError,
    RealtimePersistenceError,
)
from app.services.realtime.parser import (
    ParsedVehiclePosition,
    parse_vehicle_positions,
)
from app.services.realtime.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


class VehiclePositionIngestionService:
    """Orchestrates download, parsing, snapshot replacement, and history storage."""

    async def ingest_for_feed(
        self,
        session: AsyncSession,
        feed: TransitFeed,
        *,
        raw_bytes: bytes | None = None,
    ) -> int:
        """Fetch, validate, and atomically ingest vehicle positions and history samples.

        Treats vehicle positions as a current-state snapshot table while appending
        validated historical vehicle observations with duplicate sample deduplication.
        Atomically replaces snapshot and appends history; rolls back and preserves
        previous snapshot without partial history on any failure.

        Args:
            session: Active database session.
            feed: TransitFeed model instance.
            raw_bytes: Optional pre-loaded protobuf bytes (for testing or CLI imports).

        Returns:
            int: Number of vehicle positions in the current snapshot.

        Raises:
            RealtimeDownloadError: If download fails or URL is not configured.
            RealtimeParseError: If protobuf payload is malformed or invalid.
            UnsupportedIncrementalityError: If feed uses DIFFERENTIAL incrementality.
            RealtimePersistenceError: If database persistence fails.
        """
        feed_id = feed.id
        feed_slug = feed.slug
        receipt_time = datetime.now(UTC)

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

        # 3. Atomically replace snapshot and append historical observations
        try:
            # Delete previous snapshot rows for this feed only
            await session.execute(
                delete(VehiclePosition).where(VehiclePosition.feed_id == feed_id)
            )

            # Insert new snapshot rows
            snapshot_entities = [
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
            session.add_all(snapshot_entities)

            # Deduplicate and append historical observations
            # Determine canonical observed_at for each vehicle:
            # 1) source vehicle_timestamp if present
            # 2) feed_timestamp from header if present
            # 3) poll receipt_time fallback when source timestamps are absent
            candidate_obs: list[tuple[ParsedVehiclePosition, datetime]] = []
            candidate_keys: set[tuple[str, datetime]] = set()

            for vp in parsed_feed.vehicles:
                obs_time = (
                    vp.vehicle_timestamp or parsed_feed.feed_timestamp or receipt_time
                )
                key = (vp.entity_id, obs_time)
                if key not in candidate_keys:
                    candidate_keys.add(key)
                    candidate_obs.append((vp, obs_time))

            if candidate_obs:
                entity_ids = [k[0] for k in candidate_keys]
                obs_times = [k[1] for k in candidate_keys]

                # Check which observations already exist for this feed
                existing_stmt = select(
                    VehicleObservation.entity_id,
                    VehicleObservation.observed_at,
                ).where(
                    VehicleObservation.feed_id == feed_id,
                    VehicleObservation.entity_id.in_(entity_ids),
                    VehicleObservation.observed_at.in_(obs_times),
                )
                existing_rows = (await session.execute(existing_stmt)).all()
                existing_keys = {
                    (
                        r[0],
                        r[1].replace(tzinfo=UTC)
                        if (r[1] is not None and r[1].tzinfo is None)
                        else (r[1].astimezone(UTC) if r[1] is not None else None),
                    )
                    for r in existing_rows
                }

                new_observations: list[VehicleObservation] = []
                seen_batch_keys: set[tuple[str, datetime | None]] = set()
                for vp, obs_time in candidate_obs:
                    norm_obs_time = (
                        obs_time.replace(tzinfo=UTC)
                        if obs_time.tzinfo is None
                        else obs_time.astimezone(UTC)
                    )
                    key = (vp.entity_id, norm_obs_time)
                    if key not in existing_keys and key not in seen_batch_keys:
                        seen_batch_keys.add(key)
                        new_observations.append(
                            VehicleObservation(
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
                                point=WKTElement(
                                    f"POINT({vp.longitude} {vp.latitude})",
                                    srid=4326,
                                ),
                                bearing=vp.bearing,
                                odometer=vp.odometer,
                                speed=vp.speed,
                                congestion_level=vp.congestion_level,
                                occupancy_status=vp.occupancy_status,
                                occupancy_percentage=vp.occupancy_percentage,
                                observed_at=obs_time,
                                feed_timestamp=parsed_feed.feed_timestamp,
                                vehicle_timestamp=vp.vehicle_timestamp,
                            )
                        )
                session.add_all(new_observations)
                new_obs_count = len(new_observations)
            else:
                new_obs_count = 0

            # Update feed last_realtime_poll_at after validation and additions
            feed.last_realtime_poll_at = receipt_time
            session.add(feed)

            # Stage feed update notification within the transaction
            event = FeedUpdateEvent(
                feed_id=feed.id,
                feed_slug=feed_slug,
                update_type="vehicles",
                timestamp=receipt_time.isoformat(),
                vehicle_count=len(snapshot_entities),
            )
            await publish_feed_update(session, event)

            # Commit transaction atomically
            await session.commit()
            await dispatch_pending_feed_events(session, ws_manager)

            logger.info(
                "Ingested %d snapshot vehicles and %d new observations for feed '%s'",
                len(snapshot_entities),
                new_obs_count,
                feed_slug,
            )
            return len(snapshot_entities)
        except Exception as exc:
            clear_pending_feed_events(session)
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
