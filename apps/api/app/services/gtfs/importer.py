"""Feed-scoped database persistence for parsed GTFS entities."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from geoalchemy2.elements import WKTElement
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Agency,
    Calendar,
    CalendarDate,
    Route,
    Shape,
    Stop,
    StopTime,
    TransitFeed,
    Trip,
)
from app.services.gtfs.exceptions import GTFSPersistenceError
from app.services.gtfs.parser import ParsedFeedData

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestionStats:
    """Summary metrics of a completed GTFS static feed import."""

    feed_id: int
    agencies_count: int
    routes_count: int
    stops_count: int
    calendars_count: int
    calendar_dates_count: int
    trips_count: int
    stop_times_count: int
    shapes_count: int
    imported_at: datetime


async def persist_feed_data(
    session: AsyncSession,
    feed_id: int,
    data: ParsedFeedData,
    *,
    batch_size: int = 1000,
) -> IngestionStats:
    """Persist parsed GTFS data into the database within current session transaction.

    This operation is feed-scoped and idempotent: all existing records for the given
    feed are cleared in reverse foreign key order before the new records are inserted.
    High-volume tables (stop_times) are inserted in bounded batches.

    Args:
        session: Active AsyncSession (caller manages outer transaction/commit/rollback).
        feed_id: ID of the TransitFeed being updated.
        data: Validated GTFS entities.
        batch_size: Chunk size for bulk insertions.

    Returns:
        IngestionStats: Counts of records inserted and timestamp.

    Raises:
        GTFSPersistenceError: If feed does not exist or database operations fail.
    """
    stmt = select(TransitFeed).where(TransitFeed.id == feed_id)
    result = await session.execute(stmt)
    feed = result.scalar_one_or_none()
    if not feed:
        raise GTFSPersistenceError(f"Transit feed with ID {feed_id} does not exist")

    logger.info(
        "Beginning idempotent static import for feed ID %d (%s)",
        feed_id,
        feed.slug,
    )

    try:
        # 1. Clear existing static transit records for this feed (in reverse FK order)
        logger.debug("Clearing existing data for feed ID %d", feed_id)
        await session.execute(delete(StopTime).where(StopTime.feed_id == feed_id))
        await session.execute(delete(Trip).where(Trip.feed_id == feed_id))
        await session.execute(delete(Route).where(Route.feed_id == feed_id))
        await session.execute(delete(Shape).where(Shape.feed_id == feed_id))

        # Break any self-referencing parent station foreign keys before deleting stops
        await session.execute(
            update(Stop).where(Stop.feed_id == feed_id).values(parent_station_id=None)
        )
        await session.execute(delete(Stop).where(Stop.feed_id == feed_id))
        await session.execute(
            delete(CalendarDate).where(CalendarDate.feed_id == feed_id)
        )
        await session.execute(delete(Calendar).where(Calendar.feed_id == feed_id))
        await session.execute(delete(Agency).where(Agency.feed_id == feed_id))
        await session.flush()

        # 2. Insert Agencies
        agency_entities = [
            Agency(
                feed_id=feed_id,
                agency_id=a.agency_id,
                name=a.name,
                url=a.url,
                timezone=a.timezone,
                phone=a.phone,
                lang=a.lang,
                fare_url=a.fare_url,
                email=a.email,
            )
            for a in data.agencies
        ]
        session.add_all(agency_entities)
        await session.flush()

        # Map GTFS agency_id to database internal Agency.id
        agency_pk_map: dict[str | None, int] = {}
        for a_ent in agency_entities:
            if a_ent.agency_id:
                agency_pk_map[a_ent.agency_id] = a_ent.id
            if len(agency_entities) == 1:
                # In single-agency feeds, allow None or empty string resolution
                agency_pk_map[None] = a_ent.id
                agency_pk_map[""] = a_ent.id

        # 3. Insert Routes
        route_entities: list[Route] = []
        for r in data.routes:
            internal_agency_id = agency_pk_map.get(r.agency_id)
            if internal_agency_id is None:
                raise GTFSPersistenceError(
                    f"Route {r.route_id!r} could not resolve internal agency ID"
                )
            route_entities.append(
                Route(
                    feed_id=feed_id,
                    agency_id=internal_agency_id,
                    route_id=r.route_id,
                    short_name=r.short_name,
                    long_name=r.long_name,
                    description=r.description,
                    route_type=r.route_type,
                    route_url=r.route_url,
                    route_color=r.route_color,
                    text_color=r.text_color,
                    sort_order=r.sort_order,
                )
            )
        session.add_all(route_entities)
        await session.flush()

        route_pk_map: dict[str, int] = {r.route_id: r.id for r in route_entities}

        # 4. Insert Stops
        stop_entities = [
            Stop(
                feed_id=feed_id,
                stop_id=s.stop_id,
                code=s.code,
                name=s.name,
                description=s.description,
                latitude=s.latitude,
                longitude=s.longitude,
                point=WKTElement(f"POINT({s.longitude} {s.latitude})", srid=4326),
                parent_station_id=None,
                location_type=s.location_type,
                wheelchair_boarding=s.wheelchair_boarding,
                platform_code=s.platform_code,
                timezone=s.timezone,
            )
            for s in data.stops
        ]
        session.add_all(stop_entities)
        await session.flush()

        stop_pk_map: dict[str, int] = {s.stop_id: s.id for s in stop_entities}

        # Update parent_station_id for platforms / child stops
        for s in data.stops:
            if s.parent_station and s.parent_station in stop_pk_map:
                stop_pk = stop_pk_map[s.stop_id]
                parent_pk = stop_pk_map[s.parent_station]
                await session.execute(
                    update(Stop)
                    .where(Stop.id == stop_pk)
                    .values(parent_station_id=parent_pk)
                )
        await session.flush()

        # 5. Insert Calendars
        calendar_entities = [
            Calendar(
                feed_id=feed_id,
                service_id=c.service_id,
                monday=c.monday,
                tuesday=c.tuesday,
                wednesday=c.wednesday,
                thursday=c.thursday,
                friday=c.friday,
                saturday=c.saturday,
                sunday=c.sunday,
                start_date=c.start_date,
                end_date=c.end_date,
            )
            for c in data.calendars
        ]
        if calendar_entities:
            session.add_all(calendar_entities)

        # 6. Insert CalendarDates
        calendar_date_entities = [
            CalendarDate(
                feed_id=feed_id,
                service_id=cd.service_id,
                date=cd.date,
                exception_type=cd.exception_type,
            )
            for cd in data.calendar_dates
        ]
        if calendar_date_entities:
            session.add_all(calendar_date_entities)
        await session.flush()

        # 7. Insert Trips
        trip_entities: list[Trip] = []
        for t in data.trips:
            internal_route_id = route_pk_map.get(t.route_id)
            if internal_route_id is None:
                raise GTFSPersistenceError(
                    f"Trip {t.trip_id!r} could not resolve internal route ID"
                )
            trip_entities.append(
                Trip(
                    feed_id=feed_id,
                    route_id=internal_route_id,
                    service_id=t.service_id,
                    trip_id=t.trip_id,
                    trip_headsign=t.trip_headsign,
                    trip_short_name=t.trip_short_name,
                    direction_id=t.direction_id,
                    block_id=t.block_id,
                    shape_id=t.shape_id,
                    wheelchair_accessible=t.wheelchair_accessible,
                    bikes_allowed=t.bikes_allowed,
                )
            )
        session.add_all(trip_entities)
        await session.flush()

        trip_pk_map: dict[str, int] = {t.trip_id: t.id for t in trip_entities}

        # 8. Insert StopTimes in Bounded Batches
        total_stop_times = len(data.stop_times)
        for i in range(0, total_stop_times, batch_size):
            chunk = data.stop_times[i : i + batch_size]
            chunk_entities: list[StopTime] = []
            for st in chunk:
                trip_pk = trip_pk_map.get(st.trip_id)
                stop_pk = stop_pk_map.get(st.stop_id)
                if trip_pk is None or stop_pk is None:
                    raise GTFSPersistenceError(
                        f"StopTime references unknown ID (trip={st.trip_id!r}, "
                        f"stop={st.stop_id!r})"
                    )
                chunk_entities.append(
                    StopTime(
                        feed_id=feed_id,
                        trip_id=trip_pk,
                        stop_id=stop_pk,
                        arrival_time=st.arrival_time,
                        departure_time=st.departure_time,
                        stop_sequence=st.stop_sequence,
                        stop_headsign=st.stop_headsign,
                        pickup_type=st.pickup_type,
                        drop_off_type=st.drop_off_type,
                        shape_dist_traveled=st.shape_dist_traveled,
                        timepoint=st.timepoint,
                    )
                )
            session.add_all(chunk_entities)
            await session.flush()

        # 9. Insert Shapes (in bounded chunks)
        total_shapes = 0
        for i in range(0, len(data.shapes), batch_size):
            chunk = data.shapes[i : i + batch_size]
            chunk_entities = []
            for s in chunk:
                wkt = f"SRID=4326;POINT({s.shape_pt_lon} {s.shape_pt_lat})"
                chunk_entities.append(
                    Shape(
                        feed_id=feed_id,
                        shape_id=s.shape_id,
                        shape_pt_lat=s.shape_pt_lat,
                        shape_pt_lon=s.shape_pt_lon,
                        shape_pt_sequence=s.shape_pt_sequence,
                        shape_dist_traveled=s.shape_dist_traveled,
                        point=WKTElement(wkt, srid=4326),
                    )
                )
            session.add_all(chunk_entities)
            await session.flush()
            total_shapes += len(chunk_entities)

        # 10. Update Feed Import Timestamp & Status
        now = datetime.now(UTC)
        feed.last_static_import_at = now
        feed.feed_status = "active"
        await session.flush()

        stats = IngestionStats(
            feed_id=feed_id,
            agencies_count=len(agency_entities),
            routes_count=len(route_entities),
            stops_count=len(stop_entities),
            calendars_count=len(calendar_entities),
            calendar_dates_count=len(calendar_date_entities),
            trips_count=len(trip_entities),
            stop_times_count=total_stop_times,
            shapes_count=total_shapes,
            imported_at=now,
        )
        logger.info(
            "Imported feed %d: %d routes, %d stops, %d trips, %d stop_times",
            feed_id,
            stats.routes_count,
            stats.stops_count,
            stats.trips_count,
            stats.stop_times_count,
        )
        return stats
    except Exception as exc:
        logger.error(
            "Static GTFS import failed for feed ID %d: %s",
            feed_id,
            exc,
            exc_info=True,
        )
        if isinstance(exc, GTFSPersistenceError):
            raise
        raise GTFSPersistenceError(f"Database error during GTFS import: {exc}") from exc
