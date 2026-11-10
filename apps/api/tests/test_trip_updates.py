"""Tests for GTFS-Realtime TripUpdates ingestion and predictions."""

import argparse
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from google.transit import gtfs_realtime_pb2
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
    VehiclePosition,
)
from app.services.prediction.service import ArrivalPredictionService
from app.services.realtime.cli import run_poll_trip_updates
from app.services.realtime.exceptions import (
    RealtimeParseError,
    UnsupportedIncrementalityError,
)
from app.services.realtime.parser import (
    ParsedTripUpdatesFeed,
    parse_trip_updates,
)
from app.services.realtime.trip_update_service import TripUpdateIngestionService


def to_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime to UTC for consistent comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def create_sample_trip_update_feed_message(
    *,
    version: str = "2.0",
    incrementality: int = gtfs_realtime_pb2.FeedHeader.Incrementality.FULL_DATASET,
    feed_timestamp: int = 1773328800,
    entities: list[dict] | None = None,
) -> bytes:
    """Helper to build and serialize a FeedMessage with TripUpdates."""
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = version
    msg.header.incrementality = incrementality
    if feed_timestamp > 0:
        msg.header.timestamp = feed_timestamp

    if entities is None:
        entity = msg.entity.add()
        entity.id = "TU1"
        tu = entity.trip_update
        tu.trip.trip_id = "TRIP_1"
        tu.trip.route_id = "R101"
        tu.trip.start_date = "20261110"
        tu.trip.start_time = "10:00:00"
        tu.trip.schedule_relationship = (
            gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.SCHEDULED
        )
        tu.vehicle.id = "bus-201"
        tu.timestamp = 1773328800
        tu.delay = 120

        stu1 = tu.stop_time_update.add()
        stu1.stop_sequence = 2
        stu1.stop_id = "STOP_B"
        stu1.arrival.time = 1773328920
        stu1.arrival.delay = 120

        stu2 = tu.stop_time_update.add()
        stu2.stop_sequence = 3
        stu2.stop_id = "STOP_C"
        stu2.arrival.time = 1773330000
        stu2.arrival.delay = 180
    else:
        for ent_dict in entities:
            entity = msg.entity.add()
            entity.id = ent_dict.get("id", "TU_CUSTOM")
            if ent_dict.get("is_deleted", False):
                entity.is_deleted = True
                continue

            if "trip_update" in ent_dict:
                tu_data = ent_dict["trip_update"]
                tu = entity.trip_update
                if "trip" in tu_data:
                    t_data = tu_data["trip"]
                    if "trip_id" in t_data:
                        tu.trip.trip_id = t_data["trip_id"]
                    if "route_id" in t_data:
                        tu.trip.route_id = t_data["route_id"]
                    if "start_time" in t_data:
                        tu.trip.start_time = t_data["start_time"]
                    if "start_date" in t_data:
                        tu.trip.start_date = t_data["start_date"]
                    if "schedule_relationship" in t_data:
                        tu.trip.schedule_relationship = t_data["schedule_relationship"]

                if "vehicle" in tu_data:
                    v_data = tu_data["vehicle"]
                    if "id" in v_data:
                        tu.vehicle.id = v_data["id"]

                if "timestamp" in tu_data:
                    tu.timestamp = tu_data["timestamp"]

                if "delay" in tu_data:
                    tu.delay = tu_data["delay"]

                for stu_data in tu_data.get("stop_time_updates", []):
                    stu = tu.stop_time_update.add()
                    if "stop_sequence" in stu_data:
                        stu.stop_sequence = stu_data["stop_sequence"]
                    if "stop_id" in stu_data:
                        stu.stop_id = stu_data["stop_id"]
                    if "schedule_relationship" in stu_data:
                        stu.schedule_relationship = stu_data["schedule_relationship"]

                    if "arrival" in stu_data:
                        arr_data = stu_data["arrival"]
                        if "time" in arr_data:
                            stu.arrival.time = arr_data["time"]
                        if "delay" in arr_data:
                            stu.arrival.delay = arr_data["delay"]
                        if "uncertainty" in arr_data:
                            stu.arrival.uncertainty = arr_data["uncertainty"]

                    if "departure" in stu_data:
                        dep_data = stu_data["departure"]
                        if "time" in dep_data:
                            stu.departure.time = dep_data["time"]
                        if "delay" in dep_data:
                            stu.departure.delay = dep_data["delay"]
                        if "uncertainty" in dep_data:
                            stu.departure.uncertainty = dep_data["uncertainty"]

    return msg.SerializeToString()


# ===========================================================================
# 1. Protobuf Parser Unit Tests
# ===========================================================================


def test_parse_trip_updates_valid() -> None:
    """Verify parsing a valid TripUpdates FeedMessage."""
    payload = create_sample_trip_update_feed_message()
    parsed = parse_trip_updates(payload)

    assert isinstance(parsed, ParsedTripUpdatesFeed)
    assert parsed.gtfs_realtime_version == "2.0"
    assert parsed.feed_timestamp == datetime.fromtimestamp(1773328800, tz=UTC)
    assert len(parsed.trip_updates) == 1

    tu = parsed.trip_updates[0]
    assert tu.entity_id == "TU1"
    assert tu.trip_id == "TRIP_1"
    assert tu.route_id == "R101"
    assert tu.vehicle_id == "bus-201"
    assert tu.delay == 120
    assert len(tu.stop_time_updates) == 2

    stu2 = tu.stop_time_updates[1]
    assert stu2.stop_sequence == 3
    assert stu2.stop_id == "STOP_C"
    assert stu2.arrival is not None
    assert stu2.arrival.time == datetime.fromtimestamp(1773330000, tz=UTC)
    assert stu2.arrival.delay == 180


def test_parse_trip_updates_departure_fallback() -> None:
    """Verify departure event is parsed when arrival event is absent."""
    entities = [
        {
            "id": "TU_DEP",
            "trip_update": {
                "trip": {"trip_id": "TRIP_DEP", "route_id": "R1"},
                "stop_time_updates": [
                    {
                        "stop_sequence": 1,
                        "stop_id": "STOP_A",
                        "departure": {"time": 1773328900, "delay": 60},
                    }
                ],
            },
        }
    ]
    payload = create_sample_trip_update_feed_message(entities=entities)
    parsed = parse_trip_updates(payload)

    stu = parsed.trip_updates[0].stop_time_updates[0]
    assert stu.arrival is None
    assert stu.departure is not None
    assert stu.departure.time == datetime.fromtimestamp(1773328900, tz=UTC)
    assert stu.departure.delay == 60


def test_parse_trip_updates_trip_cancellation() -> None:
    """Verify parsing trip cancellation with no stop updates."""
    entities = [
        {
            "id": "TU_CANCEL",
            "trip_update": {
                "trip": {
                    "trip_id": "TRIP_CANCELLED",
                    "schedule_relationship": 3,  # CANCELED
                },
                "delay": 0,
            },
        }
    ]
    payload = create_sample_trip_update_feed_message(entities=entities)
    parsed = parse_trip_updates(payload)

    assert len(parsed.trip_updates) == 1
    tu = parsed.trip_updates[0]
    assert tu.trip_id == "TRIP_CANCELLED"
    assert tu.schedule_relationship == 3
    assert len(tu.stop_time_updates) == 0


def test_parse_trip_updates_skipped_stop() -> None:
    """Verify parsing stop_time_update with SKIPPED relationship."""
    entities = [
        {
            "id": "TU_SKIP",
            "trip_update": {
                "trip": {"trip_id": "TRIP_SKIP"},
                "stop_time_updates": [
                    {
                        "stop_sequence": 2,
                        "stop_id": "STOP_B",
                        "schedule_relationship": 1,  # SKIPPED
                    }
                ],
            },
        }
    ]
    payload = create_sample_trip_update_feed_message(entities=entities)
    parsed = parse_trip_updates(payload)

    stu = parsed.trip_updates[0].stop_time_updates[0]
    assert stu.schedule_relationship == 1


def test_parse_trip_updates_empty_payload() -> None:
    """Verify error on empty payload."""
    with pytest.raises(RealtimeParseError, match="Received empty payload"):
        parse_trip_updates(b"")


def test_parse_trip_updates_corrupt_payload() -> None:
    """Verify error on malformed protobuf payload."""
    with pytest.raises(RealtimeParseError, match="Failed to decode protobuf"):
        parse_trip_updates(b"not-a-protobuf-stream-garbage")


def test_parse_trip_updates_missing_header() -> None:
    """Verify error when FeedHeader is absent."""
    msg = gtfs_realtime_pb2.FeedMessage()
    ent = msg.entity.add()
    ent.id = "E1"
    ent.trip_update.trip.trip_id = "T1"
    raw = msg.SerializePartialToString()

    with pytest.raises(
        RealtimeParseError,
        match="missing required FeedHeader|missing gtfs_realtime_version",
    ):
        parse_trip_updates(raw)


def test_parse_trip_updates_differential_rejected() -> None:
    """Verify rejection of DIFFERENTIAL incrementality."""
    payload = create_sample_trip_update_feed_message(
        incrementality=gtfs_realtime_pb2.FeedHeader.Incrementality.DIFFERENTIAL
    )
    with pytest.raises(
        UnsupportedIncrementalityError, match="DIFFERENTIAL incrementality"
    ):
        parse_trip_updates(payload)


def test_parse_trip_updates_duplicate_entity_id() -> None:
    """Verify error on duplicate entity ID in feed."""
    entities = [
        {
            "id": "DUPE",
            "trip_update": {
                "trip": {"trip_id": "TRIP_1"},
                "stop_time_updates": [{"stop_id": "S1"}],
            },
        },
        {
            "id": "DUPE",
            "trip_update": {
                "trip": {"trip_id": "TRIP_2"},
                "stop_time_updates": [{"stop_id": "S2"}],
            },
        },
    ]
    payload = create_sample_trip_update_feed_message(entities=entities)
    with pytest.raises(RealtimeParseError, match="Duplicate entity ID"):
        parse_trip_updates(payload)


def test_parse_trip_updates_missing_trip_id() -> None:
    """Verify error when trip_id is omitted from trip descriptor."""
    entities = [
        {
            "id": "TU_NO_TRIP",
            "trip_update": {
                "trip": {"route_id": "R1"},
                "stop_time_updates": [{"stop_id": "S1"}],
            },
        }
    ]
    payload = create_sample_trip_update_feed_message(entities=entities)
    with pytest.raises(RealtimeParseError, match="missing trip_id"):
        parse_trip_updates(payload)


def test_parse_trip_updates_missing_stop_identifier() -> None:
    """Verify error when stop_sequence and stop_id are both missing."""
    entities = [
        {
            "id": "TU_NO_STOP",
            "trip_update": {
                "trip": {"trip_id": "TRIP_1"},
                "stop_time_updates": [{"arrival": {"delay": 60}}],
            },
        }
    ]
    payload = create_sample_trip_update_feed_message(entities=entities)
    with pytest.raises(
        RealtimeParseError, match="missing both stop_sequence and stop_id"
    ):
        parse_trip_updates(payload)


# ===========================================================================
# 2. Ingestion Service Integration Tests
# ===========================================================================


@pytest.fixture
async def tu_test_session() -> AsyncGenerator[AsyncSession, None]:
    """Isolated in-memory SQLite database session fixture."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_trip_update_ingestion_service_success(
    tu_test_session: AsyncSession,
) -> None:
    """Verify successful ingestion and snapshot replacement of trip updates."""
    feed = TransitFeed(
        city_name="Test City",
        slug="test-city",
        static_gtfs_url="https://example.com/gtfs.zip",
        realtime_trip_updates_url="https://example.com/tripupdates.pb",
        feed_status="active",
        is_live_tracking_enabled=True,
    )
    tu_test_session.add(feed)
    await tu_test_session.commit()

    service = TripUpdateIngestionService()
    payload = create_sample_trip_update_feed_message()

    # Initial ingestion: 2 stop time update rows from 1 trip update
    count1 = await service.ingest_for_feed(tu_test_session, feed, raw_bytes=payload)
    assert count1 == 2
    assert feed.last_realtime_poll_at is not None

    # Verify rows in DB
    rows = (
        (
            await tu_test_session.execute(
                select(TripUpdate).where(TripUpdate.feed_id == feed.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    assert {r.stop_id for r in rows} == {"STOP_B", "STOP_C"}
    assert all(r.trip_id == "TRIP_1" for r in rows)

    # Second ingestion with different entities atomically replaces snapshot
    new_entities = [
        {
            "id": "TU2",
            "trip_update": {
                "trip": {"trip_id": "TRIP_NEW"},
                "stop_time_updates": [
                    {"stop_sequence": 1, "stop_id": "STOP_X", "arrival": {"delay": 0}}
                ],
            },
        }
    ]
    new_payload = create_sample_trip_update_feed_message(entities=new_entities)
    count2 = await service.ingest_for_feed(tu_test_session, feed, raw_bytes=new_payload)
    assert count2 == 1

    rows_after = (
        (
            await tu_test_session.execute(
                select(TripUpdate).where(TripUpdate.feed_id == feed.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows_after) == 1
    assert rows_after[0].trip_id == "TRIP_NEW"
    assert rows_after[0].stop_id == "STOP_X"


@pytest.mark.asyncio
async def test_trip_update_ingestion_skip_when_url_missing(
    tu_test_session: AsyncSession,
) -> None:
    """Verify graceful skip (return 0) when trip updates URL is not configured."""
    feed = TransitFeed(
        city_name="No URL City",
        slug="no-url-city",
        static_gtfs_url="https://example.com/gtfs.zip",
        realtime_trip_updates_url=None,
        feed_status="active",
        is_live_tracking_enabled=True,
    )
    tu_test_session.add(feed)
    await tu_test_session.commit()

    service = TripUpdateIngestionService()
    count = await service.ingest_for_feed(tu_test_session, feed)
    assert count == 0


@pytest.mark.asyncio
async def test_trip_update_ingestion_feed_isolation(
    tu_test_session: AsyncSession,
) -> None:
    """Verify ingesting for Feed 1 does not affect Feed 2 trip update rows."""
    feed1 = TransitFeed(
        city_name="Feed 1",
        slug="feed-1",
        static_gtfs_url="https://example.com/1.zip",
        realtime_trip_updates_url="https://example.com/1.pb",
    )
    feed2 = TransitFeed(
        city_name="Feed 2",
        slug="feed-2",
        static_gtfs_url="https://example.com/2.zip",
        realtime_trip_updates_url="https://example.com/2.pb",
    )
    tu_test_session.add_all([feed1, feed2])
    await tu_test_session.commit()

    service = TripUpdateIngestionService()

    # Ingest for Feed 1
    p1 = create_sample_trip_update_feed_message()
    await service.ingest_for_feed(tu_test_session, feed1, raw_bytes=p1)

    # Ingest for Feed 2
    ent2 = [
        {
            "id": "TU_F2",
            "trip_update": {
                "trip": {"trip_id": "TRIP_FEED2"},
                "stop_time_updates": [
                    {"stop_sequence": 1, "stop_id": "S_F2", "arrival": {"delay": 10}}
                ],
            },
        }
    ]
    p2 = create_sample_trip_update_feed_message(entities=ent2)
    await service.ingest_for_feed(tu_test_session, feed2, raw_bytes=p2)

    # Ingest Feed 1 again with new payload
    ent1_new = [
        {
            "id": "TU_F1_NEW",
            "trip_update": {
                "trip": {"trip_id": "TRIP_FEED1_NEW"},
                "stop_time_updates": [
                    {
                        "stop_sequence": 1,
                        "stop_id": "S_F1_NEW",
                        "arrival": {"delay": 20},
                    }
                ],
            },
        }
    ]
    p1_new = create_sample_trip_update_feed_message(entities=ent1_new)
    await service.ingest_for_feed(tu_test_session, feed1, raw_bytes=p1_new)

    # Feed 2 rows must remain intact
    f2_rows = (
        (
            await tu_test_session.execute(
                select(TripUpdate).where(TripUpdate.feed_id == feed2.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(f2_rows) == 1
    assert f2_rows[0].trip_id == "TRIP_FEED2"


@pytest.mark.asyncio
async def test_trip_update_cli_poll_success() -> None:
    """Verify run_poll_trip_updates CLI execution."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        feed = TransitFeed(
            city_name="CLI City",
            slug="cli-city",
            static_gtfs_url="https://example.com/gtfs.zip",
            realtime_trip_updates_url="https://example.com/tu.pb",
        )
        session.add(feed)
        await session.commit()

    payload = create_sample_trip_update_feed_message()

    with (
        patch(
            "app.services.realtime.cli.async_session_factory",
            return_value=session_maker(),
        ),
        patch(
            "app.services.realtime.trip_update_service.download_realtime_feed",
            AsyncMock(return_value=payload),
        ),
    ):
        args = argparse.Namespace(feed_id=None, slug="cli-city", file=None)
        exit_code = await run_poll_trip_updates(args)
        assert exit_code == 0

    await engine.dispose()


# ===========================================================================
# 3. Stop Arrivals API Prediction with TripUpdates Integration Tests
# ===========================================================================


@pytest.fixture
async def arrivals_tu_db() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Database fixture with schedule, vehicle positions, and trip updates."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Reference evaluation time: Tuesday Nov 10, 2026 at 10:20:00 AM EST = 15:20:00 UTC
    ref_now_utc = datetime(2026, 11, 10, 15, 20, 0, tzinfo=UTC)

    async with session_maker() as session:
        feed = TransitFeed(
            city_name="TU Test City",
            slug="tu-city",
            static_gtfs_url="https://tu.example.com/gtfs.zip",
            realtime_trip_updates_url="https://tu.example.com/tu.pb",
            realtime_vehicle_positions_url="https://tu.example.com/vp.pb",
            feed_status="active",
            is_live_tracking_enabled=True,
        )
        session.add(feed)
        await session.flush()

        agency = Agency(
            feed_id=feed.id,
            agency_id="TU_AGENCY",
            name="TU Agency",
            url="https://tu.example.com",
            timezone="America/New_York",
        )
        session.add(agency)
        await session.flush()

        route = Route(
            feed_id=feed.id,
            agency_id=agency.id,
            route_id="R101",
            short_name="101",
            long_name="Main Line",
            route_type=3,
        )
        session.add(route)
        await session.flush()

        stop_a = Stop(
            feed_id=feed.id,
            stop_id="STOP_A",
            name="Stop A",
            latitude=40.71,
            longitude=-74.01,
        )
        stop_b = Stop(
            feed_id=feed.id,
            stop_id="STOP_B",
            name="Stop B",
            latitude=40.72,
            longitude=-74.02,
        )
        stop_c = Stop(
            feed_id=feed.id,
            stop_id="STOP_C",
            name="Stop C - Target",
            latitude=40.73,
            longitude=-74.03,
        )
        session.add_all([stop_a, stop_b, stop_c])
        await session.flush()

        cal = Calendar(
            feed_id=feed.id,
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
        session.add(cal)
        await session.flush()

        # Trip 1: has TripUpdate with absolute arrival time at Stop C
        trip1 = Trip(
            feed_id=feed.id,
            route_id=route.id,
            service_id="cal_weekday",
            trip_id="TRIP_TU_TIME",
            trip_headsign="Uptown via TU Time",
        )
        # Trip 2: has TripUpdate with delay-only at Stop C
        trip2 = Trip(
            feed_id=feed.id,
            route_id=route.id,
            service_id="cal_weekday",
            trip_id="TRIP_TU_DELAY",
            trip_headsign="Uptown via TU Delay",
        )
        # Trip 3: Canceled trip
        trip3 = Trip(
            feed_id=feed.id,
            route_id=route.id,
            service_id="cal_weekday",
            trip_id="TRIP_TU_CANCELED",
            trip_headsign="Canceled Service",
        )
        # Trip 4: Stop C is SKIPPED
        trip4 = Trip(
            feed_id=feed.id,
            route_id=route.id,
            service_id="cal_weekday",
            trip_id="TRIP_TU_SKIPPED",
            trip_headsign="Express Skipping C",
        )
        # Trip 5: Live VehiclePosition only (fallback to SCHEDULE_ONLY)
        trip5 = Trip(
            feed_id=feed.id,
            route_id=route.id,
            service_id="cal_weekday",
            trip_id="TRIP_VP_ONLY",
            trip_headsign="Standard VP Trip",
        )
        session.add_all([trip1, trip2, trip3, trip4, trip5])
        await session.flush()

        # Stop times:
        # Trip 1 scheduled at Stop C at 10:30:00 (15:30:00 UTC)
        st1_c = StopTime(
            feed_id=feed.id,
            trip_id=trip1.id,
            stop_id=stop_c.id,
            stop_sequence=3,
            arrival_time="10:30:00",
            departure_time="10:30:00",
        )
        # Trip 2 scheduled at Stop C at 10:35:00 (15:35:00 UTC)
        st2_c = StopTime(
            feed_id=feed.id,
            trip_id=trip2.id,
            stop_id=stop_c.id,
            stop_sequence=3,
            arrival_time="10:35:00",
            departure_time="10:35:00",
        )
        # Trip 3 scheduled at Stop C at 10:40:00 (15:40:00 UTC)
        st3_c = StopTime(
            feed_id=feed.id,
            trip_id=trip3.id,
            stop_id=stop_c.id,
            stop_sequence=3,
            arrival_time="10:40:00",
            departure_time="10:40:00",
        )
        # Trip 4 scheduled at Stop C at 10:45:00 (15:45:00 UTC)
        st4_c = StopTime(
            feed_id=feed.id,
            trip_id=trip4.id,
            stop_id=stop_c.id,
            stop_sequence=3,
            arrival_time="10:45:00",
            departure_time="10:45:00",
        )
        # Trip 5 scheduled at Stop C at 10:50:00 (15:50:00 UTC)
        st5_a = StopTime(
            feed_id=feed.id,
            trip_id=trip5.id,
            stop_id=stop_a.id,
            stop_sequence=1,
            arrival_time="10:10:00",
            departure_time="10:10:00",
        )
        st5_c = StopTime(
            feed_id=feed.id,
            trip_id=trip5.id,
            stop_id=stop_c.id,
            stop_sequence=3,
            arrival_time="10:50:00",
            departure_time="10:50:00",
        )
        session.add_all([st1_c, st2_c, st3_c, st4_c, st5_a, st5_c])
        await session.flush()

        # Real-time data:
        # 1. Trip 1 TripUpdate:
        # Scheduled: 15:30:00 UTC.
        # Absolute arrival_time: 15:33:00 UTC (180s delay)
        # arrival_delay: 120s (time takes precedence over delay!)
        tu1 = TripUpdate(
            feed_id=feed.id,
            entity_id="TU_1",
            trip_id="TRIP_TU_TIME",
            route_id="R101",
            vehicle_id="bus-101",
            stop_sequence=3,
            stop_id="STOP_C",
            arrival_time=datetime(2026, 11, 10, 15, 33, 0, tzinfo=UTC),
            arrival_delay=120,  # 180s from arrival_time must win
            update_timestamp=ref_now_utc - timedelta(seconds=30),
            feed_timestamp=ref_now_utc - timedelta(seconds=30),
        )

        # 2. Trip 2 TripUpdate:
        # Scheduled: 15:35:00 UTC.
        # Only arrival_delay: 240s late -> estimated 15:39:00 UTC
        tu2 = TripUpdate(
            feed_id=feed.id,
            entity_id="TU_2",
            trip_id="TRIP_TU_DELAY",
            route_id="R101",
            vehicle_id="bus-102",
            stop_sequence=3,
            stop_id="STOP_C",
            arrival_time=None,
            arrival_delay=240,
            update_timestamp=ref_now_utc - timedelta(seconds=45),
            feed_timestamp=ref_now_utc - timedelta(seconds=45),
        )

        # 3. Trip 3 TripUpdate: Canceled trip
        tu3 = TripUpdate(
            feed_id=feed.id,
            entity_id="TU_3",
            trip_id="TRIP_TU_CANCELED",
            route_id="R101",
            schedule_relationship=3,  # CANCELED
            update_timestamp=ref_now_utc - timedelta(seconds=10),
        )

        # 4. Trip 4 TripUpdate: Skipped stop C
        tu4 = TripUpdate(
            feed_id=feed.id,
            entity_id="TU_4",
            trip_id="TRIP_TU_SKIPPED",
            route_id="R101",
            stop_sequence=3,
            stop_id="STOP_C",
            stop_schedule_relationship=1,  # SKIPPED
            update_timestamp=ref_now_utc - timedelta(seconds=20),
        )

        # 5. Trip 5 VehiclePosition: Live position at sequence 1 (Stop A)
        vp5 = VehiclePosition(
            feed_id=feed.id,
            entity_id="VP_5",
            vehicle_id="bus-105",
            trip_id="TRIP_VP_ONLY",
            route_id="R101",
            current_stop_sequence=1,
            current_status=2,  # IN_TRANSIT_TO
            latitude=40.71,
            longitude=-74.01,
            vehicle_timestamp=ref_now_utc - timedelta(seconds=30),
        )

        session.add_all([tu1, tu2, tu3, tu4, vp5])
        await session.commit()

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield session_maker
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def arrivals_client(
    arrivals_tu_db: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    """Test HTTP client with overridden session dependency."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_stop_arrivals_with_trip_updates(
    arrivals_client: AsyncClient,
) -> None:
    """Verify stop arrivals API returns TRIP_UPDATE predictions."""
    ref_time = datetime(2026, 11, 10, 15, 20, 0, tzinfo=UTC)

    response = await arrivals_client.get(
        "/api/v1/feeds/tu-city/stops/STOP_C/arrivals",
        params={"reference_time": ref_time.isoformat()},
    )
    assert response.status_code == 200
    data = response.json()["data"]

    # Expected predictions:
    # 1. TRIP_TU_TIME (TRIP_UPDATE, estimated 15:33:00, delay 180s from arrival_time)
    # 2. TRIP_TU_DELAY (TRIP_UPDATE, estimated 15:39:00, delay 240s from arrival_delay)
    # 3. TRIP_VP_ONLY (SCHEDULE_ONLY, estimated 15:50:00, delay 0s from static schedule)
    # Canceled TRIP_TU_CANCELED and Skipped TRIP_TU_SKIPPED must be excluded!
    trip_ids = [p["trip_id"] for p in data]
    assert "TRIP_TU_CANCELED" not in trip_ids
    assert "TRIP_TU_SKIPPED" not in trip_ids
    assert trip_ids == ["TRIP_TU_TIME", "TRIP_TU_DELAY", "TRIP_VP_ONLY"]

    # Check TRIP_TU_TIME
    p1 = next(p for p in data if p["trip_id"] == "TRIP_TU_TIME")
    assert p1["prediction_source"] == "TRIP_UPDATE"
    assert p1["vehicle_id"] == "bus-101"
    assert p1["delay_seconds"] == 180  # from arrival_time (15:33 - 15:30), NOT 120
    assert datetime.fromisoformat(p1["estimated_arrival_time"]) == datetime(
        2026, 11, 10, 15, 33, 0, tzinfo=UTC
    )

    # Check TRIP_TU_DELAY
    p2 = next(p for p in data if p["trip_id"] == "TRIP_TU_DELAY")
    assert p2["prediction_source"] == "TRIP_UPDATE"
    assert p2["vehicle_id"] == "bus-102"
    assert p2["delay_seconds"] == 240
    assert datetime.fromisoformat(p2["estimated_arrival_time"]) == datetime(
        2026, 11, 10, 15, 39, 0, tzinfo=UTC
    )

    # Check TRIP_VP_ONLY
    p3 = next(p for p in data if p["trip_id"] == "TRIP_VP_ONLY")
    assert p3["prediction_source"] == "SCHEDULE_ONLY"
    assert p3["vehicle_id"] == "bus-105"
    assert p3["delay_seconds"] == 0


@pytest.mark.asyncio
async def test_stale_trip_update_ignored(
    arrivals_tu_db: async_sessionmaker[AsyncSession],
) -> None:
    """Verify that TripUpdate with timestamp older than 300s is ignored."""
    service = ArrivalPredictionService(max_realtime_age_seconds=300)

    # Evaluate at 15:40:00 UTC (update was at 15:19:30 UTC -> stale at 15:40:00)
    stale_eval_time = datetime(2026, 11, 10, 15, 40, 0, tzinfo=UTC)

    async with arrivals_tu_db() as session:
        feed = (
            await session.execute(
                select(TransitFeed).where(TransitFeed.slug == "tu-city")
            )
        ).scalar_one()
        preds = await service.predict_arrivals_for_stop(
            session,
            feed,
            stop_id="STOP_C",
            reference_time=stale_eval_time,
        )

        # None of the updates/positions are fresh at 15:40:00
        assert len(preds) == 0
