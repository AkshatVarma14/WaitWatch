"""Unit and integration tests for stop arrival predictions (Slice 3.2)."""

from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
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
    CalendarDate,
    Route,
    Stop,
    StopTime,
    TransitFeed,
    Trip,
    VehicleObservation,
    VehiclePosition,
)
from app.services.prediction import (
    parse_gtfs_time_to_seconds,
)


def to_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime to UTC for consistent comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@pytest.fixture
async def arrival_test_db() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Isolated SQLite database fixture populated with GTFS static and realtime data."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Base reference date: Tuesday, Nov 10, 2026
    # Reference evaluation time: 10:20:00 AM EST = 15:20:00 UTC
    async with session_maker() as session:
        feed1 = TransitFeed(
            city_name="Metro City",
            slug="metro-city",
            static_gtfs_url="https://metro.example.com/gtfs.zip",
            feed_status="active",
            is_live_tracking_enabled=True,
        )
        session.add(feed1)
        await session.flush()

        agency = Agency(
            feed_id=feed1.id,
            agency_id="METRO",
            name="Metro Transit",
            url="https://metro.example.com",
            timezone="America/New_York",
        )
        session.add(agency)
        await session.flush()

        route = Route(
            feed_id=feed1.id,
            agency_id=agency.id,
            route_id="R101",
            short_name="101",
            long_name="Main Crosstown",
            route_type=3,
        )
        session.add(route)
        await session.flush()

        # 4 stops along Route 101
        stop_a = Stop(
            feed_id=feed1.id,
            stop_id="STOP_A",
            name="Stop A - Origin",
            latitude=40.71,
            longitude=-74.01,
        )
        stop_b = Stop(
            feed_id=feed1.id,
            stop_id="STOP_B",
            name="Stop B - Midpoint",
            latitude=40.72,
            longitude=-74.02,
        )
        stop_c = Stop(
            feed_id=feed1.id,
            stop_id="STOP_C",
            name="Stop C - Target",
            latitude=40.73,
            longitude=-74.03,
        )
        stop_d = Stop(
            feed_id=feed1.id,
            stop_id="STOP_D",
            name="Stop D - Destination",
            latitude=40.74,
            longitude=-74.04,
        )
        session.add_all([stop_a, stop_b, stop_c, stop_d])
        await session.flush()

        # Service calendars
        # 1. Weekday calendar (Tuesday is weekday=1)
        cal_weekday = Calendar(
            feed_id=feed1.id,
            service_id="cal_weekday",
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
        # 2. Weekend calendar
        cal_weekend = Calendar(
            feed_id=feed1.id,
            service_id="cal_weekend",
            monday=False,
            tuesday=False,
            wednesday=False,
            thursday=False,
            friday=False,
            saturday=True,
            sunday=True,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        # 3. Holiday calendar with exception_type=1 (added on Tuesday 2026-11-10)
        cal_holiday = Calendar(
            feed_id=feed1.id,
            service_id="cal_holiday",
            monday=False,
            tuesday=False,
            wednesday=False,
            thursday=False,
            friday=False,
            saturday=False,
            sunday=False,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        # 4. Cancelled schedule with exception_type=2 (removed on Tuesday 2026-11-10)
        cal_cancelled = Calendar(
            feed_id=feed1.id,
            service_id="cal_cancelled",
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
        session.add_all([cal_weekday, cal_weekend, cal_holiday, cal_cancelled])
        await session.flush()

        cd_holiday = CalendarDate(
            feed_id=feed1.id,
            service_id="cal_holiday",
            date=date(2026, 11, 10),
            exception_type=1,  # Added
        )
        cd_cancelled = CalendarDate(
            feed_id=feed1.id,
            service_id="cal_cancelled",
            date=date(2026, 11, 10),
            exception_type=2,  # Removed
        )
        session.add_all([cd_holiday, cd_cancelled])
        await session.flush()

        # Trips
        # Trip 1: Standard weekday trip passing Stop C at 10:30:00 (15:30:00 UTC)
        trip1 = Trip(
            feed_id=feed1.id,
            route_id=route.id,
            service_id="cal_weekday",
            trip_id="TRIP_1",
            trip_headsign="Destination D",
        )
        # Trip 2: Extended service day trip at 25:15:00
        trip_ext = Trip(
            feed_id=feed1.id,
            route_id=route.id,
            service_id="cal_weekday",
            trip_id="TRIP_EXT",
            trip_headsign="Late Owl",
        )
        # Trip 3: Inactive weekend trip
        trip_weekend = Trip(
            feed_id=feed1.id,
            route_id=route.id,
            service_id="cal_weekend",
            trip_id="TRIP_WEEKEND",
            trip_headsign="Weekend Only",
        )
        # Trip 4: Holiday trip active via exception_type=1
        trip_holiday = Trip(
            feed_id=feed1.id,
            route_id=route.id,
            service_id="cal_holiday",
            trip_id="TRIP_HOLIDAY",
            trip_headsign="Holiday Special",
        )
        # Trip 5: Cancelled trip inactive via exception_type=2
        trip_cancelled = Trip(
            feed_id=feed1.id,
            route_id=route.id,
            service_id="cal_cancelled",
            trip_id="TRIP_CANCELLED",
            trip_headsign="Cancelled Service",
        )
        session.add_all([trip1, trip_ext, trip_weekend, trip_holiday, trip_cancelled])
        await session.flush()

        # Stop times for Trip 1
        st1_a = StopTime(
            feed_id=feed1.id,
            trip_id=trip1.id,
            stop_id=stop_a.id,
            stop_sequence=1,
            arrival_time="10:00:00",
            departure_time="10:00:00",
        )
        st1_b = StopTime(
            feed_id=feed1.id,
            trip_id=trip1.id,
            stop_id=stop_b.id,
            stop_sequence=2,
            arrival_time="10:15:00",
            departure_time="10:15:00",
        )
        st1_c = StopTime(
            feed_id=feed1.id,
            trip_id=trip1.id,
            stop_id=stop_c.id,
            stop_sequence=3,
            arrival_time="10:30:00",
            departure_time="10:30:00",
        )
        st1_d = StopTime(
            feed_id=feed1.id,
            trip_id=trip1.id,
            stop_id=stop_d.id,
            stop_sequence=4,
            arrival_time="10:45:00",
            departure_time="10:45:00",
        )

        # Stop times for Trip Extended (Stop C is sequence 2 at 25:15:00)
        st_ext_a = StopTime(
            feed_id=feed1.id,
            trip_id=trip_ext.id,
            stop_id=stop_a.id,
            stop_sequence=1,
            arrival_time="24:30:00",
            departure_time="24:30:00",
        )
        st_ext_c = StopTime(
            feed_id=feed1.id,
            trip_id=trip_ext.id,
            stop_id=stop_c.id,
            stop_sequence=2,
            arrival_time="25:15:00",
            departure_time="25:15:00",
        )

        # Stop times for Trip Weekend
        st_wk_a = StopTime(
            feed_id=feed1.id,
            trip_id=trip_weekend.id,
            stop_id=stop_a.id,
            stop_sequence=1,
            arrival_time="10:00:00",
            departure_time="10:00:00",
        )
        st_wk_c = StopTime(
            feed_id=feed1.id,
            trip_id=trip_weekend.id,
            stop_id=stop_c.id,
            stop_sequence=2,
            arrival_time="10:30:00",
            departure_time="10:30:00",
        )

        # Stop times for Trip Holiday
        st_hol_a = StopTime(
            feed_id=feed1.id,
            trip_id=trip_holiday.id,
            stop_id=stop_a.id,
            stop_sequence=1,
            arrival_time="11:00:00",
            departure_time="11:00:00",
        )
        st_hol_c = StopTime(
            feed_id=feed1.id,
            trip_id=trip_holiday.id,
            stop_id=stop_c.id,
            stop_sequence=2,
            arrival_time="11:30:00",
            departure_time="11:30:00",
        )

        # Stop times for Trip Cancelled
        st_can_a = StopTime(
            feed_id=feed1.id,
            trip_id=trip_cancelled.id,
            stop_id=stop_a.id,
            stop_sequence=1,
            arrival_time="12:00:00",
            departure_time="12:00:00",
        )
        st_can_c = StopTime(
            feed_id=feed1.id,
            trip_id=trip_cancelled.id,
            stop_id=stop_c.id,
            stop_sequence=2,
            arrival_time="12:30:00",
            departure_time="12:30:00",
        )

        session.add_all(
            [
                st1_a,
                st1_b,
                st1_c,
                st1_d,
                st_ext_a,
                st_ext_c,
                st_wk_a,
                st_wk_c,
                st_hol_a,
                st_hol_c,
                st_can_a,
                st_can_c,
            ]
        )

        # Feed 2: Isolated feed for feed-isolation testing
        feed2 = TransitFeed(
            city_name="Second City",
            slug="second-city",
            static_gtfs_url="https://second.example.com/gtfs.zip",
            feed_status="active",
            is_live_tracking_enabled=True,
        )
        session.add(feed2)
        await session.flush()

        agency2 = Agency(
            feed_id=feed2.id,
            agency_id="SEC_AGENCY",
            name="Second Agency",
            url="https://second.example.com",
            timezone="UTC",
        )
        session.add(agency2)
        await session.flush()

        route2 = Route(
            feed_id=feed2.id,
            agency_id=agency2.id,
            route_id="R2",
            short_name="2",
            route_type=3,
        )
        session.add(route2)
        await session.flush()

        stop_c_feed2 = Stop(
            feed_id=feed2.id,
            stop_id="STOP_C",
            name="Stop C in Second City",
            latitude=10.0,
            longitude=20.0,
        )
        session.add(stop_c_feed2)
        await session.flush()

        cal2 = Calendar(
            feed_id=feed2.id,
            service_id="cal_feed2",
            monday=True,
            tuesday=True,
            wednesday=True,
            thursday=True,
            friday=True,
            saturday=True,
            sunday=True,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        session.add(cal2)
        await session.flush()

        trip2 = Trip(
            feed_id=feed2.id,
            route_id=route2.id,
            service_id="cal_feed2",
            trip_id="TRIP_FEED2",
            trip_headsign="Feed 2 Headsign",
        )
        session.add(trip2)
        await session.flush()

        st2_c = StopTime(
            feed_id=feed2.id,
            trip_id=trip2.id,
            stop_id=stop_c_feed2.id,
            stop_sequence=1,
            arrival_time="10:30:00",
            departure_time="10:30:00",
        )
        session.add(st2_c)

        # Vehicle position for Feed 2
        vp_feed2 = VehiclePosition(
            feed_id=feed2.id,
            entity_id="v_feed2",
            vehicle_id="bus-feed2",
            trip_id="TRIP_FEED2",
            route_id="R2",
            current_stop_sequence=1,
            current_status=1,
            latitude=10.0,
            longitude=20.0,
            vehicle_timestamp=datetime(2026, 11, 10, 15, 18, 0, tzinfo=UTC),
        )
        session.add(vp_feed2)

        await session.commit()

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield session_maker
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def api_client(
    arrival_test_db: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    """Test HTTP client with overridden session dependency."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ---------------------------------------------------------------------------
# 1. Active Service Calendar & Exceptions Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_service_calendar_and_exceptions(
    arrival_test_db: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
) -> None:
    """Verify calendar days and calendar_dates exceptions determine active service."""
    # Reference evaluation time: Tuesday Nov 10, 2026 at 15:20:00 UTC (10:20:00 EST)
    ref_time = datetime(2026, 11, 10, 15, 20, 0, tzinfo=UTC)

    async with arrival_test_db() as session:
        # Seed 4 fresh live vehicles:
        # 1. On TRIP_1 (cal_weekday) -> active on Tuesday
        vp1 = VehiclePosition(
            feed_id=1,
            entity_id="v1",
            vehicle_id="bus-101",
            trip_id="TRIP_1",
            route_id="R101",
            current_stop_sequence=2,  # at Stop B, Stop C (seq 3) is downstream
            current_status=1,  # STOPPED_AT
            latitude=40.72,
            longitude=-74.02,
            vehicle_timestamp=ref_time - timedelta(minutes=2),
        )
        # 2. On TRIP_WEEKEND (cal_weekend) -> inactive on Tuesday
        vp_wk = VehiclePosition(
            feed_id=1,
            entity_id="v_wk",
            vehicle_id="bus-weekend",
            trip_id="TRIP_WEEKEND",
            route_id="R101",
            current_stop_sequence=1,
            current_status=1,
            latitude=40.71,
            longitude=-74.01,
            vehicle_timestamp=ref_time - timedelta(minutes=2),
        )
        # 3. On TRIP_HOLIDAY (cal_holiday + exception_type=1) -> active via exception
        vp_hol = VehiclePosition(
            feed_id=1,
            entity_id="v_hol",
            vehicle_id="bus-holiday",
            trip_id="TRIP_HOLIDAY",
            route_id="R101",
            current_stop_sequence=1,
            current_status=1,
            latitude=40.71,
            longitude=-74.01,
            vehicle_timestamp=ref_time - timedelta(minutes=2),
        )
        # 4. On TRIP_CANCELLED (exception_type=2) -> inactive via exception
        vp_can = VehiclePosition(
            feed_id=1,
            entity_id="v_can",
            vehicle_id="bus-cancelled",
            trip_id="TRIP_CANCELLED",
            route_id="R101",
            current_stop_sequence=1,
            current_status=1,
            latitude=40.71,
            longitude=-74.01,
            vehicle_timestamp=ref_time - timedelta(minutes=2),
        )
        session.add_all([vp1, vp_wk, vp_hol, vp_can])
        await session.commit()

    # Query arrivals at STOP_C
    res = await api_client.get(
        "/api/v1/feeds/metro-city/stops/STOP_C/arrivals",
        params={"reference_time": ref_time.isoformat()},
    )
    assert res.status_code == 200
    data = res.json()["data"]

    returned_trips = {p["trip_id"] for p in data}
    # TRIP_1 and TRIP_HOLIDAY must be included
    assert "TRIP_1" in returned_trips
    assert "TRIP_HOLIDAY" in returned_trips
    # TRIP_WEEKEND and TRIP_CANCELLED must be excluded
    assert "TRIP_WEEKEND" not in returned_trips
    assert "TRIP_CANCELLED" not in returned_trips


# ---------------------------------------------------------------------------
# 2. Extended-Hour Times (>24:00) Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extended_service_day_hours(
    arrival_test_db: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
) -> None:
    """Verify times exceeding 24:00 map accurately to next calendar day."""
    # Service date = 2026-11-10.
    # Scheduled arrival at STOP_C = 25:15:00 (which is 1:15 AM on 2026-11-11 in EST).
    # 2026-11-11 01:15:00 EST = 2026-11-11 06:15:00 UTC.
    ref_time = datetime(2026, 11, 11, 5, 45, 0, tzinfo=UTC)  # 00:45 AM EST on Nov 11

    async with arrival_test_db() as session:
        vp_ext = VehiclePosition(
            feed_id=1,
            entity_id="v_ext",
            vehicle_id="bus-night",
            trip_id="TRIP_EXT",
            route_id="R101",
            current_stop_sequence=1,  # at Stop A, Stop C (seq 2) is downstream
            current_status=1,
            latitude=40.71,
            longitude=-74.01,
            start_date="20261110",  # Service day was Nov 10
            vehicle_timestamp=ref_time - timedelta(minutes=1),
        )
        session.add(vp_ext)
        await session.commit()

    res = await api_client.get(
        "/api/v1/feeds/metro-city/stops/STOP_C/arrivals",
        params={"reference_time": ref_time.isoformat()},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    ext_preds = [p for p in data if p["trip_id"] == "TRIP_EXT"]
    assert len(ext_preds) == 1

    expected_scheduled = datetime(2026, 11, 11, 6, 15, 0, tzinfo=UTC)
    pred_dt = datetime.fromisoformat(ext_preds[0]["scheduled_arrival_time"])
    assert to_utc(pred_dt) == expected_scheduled


# ---------------------------------------------------------------------------
# 3. Downstream Stop Filtering Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_downstream_stop_filtering(
    arrival_test_db: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
) -> None:
    """Verify vehicles past the target stop are excluded while upstream are included."""
    ref_time = datetime(2026, 11, 10, 15, 20, 0, tzinfo=UTC)

    async with arrival_test_db() as session:
        # Vehicle past Stop C: current_stop_sequence = 4 (at Stop D)
        vp_passed = VehiclePosition(
            feed_id=1,
            entity_id="v_passed",
            vehicle_id="bus-passed",
            trip_id="TRIP_1",
            route_id="R101",
            current_stop_sequence=4,
            current_status=1,
            latitude=40.74,
            longitude=-74.04,
            vehicle_timestamp=ref_time - timedelta(minutes=1),
        )
        session.add(vp_passed)
        await session.commit()

    res = await api_client.get(
        "/api/v1/feeds/metro-city/stops/STOP_C/arrivals",
        params={"reference_time": ref_time.isoformat()},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    # Vehicle has passed sequence 3, so no prediction returned
    assert len(data) == 0


# ---------------------------------------------------------------------------
# 4. Stale and Missing Telemetry Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_and_missing_telemetry_skipped(
    arrival_test_db: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
) -> None:
    """Verify telemetry older than max freshness or missing trip/sequence is skipped."""
    ref_time = datetime(2026, 11, 10, 15, 20, 0, tzinfo=UTC)

    async with arrival_test_db() as session:
        # Stale vehicle (timestamp 10 minutes ago > 300s threshold)
        vp_stale = VehiclePosition(
            feed_id=1,
            entity_id="v_stale",
            vehicle_id="bus-stale",
            trip_id="TRIP_1",
            route_id="R101",
            current_stop_sequence=2,
            current_status=1,
            latitude=40.72,
            longitude=-74.02,
            vehicle_timestamp=ref_time - timedelta(minutes=10),
        )
        # Vehicle missing sequence
        vp_no_seq = VehiclePosition(
            feed_id=1,
            entity_id="v_no_seq",
            vehicle_id="bus-no-seq",
            trip_id="TRIP_1",
            route_id="R101",
            current_stop_sequence=None,
            current_status=1,
            latitude=40.72,
            longitude=-74.02,
            vehicle_timestamp=ref_time - timedelta(minutes=1),
        )
        # Vehicle missing trip_id
        vp_no_trip = VehiclePosition(
            feed_id=1,
            entity_id="v_no_trip",
            vehicle_id="bus-no-trip",
            trip_id=None,
            route_id="R101",
            current_stop_sequence=2,
            current_status=1,
            latitude=40.72,
            longitude=-74.02,
            vehicle_timestamp=ref_time - timedelta(minutes=1),
        )
        session.add_all([vp_stale, vp_no_seq, vp_no_trip])
        await session.commit()

    res = await api_client.get(
        "/api/v1/feeds/metro-city/stops/STOP_C/arrivals",
        params={"reference_time": ref_time.isoformat()},
    )
    assert res.status_code == 200
    assert len(res.json()["data"]) == 0


# ---------------------------------------------------------------------------
# 5. History Median Adjustment & Schedule Fallback Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_median_adjustment_and_schedule_only_fallback(
    arrival_test_db: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
) -> None:
    """Verify median delay adjustment with history and schedule fallback otherwise."""
    ref_time = datetime(2026, 11, 10, 15, 20, 0, tzinfo=UTC)

    async with arrival_test_db() as session:
        # Active vehicle at Stop B (seq 2)
        vp = VehiclePosition(
            feed_id=1,
            entity_id="v_adj",
            vehicle_id="bus-adj",
            trip_id="TRIP_1",
            route_id="R101",
            current_stop_sequence=2,
            current_status=1,
            latitude=40.72,
            longitude=-74.02,
            vehicle_timestamp=ref_time - timedelta(seconds=30),
        )
        session.add(vp)
        await session.commit()

    # Case A: Without history -> SCHEDULE_ONLY, delay=0
    res_fallback = await api_client.get(
        "/api/v1/feeds/metro-city/stops/STOP_C/arrivals",
        params={"reference_time": ref_time.isoformat()},
    )
    assert res_fallback.status_code == 200
    fallback_data = res_fallback.json()["data"]
    assert len(fallback_data) == 1
    assert fallback_data[0]["prediction_source"] == "SCHEDULE_ONLY"
    assert fallback_data[0]["delay_seconds"] == 0
    sched_dt = datetime.fromisoformat(fallback_data[0]["scheduled_arrival_time"])
    est_dt = datetime.fromisoformat(fallback_data[0]["estimated_arrival_time"])
    assert sched_dt == est_dt

    # Case B: With 2 historical STOPPED_AT observations:
    # Stop A: scheduled 10:00:00 EST (15:00:00 UTC), observed 15:02:00 UTC (+120s delay)
    # Stop B: scheduled 10:15:00 EST (15:15:00 UTC), observed 15:18:00 UTC (+180s delay)
    # Median delay = (120 + 180) / 2 = 150 seconds
    async with arrival_test_db() as session:
        obs_a = VehicleObservation(
            feed_id=1,
            entity_id="v_adj",
            vehicle_id="bus-adj",
            trip_id="TRIP_1",
            stop_id="STOP_A",
            current_stop_sequence=1,
            current_status=1,  # STOPPED_AT
            latitude=40.71,
            longitude=-74.01,
            observed_at=datetime(2026, 11, 10, 15, 2, 0, tzinfo=UTC),
        )
        obs_b = VehicleObservation(
            feed_id=1,
            entity_id="v_adj",
            vehicle_id="bus-adj",
            trip_id="TRIP_1",
            stop_id="STOP_B",
            current_stop_sequence=2,
            current_status=1,  # STOPPED_AT
            latitude=40.72,
            longitude=-74.02,
            observed_at=datetime(2026, 11, 10, 15, 18, 0, tzinfo=UTC),
        )
        session.add_all([obs_a, obs_b])
        await session.commit()

    res_adj = await api_client.get(
        "/api/v1/feeds/metro-city/stops/STOP_C/arrivals",
        params={"reference_time": ref_time.isoformat()},
    )
    assert res_adj.status_code == 200
    adj_data = res_adj.json()["data"]
    assert len(adj_data) == 1
    assert adj_data[0]["prediction_source"] == "HISTORY_ADJUSTED"
    assert adj_data[0]["delay_seconds"] == 150
    sched_dt = datetime.fromisoformat(adj_data[0]["scheduled_arrival_time"])
    est_dt = datetime.fromisoformat(adj_data[0]["estimated_arrival_time"])
    assert to_utc(est_dt) == to_utc(sched_dt) + timedelta(seconds=150)


# ---------------------------------------------------------------------------
# 6. Feed Isolation Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_isolation(
    arrival_test_db: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
) -> None:
    """Verify predictions strictly stay within the requested feed."""
    ref_time = datetime(2026, 11, 10, 15, 20, 0, tzinfo=UTC)

    # Query metro-city for STOP_C: should not contain Feed 2 (second-city) trip
    res1 = await api_client.get(
        "/api/v1/feeds/metro-city/stops/STOP_C/arrivals",
        params={"reference_time": ref_time.isoformat()},
    )
    assert res1.status_code == 200
    data1 = res1.json()["data"]
    assert all(p["feed_slug"] == "metro-city" for p in data1)
    assert not any(p["trip_id"] == "TRIP_FEED2" for p in data1)

    # Query second-city for STOP_C: should return only Feed 2 trip
    res2 = await api_client.get(
        "/api/v1/feeds/second-city/stops/STOP_C/arrivals",
        params={"reference_time": ref_time.isoformat()},
    )
    assert res2.status_code == 200
    data2 = res2.json()["data"]
    assert len(data2) == 1
    assert data2[0]["feed_slug"] == "second-city"
    assert data2[0]["trip_id"] == "TRIP_FEED2"


# ---------------------------------------------------------------------------
# 7. Bounded Ordering & Limits Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bounded_ordering_and_limits(
    arrival_test_db: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
) -> None:
    """Verify predictions are ordered by estimated arrival and capped by limit."""
    ref_time = datetime(2026, 11, 10, 15, 20, 0, tzinfo=UTC)

    async with arrival_test_db() as session:
        # Add active trip calling at Stop C earlier (10:25:00 EST / 15:25:00 UTC)
        trip_early = Trip(
            feed_id=1,
            route_id=1,
            service_id="cal_weekday",
            trip_id="TRIP_EARLY",
            trip_headsign="Early Arrival",
        )
        session.add(trip_early)
        await session.flush()

        st_early_a = StopTime(
            feed_id=1,
            trip_id=trip_early.id,
            stop_id=1,
            stop_sequence=1,
            arrival_time="10:10:00",
            departure_time="10:10:00",
        )
        st_early_c = StopTime(
            feed_id=1,
            trip_id=trip_early.id,
            stop_id=3,  # STOP_C
            stop_sequence=2,
            arrival_time="10:25:00",
            departure_time="10:25:00",
        )
        session.add_all([st_early_a, st_early_c])

        # Live vehicles for TRIP_1 (sched 15:30) and TRIP_EARLY (sched 15:25)
        vp1 = VehiclePosition(
            feed_id=1,
            entity_id="v1",
            vehicle_id="bus-101",
            trip_id="TRIP_1",
            route_id="R101",
            current_stop_sequence=2,
            current_status=1,
            latitude=40.72,
            longitude=-74.02,
            vehicle_timestamp=ref_time - timedelta(minutes=1),
        )
        vp_early = VehiclePosition(
            feed_id=1,
            entity_id="v_early",
            vehicle_id="bus-early",
            trip_id="TRIP_EARLY",
            route_id="R101",
            current_stop_sequence=1,
            current_status=1,
            latitude=40.71,
            longitude=-74.01,
            vehicle_timestamp=ref_time - timedelta(minutes=1),
        )
        session.add_all([vp1, vp_early])
        await session.commit()

    # Query with limit=1: should return the earliest trip (TRIP_EARLY)
    res_lim1 = await api_client.get(
        "/api/v1/feeds/metro-city/stops/STOP_C/arrivals",
        params={"reference_time": ref_time.isoformat(), "limit": 1},
    )
    assert res_lim1.status_code == 200
    data_lim1 = res_lim1.json()["data"]
    assert len(data_lim1) == 1
    assert data_lim1[0]["trip_id"] == "TRIP_EARLY"

    # Query with limit=10: should return both in ascending order
    res_all = await api_client.get(
        "/api/v1/feeds/metro-city/stops/STOP_C/arrivals",
        params={"reference_time": ref_time.isoformat(), "limit": 10},
    )
    assert res_all.status_code == 200
    data_all = res_all.json()["data"]
    assert len(data_all) == 2
    assert data_all[0]["trip_id"] == "TRIP_EARLY"
    assert data_all[1]["trip_id"] == "TRIP_1"
    assert (
        data_all[0]["estimated_arrival_time"] <= data_all[1]["estimated_arrival_time"]
    )


# ---------------------------------------------------------------------------
# 8. Invalid IDs and Error Handling Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_identifiers_and_error_handling(
    arrival_test_db: async_sessionmaker[AsyncSession],
    api_client: AsyncClient,
) -> None:
    """Verify 404 for invalid feed/stop and sanitized 503 for database outages."""
    # 1. Non-existent feed
    res_bad_feed = await api_client.get(
        "/api/v1/feeds/non-existent-feed/stops/STOP_C/arrivals"
    )
    assert res_bad_feed.status_code == 404
    assert "not found" in res_bad_feed.json()["detail"].lower()

    # 2. Non-existent stop
    res_bad_stop = await api_client.get(
        "/api/v1/feeds/metro-city/stops/NON_EXISTENT_STOP/arrivals"
    )
    assert res_bad_stop.status_code == 404
    assert "not found" in res_bad_stop.json()["detail"].lower()

    # 3. Numeric feed ID lookup
    res_numeric_feed = await api_client.get("/api/v1/feeds/1/stops/STOP_C/arrivals")
    assert res_numeric_feed.status_code == 200

    # 4. Simulated database outage -> sanitized 503
    with patch(
        "app.api.transit.ArrivalPredictionService.predict_arrivals_for_stop",
        side_effect=OperationalError("connection failure", {}, Exception()),
    ):
        res_503 = await api_client.get("/api/v1/feeds/metro-city/stops/STOP_C/arrivals")
        assert res_503.status_code == 503
        assert res_503.json()["detail"] == "Database service is temporarily unavailable"


# ---------------------------------------------------------------------------
# 9. Helper Function Unit Tests
# ---------------------------------------------------------------------------


def test_parse_gtfs_time_to_seconds() -> None:
    """Verify parsing standard and extended GTFS time strings."""
    assert parse_gtfs_time_to_seconds("00:00:00") == 0
    assert parse_gtfs_time_to_seconds("08:30:15") == 8 * 3600 + 30 * 60 + 15
    assert parse_gtfs_time_to_seconds("24:00:00") == 86400
    assert parse_gtfs_time_to_seconds("25:30:00") == 91800

    with pytest.raises(ValueError, match="Invalid GTFS time"):
        parse_gtfs_time_to_seconds("invalid")
