"""Tests for WaitWatch Transit Query API and Route/Stop exploration endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.session import Base, get_session
from app.main import app
from app.models import Agency, Route, Stop, TransitFeed


@pytest.fixture
async def test_db():
    """Create an isolated in-memory async SQLite engine with test fixtures."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Seed test data for two isolated feeds
    async with session_maker() as session:
        # Feed 1: Metro City (with agencies, routes, stops)
        feed1 = TransitFeed(
            city_name="Metro City",
            slug="metro-city",
            static_gtfs_url="https://metro.example.com/gtfs.zip",
            feed_status="active",
            is_live_tracking_enabled=True,
        )
        session.add(feed1)
        await session.flush()

        agency1 = Agency(
            feed_id=feed1.id,
            agency_id="METRO_BUS",
            name="Metro Bus Authority",
            url="https://metrobus.example.com",
            timezone="America/New_York",
        )
        agency2 = Agency(
            feed_id=feed1.id,
            agency_id="METRO_RAIL",
            name="Metro Commuter Rail",
            url="https://metrorail.example.com",
            timezone="America/New_York",
        )
        session.add_all([agency1, agency2])
        await session.flush()

        route1 = Route(
            feed_id=feed1.id,
            agency_id=agency1.id,
            route_id="B101",
            short_name="101",
            long_name="Crosstown Express",
            description="East-West cross-city express bus",
            route_type=3,  # Bus
            route_color="#0055A5",
            text_color="#FFFFFF",
            sort_order=1,
        )
        route2 = Route(
            feed_id=feed1.id,
            agency_id=agency2.id,
            route_id="R_RED",
            short_name="Red",
            long_name="Red Line Subway",
            description="North-South high capacity subway",
            route_type=1,  # Subway
            route_color="#E31837",
            text_color="#FFFFFF",
            sort_order=2,
        )
        session.add_all([route1, route2])
        await session.flush()

        # Station and child platforms
        station = Stop(
            feed_id=feed1.id,
            stop_id="CENTRAL_STATION",
            code="CEN",
            name="Central Transit Center",
            description="Main interchange terminal",
            latitude=40.7128,
            longitude=-74.0060,
            location_type=1,  # Station
        )
        session.add(station)
        await session.flush()

        platform1 = Stop(
            feed_id=feed1.id,
            stop_id="PLATFORM_1",
            code="P1",
            name="Platform 1 - Northbound",
            latitude=40.7130,
            longitude=-74.0062,
            parent_station_id=station.id,
            location_type=0,  # Stop / platform
            platform_code="1",
        )
        # Distant stop (~5km north)
        distant_stop = Stop(
            feed_id=feed1.id,
            stop_id="UPTOWN_STOP",
            code="UPT",
            name="Uptown Station",
            latitude=40.7589,
            longitude=-73.9851,
            location_type=0,
        )
        session.add_all([platform1, distant_stop])

        # Feed 2: Isolated empty feed
        feed2 = TransitFeed(
            city_name="Empty Town",
            slug="empty-town",
            static_gtfs_url="https://empty.example.com/gtfs.zip",
            feed_status="inactive",
            is_live_tracking_enabled=False,
        )
        session.add(feed2)
        await session.commit()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield session_maker
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def api_client(test_db):
    """Async HTTP test client with database dependency override."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# 1. Feeds Exploration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_feeds(api_client: AsyncClient) -> None:
    """Verify listing all configured transit feeds."""
    response = await api_client.get("/api/v1/feeds")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    slugs = {f["slug"] for f in data["data"]}
    assert "metro-city" in slugs
    assert "empty-town" in slugs


@pytest.mark.asyncio
async def test_get_feed_detail(api_client: AsyncClient) -> None:
    """Verify retrieving detailed configuration for a valid feed slug."""
    response = await api_client.get("/api/v1/feeds/metro-city")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["city_name"] == "Metro City"
    assert data["slug"] == "metro-city"
    assert data["static_gtfs_url"] == "https://metro.example.com/gtfs.zip"
    assert data["is_live_tracking_enabled"] is True


@pytest.mark.asyncio
async def test_get_feed_not_found(api_client: AsyncClient) -> None:
    """Verify 404 response for unknown feed slug."""
    response = await api_client.get("/api/v1/feeds/non-existent-city")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 2. Routes Exploration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_routes_pagination_envelope(api_client: AsyncClient) -> None:
    """Verify standard response envelope and pagination metadata on route list."""
    response = await api_client.get(
        "/api/v1/feeds/metro-city/routes?page=1&page_size=1"
    )
    assert response.status_code == 200
    res = response.json()
    assert "data" in res
    assert "pagination" in res

    pagination = res["pagination"]
    assert pagination["total"] == 2
    assert pagination["page"] == 1
    assert pagination["page_size"] == 1
    assert pagination["total_pages"] == 2
    assert pagination["has_next"] is True
    assert pagination["has_prev"] is False
    assert len(res["data"]) == 1


@pytest.mark.asyncio
async def test_list_routes_feed_isolation(api_client: AsyncClient) -> None:
    """Verify routes are strictly isolated by feed slug."""
    # Feed 2 has no routes
    response = await api_client.get("/api/v1/feeds/empty-town/routes")
    assert response.status_code == 200
    res = response.json()
    assert res["data"] == []
    assert res["pagination"]["total"] == 0
    assert res["pagination"]["total_pages"] == 0


@pytest.mark.asyncio
async def test_list_routes_search_query(api_client: AsyncClient) -> None:
    """Verify text search matches route names and descriptions case-insensitively."""
    # Search for 'subway' in description
    response = await api_client.get("/api/v1/feeds/metro-city/routes?q=subway")
    assert response.status_code == 200
    res = response.json()
    assert len(res["data"]) == 1
    assert res["data"][0]["route_id"] == "R_RED"

    # Search for '101' in short_name
    response = await api_client.get("/api/v1/feeds/metro-city/routes?q=101")
    assert response.status_code == 200
    res = response.json()
    assert len(res["data"]) == 1
    assert res["data"][0]["route_id"] == "B101"


@pytest.mark.asyncio
async def test_list_routes_filters(api_client: AsyncClient) -> None:
    """Verify filtering by route_type and agency_id."""
    # Filter bus (route_type=3)
    resp_bus = await api_client.get("/api/v1/feeds/metro-city/routes?route_type=3")
    assert resp_bus.status_code == 200
    assert len(resp_bus.json()["data"]) == 1
    assert resp_bus.json()["data"][0]["route_id"] == "B101"

    # Filter agency_id
    resp_rail = await api_client.get(
        "/api/v1/feeds/metro-city/routes?agency_id=METRO_RAIL"
    )
    assert resp_rail.status_code == 200
    assert len(resp_rail.json()["data"]) == 1
    assert resp_rail.json()["data"][0]["route_id"] == "R_RED"


@pytest.mark.asyncio
async def test_get_route_detail_success(api_client: AsyncClient) -> None:
    """Verify retrieving detailed route metadata with agency information."""
    response = await api_client.get("/api/v1/feeds/metro-city/routes/B101")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["route_id"] == "B101"
    assert data["agency_id"] == "METRO_BUS"
    assert data["agency_name"] == "Metro Bus Authority"
    assert data["agency_timezone"] == "America/New_York"
    assert data["short_name"] == "101"
    assert data["route_type"] == 3


@pytest.mark.asyncio
async def test_get_route_detail_not_found(api_client: AsyncClient) -> None:
    """Verify 404 when querying an unknown route."""
    response = await api_client.get("/api/v1/feeds/metro-city/routes/NONEXISTENT")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 3. Stops Exploration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_stops_pagination(api_client: AsyncClient) -> None:
    """Verify stop list pagination envelope."""
    response = await api_client.get("/api/v1/feeds/metro-city/stops?page=1&page_size=2")
    assert response.status_code == 200
    res = response.json()
    assert len(res["data"]) == 2
    assert res["pagination"]["total"] == 3
    assert res["pagination"]["total_pages"] == 2
    assert res["pagination"]["has_next"] is True


@pytest.mark.asyncio
async def test_list_stops_search(api_client: AsyncClient) -> None:
    """Verify stop text search by name and code."""
    response = await api_client.get("/api/v1/feeds/metro-city/stops?q=central")
    assert response.status_code == 200
    res = response.json()
    assert len(res["data"]) == 1
    assert res["data"][0]["stop_id"] == "CENTRAL_STATION"


@pytest.mark.asyncio
async def test_get_stop_detail_with_parent_station(api_client: AsyncClient) -> None:
    """Verify stop detail includes GTFS parent station stop_id."""
    response = await api_client.get("/api/v1/feeds/metro-city/stops/PLATFORM_1")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["stop_id"] == "PLATFORM_1"
    assert data["parent_station_id"] == "CENTRAL_STATION"
    assert data["platform_code"] == "1"


@pytest.mark.asyncio
async def test_get_stop_not_found(api_client: AsyncClient) -> None:
    """Verify 404 when querying an unknown stop."""
    response = await api_client.get("/api/v1/feeds/metro-city/stops/NONEXISTENT")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 4. Nearby Stops Exploration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_nearby_stops_sorted_by_distance(api_client: AsyncClient) -> None:
    """Verify nearby stops returns stops within radius sorted by distance."""
    # Search around Central Station (lat: 40.7128, lon: -74.0060) with radius 500m
    response = await api_client.get(
        "/api/v1/feeds/metro-city/stops/nearby"
        "?latitude=40.7128&longitude=-74.0060&radius_meters=500"
    )
    assert response.status_code == 200
    res = response.json()
    assert "data" in res
    stops = res["data"]
    # Should include CENTRAL_STATION and PLATFORM_1 (~27m away),
    # but NOT UPTOWN_STOP (~5km away)
    assert len(stops) == 2
    assert stops[0]["stop_id"] == "CENTRAL_STATION"
    assert stops[0]["distance_meters"] < 10.0
    assert stops[1]["stop_id"] == "PLATFORM_1"
    # Ordered ascending by distance
    assert stops[0]["distance_meters"] <= stops[1]["distance_meters"]


@pytest.mark.asyncio
async def test_get_nearby_stops_validation_errors(api_client: AsyncClient) -> None:
    """Verify validation errors for out-of-range latitude, longitude, and radius."""
    # Latitude > 90
    resp_bad_lat = await api_client.get(
        "/api/v1/feeds/metro-city/stops/nearby?latitude=95.0&longitude=0.0"
    )
    assert resp_bad_lat.status_code == 422

    # Longitude < -180
    resp_bad_lon = await api_client.get(
        "/api/v1/feeds/metro-city/stops/nearby?latitude=0.0&longitude=-185.0"
    )
    assert resp_bad_lon.status_code == 422

    # Radius > 50,000m
    resp_bad_radius = await api_client.get(
        "/api/v1/feeds/metro-city/stops/nearby?latitude=40.7&longitude=-74.0&radius_meters=60000"
    )
    assert resp_bad_radius.status_code == 422


# ---------------------------------------------------------------------------
# 5. Database Unavailable (503) & Path Compatibility Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_database_unavailable_returns_sanitized_503() -> None:
    """Verify that database errors return a clean 503 without leaking credentials."""

    async def failing_session():
        if False:
            yield
        raise OperationalError(
            "statement",
            {},
            Exception("FATAL: password authentication failed for user 'secret_user'"),
        )

    app.dependency_overrides[get_session] = failing_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/feeds/metro-city/routes")
            assert response.status_code == 503
            data = response.json()
            assert data["detail"] == "Database service is temporarily unavailable"
            assert "secret_user" not in response.text
            assert "password" not in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_backwards_compatible_unprefixed_routes(api_client: AsyncClient) -> None:
    """Verify routes are accessible via both /api/v1/feeds and /api/feeds."""
    response = await api_client.get("/api/feeds/metro-city/routes")
    assert response.status_code == 200
    assert len(response.json()["data"]) == 2
