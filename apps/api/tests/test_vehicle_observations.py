"""Tests for historical vehicle observation storage and querying."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from google.transit import gtfs_realtime_pb2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.session import Base
from app.models.feed import TransitFeed
from app.models.vehicle_observation import VehicleObservation
from app.models.vehicle_position import VehiclePosition
from app.services.realtime.exceptions import (
    RealtimePersistenceError,
    UnsupportedIncrementalityError,
)
from app.services.realtime.query import get_recent_observations
from app.services.realtime.service import VehiclePositionIngestionService
from tests.test_realtime_ingestion import create_sample_feed_message


@pytest.fixture
async def async_test_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async database session fixture with all tables initialized."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_maker() as session:
        yield session

    await test_engine.dispose()


@pytest.fixture
async def sample_feed(async_test_session: AsyncSession) -> TransitFeed:
    """Fixture providing an active TransitFeed in the test session."""
    feed = TransitFeed(
        city_name="Metro City",
        slug="metro-city",
        static_gtfs_url="https://transit.example.com/gtfs.zip",
        realtime_vehicle_positions_url="https://transit.example.com/rt/vehicles",
    )
    async_test_session.add(feed)
    await async_test_session.commit()
    await async_test_session.refresh(feed)
    return feed


def to_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime to UTC for cross-database assertions."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


# ---------------------------------------------------------------------------
# 1. First Insert and Repeat-Poll Deduplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_insert_creates_snapshot_and_history(
    async_test_session: AsyncSession, sample_feed: TransitFeed
) -> None:
    """Verify first poll creates rows in both snapshot and historical observations."""
    session = async_test_session
    feed = sample_feed
    service = VehiclePositionIngestionService()

    payload = create_sample_feed_message(
        entities=[
            {
                "id": "v1",
                "vehicle": {
                    "position": {
                        "latitude": 28.5,
                        "longitude": 77.1,
                        "speed": 12.0,
                        "bearing": 90.0,
                    },
                    "vehicle": {"id": "bus-101", "label": "Route 101"},
                    "trip": {"route_id": "R1", "trip_id": "T1"},
                    "timestamp": 1700000000,
                },
            },
            {
                "id": "v2",
                "vehicle": {
                    "position": {"latitude": 28.6, "longitude": 77.2},
                    "vehicle": {"id": "bus-102"},
                    "timestamp": 1700000010,
                },
            },
        ]
    )

    count = await service.ingest_for_feed(session, feed, raw_bytes=payload)
    assert count == 2

    # Verify snapshot
    snap_res = await session.execute(
        select(VehiclePosition).where(VehiclePosition.feed_id == feed.id)
    )
    snapshots = snap_res.scalars().all()
    assert len(snapshots) == 2

    # Verify history
    obs_res = await session.execute(
        select(VehicleObservation).where(VehicleObservation.feed_id == feed.id)
    )
    observations = obs_res.scalars().all()
    assert len(observations) == 2
    assert {o.entity_id for o in observations} == {"v1", "v2"}

    # Verify observation fields
    obs_v1 = next(o for o in observations if o.entity_id == "v1")
    assert obs_v1.vehicle_id == "bus-101"
    assert obs_v1.route_id == "R1"
    assert obs_v1.trip_id == "T1"
    assert obs_v1.speed == 12.0
    assert obs_v1.bearing == 90.0
    expected_ts = datetime.fromtimestamp(1700000000, tz=UTC)
    assert to_utc(obs_v1.observed_at) == expected_ts
    assert to_utc(obs_v1.vehicle_timestamp) == expected_ts


@pytest.mark.asyncio
async def test_repeat_poll_deduplication(
    async_test_session: AsyncSession, sample_feed: TransitFeed
) -> None:
    """Verify repeat poll does not insert duplicate observations."""
    session = async_test_session
    feed = sample_feed
    service = VehiclePositionIngestionService()

    payload = create_sample_feed_message(
        feed_timestamp=1700000000,
        entities=[
            {
                "id": "v1",
                "vehicle": {
                    "position": {"latitude": 28.5, "longitude": 77.1},
                    "timestamp": 1700000005,
                },
            },
        ],
    )

    # First poll: 1 snapshot, 1 observation
    await service.ingest_for_feed(session, feed, raw_bytes=payload)

    obs_count_1 = (
        (
            await session.execute(
                select(VehicleObservation).where(VehicleObservation.feed_id == feed.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(obs_count_1) == 1

    # Second poll with identical payload: snapshot refreshed, NO new observation
    await service.ingest_for_feed(session, feed, raw_bytes=payload)

    snap_count_2 = (
        (
            await session.execute(
                select(VehiclePosition).where(VehiclePosition.feed_id == feed.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(snap_count_2) == 1

    obs_count_2 = (
        (
            await session.execute(
                select(VehicleObservation).where(VehicleObservation.feed_id == feed.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(obs_count_2) == 1  # Still 1 observation, zero duplicates!


@pytest.mark.asyncio
async def test_subsequent_poll_with_new_sample_appends_history(
    async_test_session: AsyncSession, sample_feed: TransitFeed
) -> None:
    """Verify subsequent poll with new observation timestamp appends to history."""
    session = async_test_session
    feed = sample_feed
    service = VehiclePositionIngestionService()

    # Initial poll at t=100
    p1 = create_sample_feed_message(
        entities=[
            {
                "id": "v1",
                "vehicle": {
                    "position": {"latitude": 28.5, "longitude": 77.1},
                    "timestamp": 1700000100,
                },
            },
        ],
    )
    await service.ingest_for_feed(session, feed, raw_bytes=p1)

    # Second poll at t=130 (new position/time)
    p2 = create_sample_feed_message(
        entities=[
            {
                "id": "v1",
                "vehicle": {
                    "position": {"latitude": 28.51, "longitude": 77.11},
                    "timestamp": 1700000130,
                },
            },
        ],
    )
    await service.ingest_for_feed(session, feed, raw_bytes=p2)

    # Snapshot has 1 current row (the latest at t=130)
    snap = (
        (
            await session.execute(
                select(VehiclePosition).where(VehiclePosition.feed_id == feed.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(snap) == 1
    assert snap[0].latitude == pytest.approx(28.51, rel=1e-4)

    # History has 2 rows (t=100 and t=130)
    obs = (
        (
            await session.execute(
                select(VehicleObservation)
                .where(VehicleObservation.feed_id == feed.id)
                .order_by(VehicleObservation.observed_at.asc())
            )
        )
        .scalars()
        .all()
    )
    assert len(obs) == 2
    assert to_utc(obs[0].observed_at) == datetime.fromtimestamp(1700000100, tz=UTC)
    assert to_utc(obs[1].observed_at) == datetime.fromtimestamp(1700000130, tz=UTC)


# ---------------------------------------------------------------------------
# 2. Source Timestamp Fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_timestamp_fallback(
    async_test_session: AsyncSession, sample_feed: TransitFeed
) -> None:
    """Verify fallback when vehicle_timestamp is absent."""
    session = async_test_session
    feed = sample_feed
    service = VehiclePositionIngestionService()

    # Case A: vehicle_timestamp absent, feed_timestamp present
    p_feed_ts = create_sample_feed_message(
        feed_timestamp=1700000500,
        entities=[
            {
                "id": "v-no-vehicle-ts",
                "vehicle": {
                    "position": {"latitude": 28.5, "longitude": 77.1},
                    # No timestamp
                },
            },
        ],
    )
    await service.ingest_for_feed(session, feed, raw_bytes=p_feed_ts)

    obs1 = (
        await session.execute(
            select(VehicleObservation).where(
                VehicleObservation.entity_id == "v-no-vehicle-ts"
            )
        )
    ).scalar_one()
    assert obs1.vehicle_timestamp is None
    assert to_utc(obs1.feed_timestamp) == datetime.fromtimestamp(1700000500, tz=UTC)
    assert to_utc(obs1.observed_at) == datetime.fromtimestamp(1700000500, tz=UTC)

    # Case B: both vehicle_timestamp and feed_timestamp absent
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    e = msg.entity.add()
    e.id = "v-no-ts-at-all"
    e.vehicle.position.latitude = 28.5
    e.vehicle.position.longitude = 77.1
    p_no_ts = msg.SerializeToString()

    before_poll = datetime.now(UTC)
    await service.ingest_for_feed(session, feed, raw_bytes=p_no_ts)
    after_poll = datetime.now(UTC)

    obs2 = (
        await session.execute(
            select(VehicleObservation).where(
                VehicleObservation.entity_id == "v-no-ts-at-all"
            )
        )
    ).scalar_one()
    assert obs2.vehicle_timestamp is None
    assert obs2.feed_timestamp is None
    assert before_poll <= to_utc(obs2.observed_at) <= after_poll


# ---------------------------------------------------------------------------
# 3. Atomic Rollback & Error Safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_and_history_atomic_rollback(
    async_test_session: AsyncSession, sample_feed: TransitFeed
) -> None:
    """Verify failure during persistence rolls back both snapshot and history."""
    session = async_test_session
    feed = sample_feed
    service = VehiclePositionIngestionService()

    # Initial valid poll
    p_init = create_sample_feed_message(
        entities=[
            {
                "id": "v-init",
                "vehicle": {
                    "position": {"latitude": 28.5, "longitude": 77.1},
                    "timestamp": 1700000001,
                },
            },
        ],
    )
    await service.ingest_for_feed(session, feed, raw_bytes=p_init)

    # Subsequent poll fails during commit
    p_fail = create_sample_feed_message(
        entities=[
            {
                "id": "v-fail",
                "vehicle": {
                    "position": {"latitude": 28.6, "longitude": 77.2},
                    "timestamp": 1700000002,
                },
            },
        ],
    )

    feed_id = feed.id
    sim_err = Exception("Simulated commit crash")
    with patch.object(session, "commit", side_effect=sim_err):
        with pytest.raises(RealtimePersistenceError, match="Failed to persist"):
            await service.ingest_for_feed(session, feed, raw_bytes=p_fail)

    # Verify snapshot still has only v-init
    snap = (
        (
            await session.execute(
                select(VehiclePosition).where(VehiclePosition.feed_id == feed_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(snap) == 1
    assert snap[0].entity_id == "v-init"

    # Verify history still has only v-init (no partial or orphaned v-fail row)
    obs = (
        (
            await session.execute(
                select(VehicleObservation).where(VehicleObservation.feed_id == feed_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(obs) == 1
    assert obs[0].entity_id == "v-init"


@pytest.mark.asyncio
async def test_invalid_payload_preserves_snapshot_and_history(
    async_test_session: AsyncSession, sample_feed: TransitFeed
) -> None:
    """Verify DIFFERENTIAL or corrupted payload rejects without modifying DB."""
    session = async_test_session
    feed = sample_feed
    service = VehiclePositionIngestionService()

    # Initial valid poll
    p_init = create_sample_feed_message(
        entities=[
            {
                "id": "v1",
                "vehicle": {
                    "position": {"latitude": 28.5, "longitude": 77.1},
                    "timestamp": 1700000001,
                },
            },
        ],
    )
    await service.ingest_for_feed(session, feed, raw_bytes=p_init)
    await session.refresh(feed)
    initial_poll_time = feed.last_realtime_poll_at

    # Attempt to ingest DIFFERENTIAL payload
    p_diff = create_sample_feed_message(
        incrementality=gtfs_realtime_pb2.FeedHeader.Incrementality.DIFFERENTIAL
    )
    with pytest.raises(UnsupportedIncrementalityError):
        await service.ingest_for_feed(session, feed, raw_bytes=p_diff)

    # Check DB state
    feed_id = feed.id
    snap = (
        (
            await session.execute(
                select(VehiclePosition).where(VehiclePosition.feed_id == feed_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(snap) == 1
    assert snap[0].entity_id == "v1"

    obs = (
        (
            await session.execute(
                select(VehicleObservation).where(VehicleObservation.feed_id == feed_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(obs) == 1

    await session.refresh(feed)
    assert feed.last_realtime_poll_at == initial_poll_time


# ---------------------------------------------------------------------------
# 4. Feed Isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_isolation_on_observations(
    async_test_session: AsyncSession, sample_feed: TransitFeed
) -> None:
    """Verify observations for different feeds do not conflict or cross-pollinate."""
    session = async_test_session
    feed_a = sample_feed

    feed_b = TransitFeed(
        city_name="Second City",
        slug="second-city",
        static_gtfs_url="https://second.example.com/gtfs.zip",
        realtime_vehicle_positions_url="https://second.example.com/rt/vehicles",
    )
    session.add(feed_b)
    await session.commit()
    await session.refresh(feed_b)

    service = VehiclePositionIngestionService()

    # Same entity_id 'v-1' and same timestamp in both feeds
    payload = create_sample_feed_message(
        entities=[
            {
                "id": "v-1",
                "vehicle": {
                    "position": {"latitude": 28.5, "longitude": 77.1},
                    "timestamp": 1700000000,
                },
            },
        ],
    )

    await service.ingest_for_feed(session, feed_a, raw_bytes=payload)
    await service.ingest_for_feed(session, feed_b, raw_bytes=payload)

    # Feed A has its observation
    obs_a = (
        (
            await session.execute(
                select(VehicleObservation).where(
                    VehicleObservation.feed_id == feed_a.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(obs_a) == 1
    assert obs_a[0].feed_id == feed_a.id

    # Feed B has its observation
    obs_b = (
        (
            await session.execute(
                select(VehicleObservation).where(
                    VehicleObservation.feed_id == feed_b.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(obs_b) == 1
    assert obs_b[0].feed_id == feed_b.id


# ---------------------------------------------------------------------------
# 5. Query Helper Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recent_observations_query_helper(
    async_test_session: AsyncSession, sample_feed: TransitFeed
) -> None:
    """Verify get_recent_observations respects time bounds, filters, and limits."""
    session = async_test_session
    feed = sample_feed

    base_time = datetime(2026, 11, 10, 10, 0, 0, tzinfo=UTC)

    # Insert 4 historical observations
    records = [
        VehicleObservation(
            feed_id=feed.id,
            entity_id="v1",
            vehicle_id="bus-101",
            route_id="R1",
            trip_id="T1",
            latitude=28.5,
            longitude=77.1,
            speed=10.0,
            observed_at=base_time + timedelta(minutes=1),
        ),
        VehicleObservation(
            feed_id=feed.id,
            entity_id="v1",
            vehicle_id="bus-101",
            route_id="R1",
            trip_id="T1",
            latitude=28.51,
            longitude=77.11,
            speed=12.0,
            observed_at=base_time + timedelta(minutes=5),
        ),
        VehicleObservation(
            feed_id=feed.id,
            entity_id="v2",
            vehicle_id="bus-102",
            route_id="R2",
            trip_id="T2",
            latitude=28.6,
            longitude=77.2,
            speed=15.0,
            observed_at=base_time + timedelta(minutes=3),
        ),
        VehicleObservation(
            feed_id=feed.id,
            entity_id="v1",
            vehicle_id="bus-101",
            route_id="R1",
            trip_id="T1",
            latitude=28.52,
            longitude=77.12,
            speed=14.0,
            observed_at=base_time + timedelta(minutes=15),
        ),
    ]
    session.add_all(records)
    await session.commit()

    # 1. Query with since = base_time + 2 min
    res1 = await get_recent_observations(
        session,
        feed.id,
        since=base_time + timedelta(minutes=2),
    )
    # Should exclude minute 1, returning minutes 15, 5, 3 (ordered newest to oldest)
    assert len(res1) == 3
    assert [r.observed_at for r in res1] == [
        base_time + timedelta(minutes=15),
        base_time + timedelta(minutes=5),
        base_time + timedelta(minutes=3),
    ]

    # 2. Filter by vehicle_id
    res_veh = await get_recent_observations(
        session,
        feed.id,
        since=base_time,
        vehicle_id="bus-102",
    )
    assert len(res_veh) == 1
    assert res_veh[0].vehicle_id == "bus-102"

    # 3. Filter by route_id
    res_route = await get_recent_observations(
        session,
        feed.id,
        since=base_time,
        route_id="R1",
    )
    assert len(res_route) == 3
    assert all(r.route_id == "R1" for r in res_route)

    # 4. Upper bound `until`
    res_until = await get_recent_observations(
        session,
        feed.id,
        since=base_time,
        until=base_time + timedelta(minutes=5),
    )
    assert len(res_until) == 3
    assert all(r.observed_at <= base_time + timedelta(minutes=5) for r in res_until)

    # 5. Limit capping
    res_lim = await get_recent_observations(
        session,
        feed.id,
        since=base_time,
        limit=2,
    )
    assert len(res_lim) == 2


@pytest.mark.asyncio
async def test_get_recent_observations_requires_since(
    async_test_session: AsyncSession, sample_feed: TransitFeed
) -> None:
    """Verify get_recent_observations raises ValueError if since is None."""
    with pytest.raises(ValueError, match="A 'since' timestamp is required"):
        await get_recent_observations(
            async_test_session,
            sample_feed.id,
            since=None,  # type: ignore[arg-type]
        )
