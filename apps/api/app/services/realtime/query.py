"""Internal query helpers for historical vehicle observations."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vehicle_observation import VehicleObservation

logger = logging.getLogger(__name__)

DEFAULT_OBSERVATION_LIMIT = 100
MAX_OBSERVATION_LIMIT = 1000


async def get_recent_observations(
    session: AsyncSession,
    feed_id: int,
    *,
    since: datetime,
    until: datetime | None = None,
    vehicle_id: str | None = None,
    entity_id: str | None = None,
    route_id: str | None = None,
    trip_id: str | None = None,
    limit: int = DEFAULT_OBSERVATION_LIMIT,
) -> list[VehicleObservation]:
    """Retrieve historical vehicle observations for a feed with mandatory time bounds.

    Internal helper designed to support ETA prediction, speed profiling, and delay
    analysis by retrieving bounded observation windows for specific vehicles or routes.

    Args:
        session: Active async database session.
        feed_id: Internal primary key of the transit feed.
        since: Mandatory lower time bound (must be timezone-aware).
        until: Optional upper time bound.
        vehicle_id: Optional filter by vehicle descriptor ID.
        entity_id: Optional filter by GTFS entity ID.
        route_id: Optional filter by GTFS route ID.
        trip_id: Optional filter by GTFS trip ID.
        limit: Maximum observations to return (capped at 1000).

    Returns:
        list[VehicleObservation]: Matching observations ordered newest to oldest.

    Raises:
        ValueError: If `since` is omitted or limit is non-positive.
    """
    if since is None:
        raise ValueError("A 'since' timestamp is required for observation queries")

    # Ensure since and until are timezone-aware in UTC
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)

    if until is not None and until.tzinfo is None:
        until = until.replace(tzinfo=UTC)

    bounded_limit = min(max(1, limit), MAX_OBSERVATION_LIMIT)

    stmt = select(VehicleObservation).where(
        VehicleObservation.feed_id == feed_id,
        VehicleObservation.observed_at >= since,
    )

    if until is not None:
        stmt = stmt.where(VehicleObservation.observed_at <= until)

    if vehicle_id is not None:
        stmt = stmt.where(VehicleObservation.vehicle_id == vehicle_id)

    if entity_id is not None:
        stmt = stmt.where(VehicleObservation.entity_id == entity_id)

    if route_id is not None:
        stmt = stmt.where(VehicleObservation.route_id == route_id)

    if trip_id is not None:
        stmt = stmt.where(VehicleObservation.trip_id == trip_id)

    stmt = stmt.order_by(VehicleObservation.observed_at.desc()).limit(bounded_limit)

    result = await session.execute(stmt)
    observations = list(result.scalars().all())
    logger.debug(
        "Retrieved %d observations for feed %d (since=%s, vehicle=%s, route=%s)",
        len(observations),
        feed_id,
        since,
        vehicle_id,
        route_id,
    )
    return observations
