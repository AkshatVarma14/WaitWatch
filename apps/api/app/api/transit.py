"""WaitWatch API — Transit route, stop, and feed exploration endpoints."""

import logging
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from datetime import date as datetime_date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_MakePoint, ST_SetSRID
from sqlalchemy import cast, func, or_, select
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from app.database.session import get_session
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
    TripUpdate,
    VehiclePosition,
)
from app.schemas.transit import (
    FeedDetailResponse,
    FeedSummaryResponse,
    ItemEnvelope,
    NearbyStopResponse,
    PaginatedResponse,
    PaginationMeta,
    RouteDetailResponse,
    RouteMapResponse,
    RouteMapStopResponse,
    RouteMapVehicleResponse,
    RouteResponse,
    RouteShapeResponse,
    ShapePointResponse,
    StopArrivalPrediction,
    StopDetailResponse,
    StopPlanDetailResponse,
    StopResponse,
    TripItineraryResponse,
    TripPlanResponse,
)
from app.services.prediction import (
    ArrivalPredictionService,
    resolve_feed_timezone,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters using the haversine formula."""
    r = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return r * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


async def _get_feed_by_slug(session: AsyncSession, feed_slug: str) -> TransitFeed:
    """Look up a transit feed by slug or numeric ID, or raise 404."""
    if feed_slug.isdigit():
        stmt = select(TransitFeed).where(
            or_(TransitFeed.slug == feed_slug, TransitFeed.id == int(feed_slug))
        )
    else:
        stmt = select(TransitFeed).where(TransitFeed.slug == feed_slug)
    result = await session.execute(stmt)
    feed = result.scalar_one_or_none()
    if not feed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transit feed '{feed_slug}' not found",
        )
    return feed


# ---------------------------------------------------------------------------
# Feeds Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/feeds",
    response_model=ItemEnvelope[list[FeedSummaryResponse]],
    summary="List all configured transit feeds",
)
async def list_feeds(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ItemEnvelope[list[FeedSummaryResponse]]:
    """Return all configured transit feeds and their operational status."""
    try:
        stmt = select(TransitFeed).order_by(TransitFeed.city_name.asc())
        result = await session.execute(stmt)
        feeds = result.scalars().all()
        return ItemEnvelope(data=[FeedSummaryResponse.model_validate(f) for f in feeds])
    except (OperationalError, DBAPIError, TimeoutError, OSError) as exc:
        logger.warning("Database unavailable in list_feeds: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable",
        ) from exc


@router.get(
    "/feeds/{feed_slug}",
    response_model=ItemEnvelope[FeedDetailResponse],
    summary="Get transit feed configuration by slug",
)
async def get_feed(
    feed_slug: Annotated[
        str,
        Path(
            min_length=1,
            max_length=64,
            pattern=r"^[a-zA-Z0-9_-]+$",
            description="Feed slug identifier",
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ItemEnvelope[FeedDetailResponse]:
    """Return detailed metadata for a specific transit feed."""
    try:
        feed = await _get_feed_by_slug(session, feed_slug)
        return ItemEnvelope(data=FeedDetailResponse.model_validate(feed))
    except HTTPException:
        raise
    except (OperationalError, DBAPIError, TimeoutError, OSError) as exc:
        logger.warning("Database unavailable in get_feed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable",
        ) from exc


# ---------------------------------------------------------------------------
# Routes Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/feeds/{feed_slug}/routes",
    response_model=PaginatedResponse[RouteResponse],
    summary="List and filter transit routes within a feed",
)
async def list_routes(
    feed_slug: Annotated[
        str,
        Path(
            min_length=1,
            max_length=64,
            pattern=r"^[a-zA-Z0-9_-]+$",
            description="Feed slug identifier",
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    q: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=100,
            description="Text search on route short name, long name, or description",
        ),
    ] = None,
    route_type: Annotated[
        int | None,
        Query(
            ge=0,
            le=12,
            description=(
                "Filter by GTFS route_type (0=tram, 1=subway, 2=rail, 3=bus, etc.)"
            ),
        ),
    ] = None,
    agency_id: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=255,
            description="Filter by GTFS agency ID",
        ),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number (1-based)")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page (max 100)")
    ] = 20,
) -> PaginatedResponse[RouteResponse]:
    """List routes for a feed with search text, route_type, and agency filtering."""
    try:
        feed = await _get_feed_by_slug(session, feed_slug)

        base_stmt = (
            select(Route)
            .join(Agency, Route.agency_id == Agency.id)
            .where(Route.feed_id == feed.id)
        )

        if q:
            search_term = f"%{q.strip()}%"
            base_stmt = base_stmt.where(
                or_(
                    Route.short_name.ilike(search_term),
                    Route.long_name.ilike(search_term),
                    Route.description.ilike(search_term),
                )
            )

        if route_type is not None:
            base_stmt = base_stmt.where(Route.route_type == route_type)

        if agency_id:
            base_stmt = base_stmt.where(Agency.agency_id == agency_id.strip())

        # Total count query
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        # Paginated items with joinedload for agency to avoid N+1 queries
        data_stmt = (
            base_stmt.options(joinedload(Route.agency))
            .order_by(
                Route.sort_order.asc().nulls_last(),
                Route.short_name.asc().nulls_last(),
                Route.route_id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        routes = (await session.execute(data_stmt)).scalars().all()

        total_pages = math.ceil(total / page_size) if total > 0 else 0
        pagination = PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1 and total > 0,
        )

        items = [
            RouteResponse(
                route_id=r.route_id,
                agency_id=r.agency.agency_id if r.agency else None,
                short_name=r.short_name,
                long_name=r.long_name,
                description=r.description,
                route_type=r.route_type,
                route_url=r.route_url,
                route_color=r.route_color,
                text_color=r.text_color,
                sort_order=r.sort_order,
            )
            for r in routes
        ]

        return PaginatedResponse(data=items, pagination=pagination)
    except HTTPException:
        raise
    except (OperationalError, DBAPIError, TimeoutError, OSError) as exc:
        logger.warning("Database unavailable in list_routes: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable",
        ) from exc


@router.get(
    "/feeds/{feed_slug}/routes/{route_id}",
    response_model=ItemEnvelope[RouteDetailResponse],
    summary="Get route details by GTFS route_id",
)
async def get_route(
    feed_slug: Annotated[
        str,
        Path(
            min_length=1,
            max_length=64,
            pattern=r"^[a-zA-Z0-9_-]+$",
            description="Feed slug identifier",
        ),
    ],
    route_id: Annotated[
        str,
        Path(
            min_length=1,
            max_length=255,
            description="GTFS route identifier",
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ItemEnvelope[RouteDetailResponse]:
    """Retrieve full details of a specific route including operating agency info."""
    try:
        feed = await _get_feed_by_slug(session, feed_slug)

        stmt = (
            select(Route)
            .options(joinedload(Route.agency))
            .where(Route.feed_id == feed.id, Route.route_id == route_id)
        )
        route = (await session.execute(stmt)).scalar_one_or_none()

        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Route '{route_id}' not found in feed '{feed_slug}'",
            )

        return ItemEnvelope(
            data=RouteDetailResponse(
                route_id=route.route_id,
                agency_id=route.agency.agency_id if route.agency else None,
                short_name=route.short_name,
                long_name=route.long_name,
                description=route.description,
                route_type=route.route_type,
                route_url=route.route_url,
                route_color=route.route_color,
                text_color=route.text_color,
                sort_order=route.sort_order,
                agency_name=route.agency.name if route.agency else None,
                agency_url=route.agency.url if route.agency else None,
                agency_timezone=route.agency.timezone if route.agency else None,
            )
        )
    except HTTPException:
        raise
    except (OperationalError, DBAPIError, TimeoutError, OSError) as exc:
        logger.warning("Database unavailable in get_route: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable",
        ) from exc


@router.get(
    "/feeds/{feed_slug}/routes/{route_id}/map",
    response_model=ItemEnvelope[RouteMapResponse],
    summary="Get route geometry, ordered stops, and vehicles for map view",
)
async def get_route_map(
    feed_slug: Annotated[
        str,
        Path(
            min_length=1,
            max_length=64,
            pattern=r"^[a-zA-Z0-9_-]+$",
            description="Feed slug or numeric ID identifier",
        ),
    ],
    route_id: Annotated[
        str,
        Path(
            min_length=1,
            max_length=255,
            description="GTFS route identifier",
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    reference_time: Annotated[
        datetime | None,
        Query(
            description=(
                "Reference time for telemetry freshness check (defaults to UTC now)"
            ),
        ),
    ] = None,
) -> ItemEnvelope[RouteMapResponse]:
    """Retrieve GTFS shape points, ordered stops, and active vehicles for a route."""
    try:
        feed = await _get_feed_by_slug(session, feed_slug)

        # 1. Fetch route
        route_stmt = select(Route).where(
            Route.feed_id == feed.id, Route.route_id == route_id
        )
        route = (await session.execute(route_stmt)).scalar_one_or_none()
        if not route:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Route '{route_id}' not found in feed '{feed_slug}'",
            )

        # 2. Query distinct shape_ids from trips belonging to this route
        shape_ids_stmt = (
            select(Trip.shape_id)
            .where(
                Trip.feed_id == feed.id,
                Trip.route_id == route.id,
                Trip.shape_id.isnot(None),
            )
            .distinct()
            .order_by(Trip.shape_id.asc())
        )
        shape_ids = [
            s for s in (await session.execute(shape_ids_stmt)).scalars().all() if s
        ]

        route_shapes: list[RouteShapeResponse] = []
        if shape_ids:
            # Bound to at most 10 distinct shapes per route
            shape_ids = shape_ids[:10]
            shapes_stmt = (
                select(Shape)
                .where(Shape.feed_id == feed.id, Shape.shape_id.in_(shape_ids))
                .order_by(Shape.shape_id.asc(), Shape.shape_pt_sequence.asc())
            )
            shape_points = (await session.execute(shapes_stmt)).scalars().all()

            points_by_shape: dict[str, list[ShapePointResponse]] = defaultdict(list)
            for p in shape_points:
                points_by_shape[p.shape_id].append(
                    ShapePointResponse(
                        latitude=p.shape_pt_lat,
                        longitude=p.shape_pt_lon,
                        sequence=p.shape_pt_sequence,
                        distance_traveled=p.shape_dist_traveled,
                    )
                )

            for sid in shape_ids:
                pts = points_by_shape.get(sid, [])
                if pts:
                    route_shapes.append(RouteShapeResponse(shape_id=sid, points=pts))

        # 3. Retrieve ordered stops along the route
        stops_stmt = (
            select(
                Stop.stop_id,
                Stop.name,
                Stop.code,
                Stop.latitude,
                Stop.longitude,
                Stop.wheelchair_boarding,
                func.min(StopTime.stop_sequence).label("min_seq"),
                Trip.direction_id,
            )
            .join(StopTime, StopTime.stop_id == Stop.id)
            .join(Trip, Trip.id == StopTime.trip_id)
            .where(Trip.feed_id == feed.id, Trip.route_id == route.id)
            .group_by(
                Stop.stop_id,
                Stop.name,
                Stop.code,
                Stop.latitude,
                Stop.longitude,
                Stop.wheelchair_boarding,
                Trip.direction_id,
            )
            .order_by(
                Trip.direction_id.asc().nullslast(),
                func.min(StopTime.stop_sequence).asc(),
                Stop.name.asc(),
            )
            .limit(200)
        )
        stop_rows = (await session.execute(stops_stmt)).all()

        route_stops = [
            RouteMapStopResponse(
                stop_id=r[0],
                name=r[1],
                code=r[2],
                latitude=r[3],
                longitude=r[4],
                wheelchair_boarding=r[5],
                stop_sequence=r[6],
                direction_id=r[7],
            )
            for r in stop_rows
        ]

        # 4. Retrieve fresh vehicles currently assigned to this route
        now = reference_time or datetime.now(UTC)
        fresh_since = now - timedelta(seconds=300)
        max_future = now + timedelta(seconds=60)
        veh_time = func.coalesce(
            VehiclePosition.vehicle_timestamp,
            VehiclePosition.feed_timestamp,
            VehiclePosition.recorded_at,
        )

        veh_stmt = (
            select(VehiclePosition)
            .where(
                VehiclePosition.feed_id == feed.id,
                VehiclePosition.route_id == route_id,
                veh_time >= fresh_since,
                veh_time <= max_future,
            )
            .order_by(veh_time.desc(), VehiclePosition.entity_id.asc())
            .limit(50)
        )
        vehicles = (await session.execute(veh_stmt)).scalars().all()

        route_vehicles = [
            RouteMapVehicleResponse(
                entity_id=v.entity_id,
                vehicle_id=v.vehicle_id,
                vehicle_label=v.vehicle_label,
                latitude=v.latitude,
                longitude=v.longitude,
                bearing=v.bearing,
                speed=v.speed,
                current_status=v.current_status,
                trip_id=v.trip_id,
                observed_at=v.vehicle_timestamp or v.feed_timestamp or v.recorded_at,
            )
            for v in vehicles
        ]

        return ItemEnvelope(
            data=RouteMapResponse(
                feed_slug=feed.slug,
                route_id=route.route_id,
                route_short_name=route.short_name,
                route_long_name=route.long_name,
                route_color=route.route_color,
                text_color=route.text_color,
                shapes=route_shapes,
                stops=route_stops,
                vehicles=route_vehicles,
            )
        )
    except HTTPException:
        raise
    except (OperationalError, DBAPIError, TimeoutError, OSError) as exc:
        logger.warning("Database unavailable in get_route_map: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable",
        ) from exc


# ---------------------------------------------------------------------------
# Stops Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/feeds/{feed_slug}/stops",
    response_model=PaginatedResponse[StopResponse],
    summary="List and search transit stops within a feed",
)
async def list_stops(
    feed_slug: Annotated[
        str,
        Path(
            min_length=1,
            max_length=64,
            pattern=r"^[a-zA-Z0-9_-]+$",
            description="Feed slug identifier",
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    q: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=100,
            description="Text search on stop name, code, or stop_id",
        ),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number (1-based)")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page (max 100)")
    ] = 20,
) -> PaginatedResponse[StopResponse]:
    """List transit stops for a feed with search text and bounded pagination."""
    try:
        feed = await _get_feed_by_slug(session, feed_slug)

        base_stmt = select(Stop).where(Stop.feed_id == feed.id)

        if q:
            search_term = f"%{q.strip()}%"
            base_stmt = base_stmt.where(
                or_(
                    Stop.name.ilike(search_term),
                    Stop.code.ilike(search_term),
                    Stop.stop_id.ilike(search_term),
                )
            )

        # Count total matches
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        # Paginated items with joinedload for parent station to avoid N+1 queries
        data_stmt = (
            base_stmt.options(joinedload(Stop.parent_station))
            .order_by(Stop.name.asc(), Stop.stop_id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        stops = (await session.execute(data_stmt)).scalars().all()

        total_pages = math.ceil(total / page_size) if total > 0 else 0
        pagination = PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1 and total > 0,
        )

        items = [
            StopResponse(
                stop_id=s.stop_id,
                code=s.code,
                name=s.name,
                description=s.description,
                latitude=s.latitude,
                longitude=s.longitude,
                parent_station_id=(
                    s.parent_station.stop_id if s.parent_station else None
                ),
                location_type=s.location_type,
                wheelchair_boarding=s.wheelchair_boarding,
                platform_code=s.platform_code,
                timezone=s.timezone,
            )
            for s in stops
        ]

        return PaginatedResponse(data=items, pagination=pagination)
    except HTTPException:
        raise
    except (OperationalError, DBAPIError, TimeoutError, OSError) as exc:
        logger.warning("Database unavailable in list_stops: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable",
        ) from exc


@router.get(
    "/feeds/{feed_slug}/stops/nearby",
    response_model=ItemEnvelope[list[NearbyStopResponse]],
    summary="Query nearby transit stops by coordinates",
)
async def get_nearby_stops(
    feed_slug: Annotated[
        str,
        Path(
            min_length=1,
            max_length=64,
            pattern=r"^[a-zA-Z0-9_-]+$",
            description="Feed slug identifier",
        ),
    ],
    latitude: Annotated[
        float,
        Query(
            ge=-90.0,
            le=90.0,
            description="Reference WGS84 latitude coordinate",
        ),
    ],
    longitude: Annotated[
        float,
        Query(
            ge=-180.0,
            le=180.0,
            description="Reference WGS84 longitude coordinate",
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    radius_meters: Annotated[
        float,
        Query(
            ge=1.0,
            le=50000.0,
            description="Search radius in meters (default 1000m, max 50000m)",
        ),
    ] = 1000.0,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum stops to return (default 20, max 100)",
        ),
    ] = 20,
) -> ItemEnvelope[list[NearbyStopResponse]]:
    """Return stops sorted by distance from query coordinates within a radius.

    On PostgreSQL, utilizes the PostGIS GiST index and ST_DWithin/ST_Distance.
    On fallback dialects (SQLite tests), uses bounding box and haversine.
    """
    try:
        feed = await _get_feed_by_slug(session, feed_slug)
        conn = await session.connection()
        dialect_name = conn.dialect.name

        if dialect_name == "postgresql":
            # Native PostGIS geography query utilizing GiST spatial index
            ref_geog = cast(
                ST_SetSRID(ST_MakePoint(longitude, latitude), 4326),
                Geography,
            )
            dist_expr = ST_Distance(Stop.point, ref_geog).label("distance_meters")

            stmt = (
                select(Stop, dist_expr)
                .options(joinedload(Stop.parent_station))
                .where(Stop.feed_id == feed.id)
                .where(ST_DWithin(Stop.point, ref_geog, radius_meters))
                .order_by(dist_expr.asc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()

            results = [
                NearbyStopResponse(
                    stop_id=s.stop_id,
                    code=s.code,
                    name=s.name,
                    description=s.description,
                    latitude=s.latitude,
                    longitude=s.longitude,
                    parent_station_id=(
                        s.parent_station.stop_id if s.parent_station else None
                    ),
                    location_type=s.location_type,
                    wheelchair_boarding=s.wheelchair_boarding,
                    platform_code=s.platform_code,
                    timezone=s.timezone,
                    distance_meters=round(float(dist), 1),
                )
                for s, dist in rows
            ]
        else:
            # Dialect fallback (SQLite / unit tests without PostGIS)
            lat_delta = radius_meters / 111000.0
            cos_lat = max(math.cos(math.radians(latitude)), 0.01)
            lon_delta = radius_meters / (111000.0 * cos_lat)

            stmt = (
                select(Stop)
                .options(joinedload(Stop.parent_station))
                .where(Stop.feed_id == feed.id)
                .where(
                    Stop.latitude.between(latitude - lat_delta, latitude + lat_delta)
                )
                .where(
                    Stop.longitude.between(longitude - lon_delta, longitude + lon_delta)
                )
            )
            candidate_stops = (await session.execute(stmt)).scalars().all()

            scored: list[tuple[Stop, float]] = []
            for s in candidate_stops:
                dist = _haversine_meters(latitude, longitude, s.latitude, s.longitude)
                if dist <= radius_meters:
                    scored.append((s, dist))

            scored.sort(key=lambda pair: pair[1])
            results = [
                NearbyStopResponse(
                    stop_id=s.stop_id,
                    code=s.code,
                    name=s.name,
                    description=s.description,
                    latitude=s.latitude,
                    longitude=s.longitude,
                    parent_station_id=(
                        s.parent_station.stop_id if s.parent_station else None
                    ),
                    location_type=s.location_type,
                    wheelchair_boarding=s.wheelchair_boarding,
                    platform_code=s.platform_code,
                    timezone=s.timezone,
                    distance_meters=round(d, 1),
                )
                for s, d in scored[:limit]
            ]

        return ItemEnvelope(data=results)
    except HTTPException:
        raise
    except (OperationalError, DBAPIError, TimeoutError, OSError) as exc:
        logger.warning(
            "Database unavailable in get_nearby_stops: %s", type(exc).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable",
        ) from exc


@router.get(
    "/feeds/{feed_slug}/stops/{stop_id}",
    response_model=ItemEnvelope[StopDetailResponse],
    summary="Get stop details by GTFS stop_id",
)
async def get_stop(
    feed_slug: Annotated[
        str,
        Path(
            min_length=1,
            max_length=64,
            pattern=r"^[a-zA-Z0-9_-]+$",
            description="Feed slug identifier",
        ),
    ],
    stop_id: Annotated[
        str,
        Path(
            min_length=1,
            max_length=255,
            description="GTFS stop identifier",
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ItemEnvelope[StopDetailResponse]:
    """Retrieve full details of a specific stop within a feed."""
    try:
        feed = await _get_feed_by_slug(session, feed_slug)

        stmt = (
            select(Stop)
            .options(joinedload(Stop.parent_station))
            .where(Stop.feed_id == feed.id, Stop.stop_id == stop_id)
        )
        stop = (await session.execute(stmt)).scalar_one_or_none()

        if not stop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stop '{stop_id}' not found in feed '{feed_slug}'",
            )

        return ItemEnvelope(
            data=StopDetailResponse(
                stop_id=stop.stop_id,
                code=stop.code,
                name=stop.name,
                description=stop.description,
                latitude=stop.latitude,
                longitude=stop.longitude,
                parent_station_id=(
                    stop.parent_station.stop_id if stop.parent_station else None
                ),
                location_type=stop.location_type,
                wheelchair_boarding=stop.wheelchair_boarding,
                platform_code=stop.platform_code,
                timezone=stop.timezone,
            )
        )
    except HTTPException:
        raise
    except (OperationalError, DBAPIError, TimeoutError, OSError) as exc:
        logger.warning("Database unavailable in get_stop: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable",
        ) from exc


@router.get(
    "/feeds/{feed_slug}/stops/{stop_id}/arrivals",
    response_model=ItemEnvelope[list[StopArrivalPrediction]],
    summary="Get estimated arrival predictions for a stop",
)
async def get_stop_arrivals(
    feed_slug: Annotated[
        str,
        Path(
            min_length=1,
            max_length=64,
            pattern=r"^[a-zA-Z0-9_-]+$",
            description="Feed slug or numeric ID identifier",
        ),
    ],
    stop_id: Annotated[
        str,
        Path(
            min_length=1,
            max_length=255,
            description="GTFS stop identifier",
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=50,
            description="Maximum arrival predictions to return (default 10, max 50)",
        ),
    ] = 10,
    reference_time: Annotated[
        datetime | None,
        Query(
            description=(
                "Evaluation reference timestamp in ISO 8601 (defaults to current time)"
            ),
        ),
    ] = None,
) -> ItemEnvelope[list[StopArrivalPrediction]]:
    """Predict upcoming stop arrivals using live vehicle positions and GTFS."""
    try:
        feed = await _get_feed_by_slug(session, feed_slug)
        service = ArrivalPredictionService()
        predictions = await service.predict_arrivals_for_stop(
            session=session,
            feed=feed,
            stop_id=stop_id,
            limit=limit,
            reference_time=reference_time,
        )
        return ItemEnvelope(data=predictions)
    except HTTPException:
        raise
    except (OperationalError, DBAPIError, TimeoutError, OSError) as exc:
        logger.warning(
            "Database unavailable in get_stop_arrivals: %s", type(exc).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable",
        ) from exc


# ---------------------------------------------------------------------------
# Trip Planning Endpoints (Stage 5, Slice 5.1)
# ---------------------------------------------------------------------------


def _get_current_utc() -> datetime:
    """Return the current UTC instant."""
    return datetime.now(UTC)


def _time_str_to_seconds(t_str: str) -> int:
    """Convert HH:MM or HH:MM:SS string to total seconds from start of service day."""
    parts = t_str.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 3600 + int(parts[1]) * 60
    return 0


def _seconds_to_time_str(total_seconds: int) -> str:
    """Format total seconds to HH:MM:SS string (preserving GTFS hours >= 24)."""
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _add_delay_to_time(base_time_str: str, delay_seconds: int | None) -> str:
    """Add delay in seconds to a base HH:MM:SS string."""
    if delay_seconds is None or delay_seconds == 0:
        return base_time_str
    base_sec = _time_str_to_seconds(base_time_str)
    return _seconds_to_time_str(max(0, base_sec + delay_seconds))


async def _get_active_service_ids_for_date(
    session: AsyncSession,
    feed_id: int,
    target_date: datetime_date,
) -> set[str] | None:
    """Return active service IDs for feed on date, or None if no calendar exists."""
    has_cal = await session.execute(
        select(Calendar.id).where(Calendar.feed_id == feed_id).limit(1)
    )
    has_cal_date = await session.execute(
        select(CalendarDate.id).where(CalendarDate.feed_id == feed_id).limit(1)
    )
    if (
        has_cal.scalar_one_or_none() is None
        and has_cal_date.scalar_one_or_none() is None
    ):
        return None  # Unconfigured calendar: all trips treated as active

    day_col_name = target_date.strftime("%A").lower()  # "monday", "tuesday", etc.
    day_col = getattr(Calendar, day_col_name, None)

    active_services: set[str] = set()
    if day_col is not None:
        cal_stmt = select(Calendar.service_id).where(
            Calendar.feed_id == feed_id,
            Calendar.start_date <= target_date,
            Calendar.end_date >= target_date,
            day_col.is_(True),
        )
        cal_res = await session.execute(cal_stmt)
        active_services.update(cal_res.scalars().all())

    # Apply CalendarDate exceptions: 1=added service, 2=removed service
    cd_stmt = select(CalendarDate.service_id, CalendarDate.exception_type).where(
        CalendarDate.feed_id == feed_id,
        CalendarDate.date == target_date,
    )
    cd_res = await session.execute(cd_stmt)
    for service_id, exc_type in cd_res.all():
        if exc_type == 1:
            active_services.add(service_id)
        elif exc_type == 2:
            active_services.discard(service_id)

    return active_services


@router.get(
    "/feeds/{feed_slug}/plan",
    response_model=ItemEnvelope[TripPlanResponse],
    summary="Plan direct transit trips between two stops within a feed",
)
async def plan_trip(
    feed_slug: Annotated[
        str,
        Path(
            min_length=1,
            max_length=64,
            pattern=r"^[a-zA-Z0-9_-]+$",
            description="Feed slug identifier",
        ),
    ],
    origin_stop_id: Annotated[
        str,
        Query(
            min_length=1,
            max_length=255,
            description="Origin GTFS stop identifier",
        ),
    ],
    destination_stop_id: Annotated[
        str,
        Query(
            min_length=1,
            max_length=255,
            description="Destination GTFS stop identifier",
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    date: Annotated[
        datetime_date | None,
        Query(
            description=(
                "Travel date in YYYY-MM-DD format "
                "(defaults to current agency local date)"
            )
        ),
    ] = None,
    time: Annotated[
        str | None,
        Query(
            pattern=r"^\d{1,2}:\d{2}(:\d{2})?$",
            description=(
                "Earliest departure time in HH:MM or HH:MM:SS format "
                "(defaults to current agency local time)"
            ),
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=20,
            description="Maximum number of itineraries to return (default 5, max 20)",
        ),
    ] = 5,
) -> ItemEnvelope[TripPlanResponse]:
    """Plan direct scheduled transit trips between an origin and destination stop.

    Returns ordered itineraries departing on or after the specified departure time,
    annotated with route summary, intermediate stop counts, scheduled times, and
    live GTFS-Realtime TripUpdate delay estimates when available.
    """
    try:
        feed = await _get_feed_by_slug(session, feed_slug)
        clean_origin = origin_stop_id.strip()
        clean_dest = destination_stop_id.strip()

        if clean_origin == clean_dest:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Origin and destination stops must be different",
            )

        # Verify origin stop exists in feed
        origin_res = await session.execute(
            select(Stop).where(Stop.feed_id == feed.id, Stop.stop_id == clean_origin)
        )
        origin_stop = origin_res.scalar_one_or_none()
        if origin_stop is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Origin stop '{clean_origin}' not found in feed '{feed_slug}'",
            )

        # Verify destination stop exists in feed
        dest_res = await session.execute(
            select(Stop).where(Stop.feed_id == feed.id, Stop.stop_id == clean_dest)
        )
        dest_stop = dest_res.scalar_one_or_none()
        if dest_stop is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Destination stop '{clean_dest}' not found in feed '{feed_slug}'"
                ),
            )

        # Resolve feed local timezone for default date/time derivation
        agency_stmt = select(Agency.timezone).where(Agency.feed_id == feed.id).limit(1)
        agency_tz_str = (await session.execute(agency_stmt)).scalar_one_or_none()
        feed_tz = resolve_feed_timezone(agency_tz_str, origin_stop.timezone)

        # Capture one current UTC instant and convert to feed local time
        now_utc = _get_current_utc()
        local_now = now_utc.astimezone(feed_tz)

        target_date = date if date is not None else local_now.date()

        # Normalize target time to HH:MM:SS
        if time:
            clean_time = time.strip()
            parts = clean_time.split(":")
            h = int(parts[0])
            m = int(parts[1])
            s = int(parts[2]) if len(parts) > 2 else 0
            target_time = f"{h:02d}:{m:02d}:{s:02d}"
        else:
            target_time = local_now.strftime("%H:%M:%S")

        # Resolve active service IDs for target date
        active_service_ids = await _get_active_service_ids_for_date(
            session, feed.id, target_date
        )
        if active_service_ids is not None and not active_service_ids:
            return ItemEnvelope(
                data=TripPlanResponse(
                    feed_slug=feed.slug,
                    origin_stop_id=clean_origin,
                    destination_stop_id=clean_dest,
                    target_date=target_date.isoformat(),
                    target_time=target_time,
                    itineraries=[],
                )
            )

        # Join StopTime for origin and destination on same trip
        st_origin = aliased(StopTime)
        st_dest = aliased(StopTime)

        query = (
            select(
                Trip,
                Route,
                st_origin.stop_sequence.label("origin_seq"),
                st_origin.departure_time.label("origin_dep_time"),
                st_dest.stop_sequence.label("dest_seq"),
                st_dest.arrival_time.label("dest_arr_time"),
            )
            .join(
                st_origin,
                (st_origin.trip_id == Trip.id) & (st_origin.feed_id == feed.id),
            )
            .join(st_dest, (st_dest.trip_id == Trip.id) & (st_dest.feed_id == feed.id))
            .join(Route, (Route.id == Trip.route_id) & (Route.feed_id == feed.id))
            .where(
                Trip.feed_id == feed.id,
                st_origin.stop_id == origin_stop.id,
                st_dest.stop_id == dest_stop.id,
                st_origin.stop_sequence < st_dest.stop_sequence,
                st_origin.departure_time >= target_time,
            )
        )

        if active_service_ids is not None:
            query = query.where(Trip.service_id.in_(active_service_ids))

        query = query.order_by(st_origin.departure_time.asc()).limit(limit)
        trip_rows = (await session.execute(query)).all()

        if not trip_rows:
            return ItemEnvelope(
                data=TripPlanResponse(
                    feed_slug=feed.slug,
                    origin_stop_id=clean_origin,
                    destination_stop_id=clean_dest,
                    target_date=target_date.isoformat(),
                    target_time=target_time,
                    itineraries=[],
                )
            )

        # Batch lookup any real-time TripUpdates for matching trips
        matching_trip_ids = [row.Trip.trip_id for row in trip_rows]
        tu_stmt = select(TripUpdate).where(
            TripUpdate.feed_id == feed.id,
            TripUpdate.trip_id.in_(matching_trip_ids),
        )
        tu_res = await session.execute(tu_stmt)
        all_trip_updates = tu_res.scalars().all()

        tu_by_trip: dict[str, list[TripUpdate]] = defaultdict(list)
        for tu in all_trip_updates:
            tu_by_trip[tu.trip_id].append(tu)

        itineraries: list[TripItineraryResponse] = []
        for row in trip_rows:
            trip_obj = row.Trip
            route_obj = row.Route
            origin_seq = row.origin_seq
            origin_dep_time = row.origin_dep_time
            dest_seq = row.dest_seq
            dest_arr_time = row.dest_arr_time

            # Check for live trip updates matching origin stop or trip
            trip_tus = tu_by_trip.get(trip_obj.trip_id, [])
            origin_delay: int | None = None
            dest_delay: int | None = None

            for tu in trip_tus:
                if tu.stop_id == clean_origin:
                    origin_delay = tu.departure_delay or tu.arrival_delay
                elif tu.stop_id == clean_dest:
                    dest_delay = tu.arrival_delay or tu.departure_delay

            if origin_delay is None and trip_tus:
                for tu in trip_tus:
                    if tu.stop_id is None and (tu.departure_delay or tu.arrival_delay):
                        origin_delay = tu.departure_delay or tu.arrival_delay
                        break

            if dest_delay is None:
                dest_delay = origin_delay

            if origin_delay is not None:
                if origin_delay > 60:
                    realtime_status = "REALTIME_DELAYED"
                elif origin_delay < -60:
                    realtime_status = "REALTIME_EARLY"
                else:
                    realtime_status = "REALTIME_ON_TIME"
            else:
                realtime_status = "SCHEDULED"

            origin_dep_sec = _time_str_to_seconds(origin_dep_time)
            dest_arr_sec = _time_str_to_seconds(dest_arr_time)

            if origin_delay:
                origin_dep_sec += origin_delay
            if dest_delay:
                dest_arr_sec += dest_delay

            duration_min = max(1, (dest_arr_sec - origin_dep_sec) // 60)
            intermediate_count = max(0, dest_seq - origin_seq - 1)

            origin_detail = StopPlanDetailResponse(
                stop_id=origin_stop.stop_id,
                name=origin_stop.name,
                latitude=origin_stop.latitude,
                longitude=origin_stop.longitude,
                stop_sequence=origin_seq,
                scheduled_time=origin_dep_time,
                estimated_time=_add_delay_to_time(origin_dep_time, origin_delay),
                delay_seconds=origin_delay,
            )

            dest_detail = StopPlanDetailResponse(
                stop_id=dest_stop.stop_id,
                name=dest_stop.name,
                latitude=dest_stop.latitude,
                longitude=dest_stop.longitude,
                stop_sequence=dest_seq,
                scheduled_time=dest_arr_time,
                estimated_time=_add_delay_to_time(dest_arr_time, dest_delay),
                delay_seconds=dest_delay,
            )

            itinerary = TripItineraryResponse(
                route_id=route_obj.route_id,
                route_short_name=route_obj.short_name,
                route_long_name=route_obj.long_name,
                route_color=route_obj.route_color,
                text_color=route_obj.text_color,
                route_type=route_obj.route_type,
                trip_id=trip_obj.trip_id,
                trip_headsign=trip_obj.trip_headsign,
                direction_id=trip_obj.direction_id,
                origin=origin_detail,
                destination=dest_detail,
                duration_minutes=duration_min,
                intermediate_stops_count=intermediate_count,
                realtime_status=realtime_status,
            )
            itineraries.append(itinerary)

        return ItemEnvelope(
            data=TripPlanResponse(
                feed_slug=feed.slug,
                origin_stop_id=clean_origin,
                destination_stop_id=clean_dest,
                target_date=target_date.isoformat(),
                target_time=target_time,
                itineraries=itineraries,
            )
        )
    except HTTPException:
        raise
    except (OperationalError, DBAPIError, TimeoutError, OSError) as exc:
        logger.warning("Database unavailable in plan_trip: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is temporarily unavailable",
        ) from exc
