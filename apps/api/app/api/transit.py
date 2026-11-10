"""WaitWatch API — Transit route, stop, and feed exploration endpoints."""

import logging
import math
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_MakePoint, ST_SetSRID
from sqlalchemy import cast, func, or_, select
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database.session import get_session
from app.models import Agency, Route, Stop, TransitFeed
from app.schemas.transit import (
    FeedDetailResponse,
    FeedSummaryResponse,
    ItemEnvelope,
    NearbyStopResponse,
    PaginatedResponse,
    PaginationMeta,
    RouteDetailResponse,
    RouteResponse,
    StopArrivalPrediction,
    StopDetailResponse,
    StopResponse,
)
from app.services.prediction import ArrivalPredictionService

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
