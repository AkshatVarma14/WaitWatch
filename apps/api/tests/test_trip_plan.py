"""Unit and integration tests for direct stop-to-stop trip planning (Slice 5.1)."""

from collections.abc import AsyncGenerator
from datetime import date
from unittest.mock import patch

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
from app.models import (
    Agency,
    Calendar,
    Route,
    Stop,
    StopTime,
    TransitFeed,
    Trip,
    TripUpdate,
)


@pytest.fixture
async def trip_plan_db() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Isolated SQLite test database populated with transit feed and direct trips."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_maker() as session:
        feed = TransitFeed(
            city_name="Planville",
            slug="planville",
            static_gtfs_url="https://example.com/gtfs.zip",
            feed_status="active",
            is_live_tracking_enabled=True,
        )
        session.add(feed)
        await session.flush()

        agency = Agency(
            feed_id=feed.id,
            agency_id="AGENCY_1",
            name="Planville Transit",
            url="https://example.com",
            timezone="UTC",
        )
        session.add(agency)
        await session.flush()

        route = Route(
            feed_id=feed.id,
            agency_id=agency.id,
            route_id="ROUTE_10",
            short_name="10",
            long_name="Crosstown Express",
            route_type=3,
            route_color="0055A5",
            text_color="FFFFFF",
        )
        session.add(route)
        await session.flush()

        # Stops along Route 10: Stop A -> Stop B -> Stop C
        stop_a = Stop(
            feed_id=feed.id,
            stop_id="STOP_A",
            name="Alpha Station",
            latitude=40.7128,
            longitude=-74.0060,
        )
        stop_b = Stop(
            feed_id=feed.id,
            stop_id="STOP_B",
            name="Bravo Central",
            latitude=40.7200,
            longitude=-73.9950,
        )
        stop_c = Stop(
            feed_id=feed.id,
            stop_id="STOP_C",
            name="Charlie Terminal",
            latitude=40.7300,
            longitude=-73.9850,
        )
        # Unrelated stop
        stop_d = Stop(
            feed_id=feed.id,
            stop_id="STOP_D",
            name="Delta Depot",
            latitude=40.7400,
            longitude=-73.9750,
        )
        session.add_all([stop_a, stop_b, stop_c, stop_d])
        await session.flush()

        # Calendar: Active on Mondays (2026-11-09 was a Monday)
        calendar = Calendar(
            feed_id=feed.id,
            service_id="SERVICE_WEEKDAY",
            monday=True,
            tuesday=True,
            wednesday=True,
            thursday=True,
            friday=True,
            saturday=False,
            sunday=False,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        session.add(calendar)
        await session.flush()

        # Trip 1: Morning Trip at 08:00 (A -> B -> C)
        trip_morning = Trip(
            feed_id=feed.id,
            route_id=route.id,
            service_id="SERVICE_WEEKDAY",
            trip_id="TRIP_MORNING",
            trip_headsign="Charlie Terminal",
            direction_id=0,
        )
        # Trip 2: Midday Trip at 12:00 (A -> B -> C)
        trip_midday = Trip(
            feed_id=feed.id,
            route_id=route.id,
            service_id="SERVICE_WEEKDAY",
            trip_id="TRIP_MIDDAY",
            trip_headsign="Charlie Terminal",
            direction_id=0,
        )
        # Trip 3: Reverse Trip at 12:30 (C -> B -> A)
        trip_reverse = Trip(
            feed_id=feed.id,
            route_id=route.id,
            service_id="SERVICE_WEEKDAY",
            trip_id="TRIP_REVERSE",
            trip_headsign="Alpha Station",
            direction_id=1,
        )
        session.add_all([trip_morning, trip_midday, trip_reverse])
        await session.flush()

        # Stop times for Trip 1 (08:00 A, 08:15 B, 08:30 C)
        st1_a = StopTime(
            feed_id=feed.id,
            trip_id=trip_morning.id,
            stop_id=stop_a.id,
            stop_sequence=1,
            arrival_time="08:00:00",
            departure_time="08:00:00",
        )
        st1_b = StopTime(
            feed_id=feed.id,
            trip_id=trip_morning.id,
            stop_id=stop_b.id,
            stop_sequence=2,
            arrival_time="08:15:00",
            departure_time="08:15:00",
        )
        st1_c = StopTime(
            feed_id=feed.id,
            trip_id=trip_morning.id,
            stop_id=stop_c.id,
            stop_sequence=3,
            arrival_time="08:30:00",
            departure_time="08:30:00",
        )

        # Stop times for Trip 2 (12:00 A, 12:15 B, 12:30 C)
        st2_a = StopTime(
            feed_id=feed.id,
            trip_id=trip_midday.id,
            stop_id=stop_a.id,
            stop_sequence=1,
            arrival_time="12:00:00",
            departure_time="12:00:00",
        )
        st2_b = StopTime(
            feed_id=feed.id,
            trip_id=trip_midday.id,
            stop_id=stop_b.id,
            stop_sequence=2,
            arrival_time="12:15:00",
            departure_time="12:15:00",
        )
        st2_c = StopTime(
            feed_id=feed.id,
            trip_id=trip_midday.id,
            stop_id=stop_c.id,
            stop_sequence=3,
            arrival_time="12:30:00",
            departure_time="12:30:00",
        )

        # Stop times for Trip 3 (Reverse: 12:30 C, 12:45 B, 13:00 A)
        st3_c = StopTime(
            feed_id=feed.id,
            trip_id=trip_reverse.id,
            stop_id=stop_c.id,
            stop_sequence=1,
            arrival_time="12:30:00",
            departure_time="12:30:00",
        )
        st3_b = StopTime(
            feed_id=feed.id,
            trip_id=trip_reverse.id,
            stop_id=stop_b.id,
            stop_sequence=2,
            arrival_time="12:45:00",
            departure_time="12:45:00",
        )
        st3_a = StopTime(
            feed_id=feed.id,
            trip_id=trip_reverse.id,
            stop_id=stop_a.id,
            stop_sequence=3,
            arrival_time="13:00:00",
            departure_time="13:00:00",
        )

        session.add_all([st1_a, st1_b, st1_c, st2_a, st2_b, st2_c, st3_c, st3_b, st3_a])
        await session.commit()

    yield session_maker
    await engine.dispose()


@pytest.fixture
async def client(
    trip_plan_db: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    """Test HTTP client with database dependency override."""

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with trip_plan_db() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_plan_trip_unknown_feed_returns_404(client: AsyncClient):
    """Ensure non-existent feed slug returns 404."""
    resp = await client.get(
        "/api/v1/feeds/nonexistent-feed/plan",
        params={"origin_stop_id": "STOP_A", "destination_stop_id": "STOP_C"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_plan_trip_same_origin_and_destination_returns_400(client: AsyncClient):
    """Ensure choosing identical origin and destination returns 400."""
    resp = await client.get(
        "/api/v1/feeds/planville/plan",
        params={"origin_stop_id": "STOP_A", "destination_stop_id": "STOP_A"},
    )
    assert resp.status_code == 400
    assert "must be different" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_plan_trip_unknown_origin_stop_returns_404(client: AsyncClient):
    """Ensure missing origin stop returns 404."""
    resp = await client.get(
        "/api/v1/feeds/planville/plan",
        params={"origin_stop_id": "UNKNOWN_STOP", "destination_stop_id": "STOP_C"},
    )
    assert resp.status_code == 404
    assert "origin stop 'unknown_stop' not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_plan_trip_unknown_destination_stop_returns_404(client: AsyncClient):
    """Ensure missing destination stop returns 404."""
    resp = await client.get(
        "/api/v1/feeds/planville/plan",
        params={"origin_stop_id": "STOP_A", "destination_stop_id": "UNKNOWN_DEST"},
    )
    assert resp.status_code == 404
    assert "destination stop 'unknown_dest' not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_plan_trip_direct_itineraries_success(client: AsyncClient):
    """Test successful stop-to-stop direct trip planning."""
    # Travel on Monday 2026-11-09, departure time 07:30
    resp = await client.get(
        "/api/v1/feeds/planville/plan",
        params={
            "origin_stop_id": "STOP_A",
            "destination_stop_id": "STOP_C",
            "date": "2026-11-09",
            "time": "07:30:00",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["feed_slug"] == "planville"
    assert data["origin_stop_id"] == "STOP_A"
    assert data["destination_stop_id"] == "STOP_C"
    assert data["target_date"] == "2026-11-09"
    assert data["target_time"] == "07:30:00"

    itineraries = data["itineraries"]
    assert len(itineraries) == 2  # TRIP_MORNING (08:00) and TRIP_MIDDAY (12:00)

    # First itinerary is TRIP_MORNING
    first = itineraries[0]
    assert first["route_id"] == "ROUTE_10"
    assert first["route_short_name"] == "10"
    assert first["route_color"] == "0055A5"
    assert first["trip_id"] == "TRIP_MORNING"
    assert first["trip_headsign"] == "Charlie Terminal"

    # Origin details
    assert first["origin"]["stop_id"] == "STOP_A"
    assert first["origin"]["name"] == "Alpha Station"
    assert first["origin"]["scheduled_time"] == "08:00:00"
    assert first["origin"]["estimated_time"] == "08:00:00"
    assert first["origin"]["delay_seconds"] is None

    # Destination details
    assert first["destination"]["stop_id"] == "STOP_C"
    assert first["destination"]["name"] == "Charlie Terminal"
    assert first["destination"]["scheduled_time"] == "08:30:00"

    # Duration and intermediate stops
    assert first["duration_minutes"] == 30
    assert first["intermediate_stops_count"] == 1  # Stop B is between A and C
    assert first["realtime_status"] == "SCHEDULED"


@pytest.mark.asyncio
async def test_plan_trip_reverse_direction_not_included(client: AsyncClient):
    """Test that trips traveling in the opposite direction are not returned."""
    # Query from C to A
    resp = await client.get(
        "/api/v1/feeds/planville/plan",
        params={
            "origin_stop_id": "STOP_C",
            "destination_stop_id": "STOP_A",
            "date": "2026-11-09",
            "time": "12:00:00",
        },
    )
    assert resp.status_code == 200
    itineraries = resp.json()["data"]["itineraries"]
    assert len(itineraries) == 1
    assert itineraries[0]["trip_id"] == "TRIP_REVERSE"
    assert itineraries[0]["origin"]["scheduled_time"] == "12:30:00"
    assert itineraries[0]["destination"]["scheduled_time"] == "13:00:00"


@pytest.mark.asyncio
async def test_plan_trip_departure_time_filter(client: AsyncClient):
    """Test that trips departing prior to target_time are excluded."""
    # Target time 10:00:00 should exclude 08:00:00 morning trip
    resp = await client.get(
        "/api/v1/feeds/planville/plan",
        params={
            "origin_stop_id": "STOP_A",
            "destination_stop_id": "STOP_C",
            "date": "2026-11-09",
            "time": "10:00",  # Tests HH:MM format normalization
        },
    )
    assert resp.status_code == 200
    itineraries = resp.json()["data"]["itineraries"]
    assert len(itineraries) == 1
    assert itineraries[0]["trip_id"] == "TRIP_MIDDAY"
    assert itineraries[0]["origin"]["scheduled_time"] == "12:00:00"


@pytest.mark.asyncio
async def test_plan_trip_with_realtime_delay(
    client: AsyncClient, trip_plan_db: async_sessionmaker[AsyncSession]
):
    """Test that GTFS-RT TripUpdate delay adjusts estimated_time and status."""
    async with trip_plan_db() as session:
        # Ingest a real-time TripUpdate with 180s delay for TRIP_MIDDAY at STOP_A
        tu = TripUpdate(
            feed_id=1,
            entity_id="TU_1",
            trip_id="TRIP_MIDDAY",
            stop_id="STOP_A",
            departure_delay=180,  # 3 minutes late
            arrival_delay=180,
        )
        session.add(tu)
        await session.commit()

    resp = await client.get(
        "/api/v1/feeds/planville/plan",
        params={
            "origin_stop_id": "STOP_A",
            "destination_stop_id": "STOP_C",
            "date": "2026-11-09",
            "time": "11:00:00",
        },
    )
    assert resp.status_code == 200
    itinerary = resp.json()["data"]["itineraries"][0]
    assert itinerary["trip_id"] == "TRIP_MIDDAY"
    assert itinerary["origin"]["scheduled_time"] == "12:00:00"
    assert itinerary["origin"]["estimated_time"] == "12:03:00"
    assert itinerary["origin"]["delay_seconds"] == 180
    assert itinerary["realtime_status"] == "REALTIME_DELAYED"


@pytest.mark.asyncio
async def test_plan_trip_calendar_active_service_filtering(client: AsyncClient):
    """Test that querying on a weekend (Sunday 2026-11-08) returns 0 itineraries."""
    # Sunday has no service configured in calendar
    resp = await client.get(
        "/api/v1/feeds/planville/plan",
        params={
            "origin_stop_id": "STOP_A",
            "destination_stop_id": "STOP_C",
            "date": "2026-11-08",  # Sunday
            "time": "08:00:00",
        },
    )
    assert resp.status_code == 200
    itineraries = resp.json()["data"]["itineraries"]
    assert itineraries == []


@pytest.mark.asyncio
async def test_plan_trip_unconnected_stops_returns_empty_itineraries(
    client: AsyncClient,
):
    """Test querying stops that have no direct trip connection returns empty list."""
    resp = await client.get(
        "/api/v1/feeds/planville/plan",
        params={
            "origin_stop_id": "STOP_A",
            "destination_stop_id": "STOP_D",  # Stop D has no trips
            "date": "2026-11-09",
            "time": "08:00:00",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["itineraries"] == []


@pytest.mark.asyncio
async def test_plan_trip_limit_parameter(client: AsyncClient):
    """Test that the limit parameter restricts returned itineraries."""
    resp = await client.get(
        "/api/v1/feeds/planville/plan",
        params={
            "origin_stop_id": "STOP_A",
            "destination_stop_id": "STOP_C",
            "date": "2026-11-09",
            "time": "07:00:00",
            "limit": 1,
        },
    )
    assert resp.status_code == 200
    itineraries = resp.json()["data"]["itineraries"]
    assert len(itineraries) == 1
    assert itineraries[0]["trip_id"] == "TRIP_MORNING"


@pytest.mark.asyncio
async def test_plan_trip_database_error_returns_503(client: AsyncClient):
    """Test that database connectivity failure returns 503."""
    with patch(
        "app.api.transit.AsyncSession.execute",
        side_effect=OperationalError("Database disconnected", None, Exception()),
    ):
        resp = await client.get(
            "/api/v1/feeds/planville/plan",
            params={"origin_stop_id": "STOP_A", "destination_stop_id": "STOP_C"},
        )
        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"].lower()
