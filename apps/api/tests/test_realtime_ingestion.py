"""Unit and integration tests for GTFS-Realtime vehicle position ingestion."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.transit import gtfs_realtime_pb2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.session import Base
from app.models.feed import TransitFeed
from app.models.vehicle_position import VehiclePosition
from app.services.realtime.cli import run_poll_vehicles
from app.services.realtime.downloader import download_realtime_feed
from app.services.realtime.exceptions import (
    RealtimeDownloadError,
    RealtimeParseError,
    RealtimePersistenceError,
    UnsupportedIncrementalityError,
)
from app.services.realtime.parser import parse_vehicle_positions
from app.services.realtime.service import VehiclePositionIngestionService

# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------


def create_sample_feed_message(
    *,
    version: str = "2.0",
    incrementality: int = gtfs_realtime_pb2.FeedHeader.Incrementality.FULL_DATASET,
    feed_timestamp: int = 1700000000,
    entities: list[dict] | None = None,
) -> bytes:
    """Helper to build and serialize a valid or customized FeedMessage."""
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = version
    msg.header.incrementality = incrementality
    if feed_timestamp > 0:
        msg.header.timestamp = feed_timestamp

    if entities is None:
        # Default with 1 full vehicle position
        entity = msg.entity.add()
        entity.id = "V1"
        vp = entity.vehicle
        vp.vehicle.id = "bus-101"
        vp.vehicle.label = "101 Downtown"
        vp.vehicle.license_plate = "DL-01-AB-1234"
        vp.trip.trip_id = "trip-456"
        vp.trip.route_id = "route-7"
        vp.trip.direction_id = 0
        vp.trip.start_time = "09:30:00"
        vp.trip.start_date = "20261110"
        vp.trip.schedule_relationship = (
            gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.SCHEDULED
        )
        vp.position.latitude = 28.6139
        vp.position.longitude = 77.2090
        vp.position.bearing = 180.0
        vp.position.speed = 11.5
        vp.position.odometer = 5420.0
        vp.stop_id = "stop-10"
        vp.current_stop_sequence = 4
        vp.current_status = (
            gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.STOPPED_AT
        )
        vp.congestion_level = (
            gtfs_realtime_pb2.VehiclePosition.CongestionLevel.RUNNING_SMOOTHLY
        )
        vp.occupancy_status = (
            gtfs_realtime_pb2.VehiclePosition.OccupancyStatus.MANY_SEATS_AVAILABLE
        )
        vp.occupancy_percentage = 35
        vp.timestamp = 1700000010
    else:
        for ent_dict in entities:
            entity = msg.entity.add()
            entity.id = ent_dict.get("id", "ent-default")
            if ent_dict.get("is_deleted"):
                entity.is_deleted = True
            if "vehicle" in ent_dict:
                v_data = ent_dict["vehicle"]
                vp = entity.vehicle
                if "position" in v_data:
                    p_data = v_data["position"]
                    if "latitude" in p_data:
                        vp.position.latitude = p_data["latitude"]
                    if "longitude" in p_data:
                        vp.position.longitude = p_data["longitude"]
                    if "bearing" in p_data:
                        vp.position.bearing = p_data["bearing"]
                    if "speed" in p_data:
                        vp.position.speed = p_data["speed"]
                    if "odometer" in p_data:
                        vp.position.odometer = p_data["odometer"]
                if "vehicle" in v_data:
                    v_desc = v_data["vehicle"]
                    if "id" in v_desc:
                        vp.vehicle.id = v_desc["id"]
                    if "label" in v_desc:
                        vp.vehicle.label = v_desc["label"]
                    if "license_plate" in v_desc:
                        vp.vehicle.license_plate = v_desc["license_plate"]
                if "trip" in v_data:
                    t_desc = v_data["trip"]
                    if "trip_id" in t_desc:
                        vp.trip.trip_id = t_desc["trip_id"]
                    if "route_id" in t_desc:
                        vp.trip.route_id = t_desc["route_id"]
                    if "direction_id" in t_desc:
                        vp.trip.direction_id = t_desc["direction_id"]
                    if "start_time" in t_desc:
                        vp.trip.start_time = t_desc["start_time"]
                    if "start_date" in t_desc:
                        vp.trip.start_date = t_desc["start_date"]
                    if "schedule_relationship" in t_desc:
                        vp.trip.schedule_relationship = t_desc["schedule_relationship"]
                if "stop_id" in v_data:
                    vp.stop_id = v_data["stop_id"]
                if "current_stop_sequence" in v_data:
                    vp.current_stop_sequence = v_data["current_stop_sequence"]
                if "current_status" in v_data:
                    vp.current_status = v_data["current_status"]
                if "timestamp" in v_data:
                    vp.timestamp = v_data["timestamp"]

    return msg.SerializeToString()


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


# ---------------------------------------------------------------------------
# 1. Protobuf Parser & Validation Tests
# ---------------------------------------------------------------------------


def test_parse_valid_single_vehicle_full_dataset() -> None:
    """Verify parsing a fully-populated GTFS-Realtime vehicle position message."""
    payload = create_sample_feed_message()
    parsed = parse_vehicle_positions(payload)

    assert parsed.gtfs_realtime_version == "2.0"
    assert parsed.feed_timestamp == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
    assert len(parsed.vehicles) == 1

    v = parsed.vehicles[0]
    assert v.entity_id == "V1"
    assert v.vehicle_id == "bus-101"
    assert v.vehicle_label == "101 Downtown"
    assert v.license_plate == "DL-01-AB-1234"
    assert v.trip_id == "trip-456"
    assert v.route_id == "route-7"
    assert v.direction_id == 0
    assert v.start_time == "09:30:00"
    assert v.start_date == "20261110"
    assert v.schedule_relationship == 0
    assert v.latitude == pytest.approx(28.6139, rel=1e-4)
    assert v.longitude == pytest.approx(77.2090, rel=1e-4)
    assert v.bearing == 180.0
    assert v.speed == 11.5
    assert v.odometer == 5420.0
    assert v.stop_id == "stop-10"
    assert v.current_stop_sequence == 4
    assert v.current_status == 1  # STOPPED_AT
    assert v.congestion_level == 1  # RUNNING_SMOOTHLY
    assert v.occupancy_status == 1  # MANY_SEATS_AVAILABLE
    assert v.occupancy_percentage == 35
    assert v.vehicle_timestamp == datetime(2023, 11, 14, 22, 13, 30, tzinfo=UTC)


def test_parse_multiple_vehicles() -> None:
    """Verify parsing multiple vehicle positions in a single feed."""
    entities = [
        {
            "id": "bus-1",
            "vehicle": {
                "position": {"latitude": 28.5, "longitude": 77.1},
                "vehicle": {"id": "v-1"},
            },
        },
        {
            "id": "bus-2",
            "vehicle": {
                "position": {"latitude": 28.6, "longitude": 77.2},
                "vehicle": {"id": "v-2"},
            },
        },
        {
            "id": "bus-3",
            "vehicle": {
                "position": {"latitude": 28.7, "longitude": 77.3},
                "vehicle": {"id": "v-3"},
            },
        },
    ]
    payload = create_sample_feed_message(entities=entities)
    parsed = parse_vehicle_positions(payload)

    assert len(parsed.vehicles) == 3
    assert [v.entity_id for v in parsed.vehicles] == ["bus-1", "bus-2", "bus-3"]
    assert [v.latitude for v in parsed.vehicles] == [
        pytest.approx(28.5, rel=1e-4),
        pytest.approx(28.6, rel=1e-4),
        pytest.approx(28.7, rel=1e-4),
    ]


def test_parse_absent_optional_fields_with_stable_entity_id() -> None:
    """Verify entity with only minimal required fields parses cleanly."""
    entities = [
        {
            "id": "minimal-entity",
            "vehicle": {
                "position": {"latitude": 40.7128, "longitude": -74.0060},
            },
        }
    ]
    payload = create_sample_feed_message(entities=entities)
    parsed = parse_vehicle_positions(payload)

    assert len(parsed.vehicles) == 1
    v = parsed.vehicles[0]
    assert v.entity_id == "minimal-entity"
    assert v.latitude == pytest.approx(40.7128, rel=1e-4)
    assert v.longitude == pytest.approx(-74.0060, rel=1e-4)
    assert v.vehicle_id is None
    assert v.trip_id is None
    assert v.route_id is None
    assert v.speed is None
    assert v.bearing is None
    assert v.vehicle_timestamp is None


def test_parse_skips_non_vehicle_or_deleted_entities() -> None:
    """Ensure entities without vehicle positions or marked deleted are skipped."""
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"

    # 1. Normal vehicle entity
    e1 = msg.entity.add()
    e1.id = "v1"
    e1.vehicle.position.latitude = 10.0
    e1.vehicle.position.longitude = 20.0

    # 2. Trip update only (no vehicle)
    e2 = msg.entity.add()
    e2.id = "tu1"
    e2.trip_update.trip.trip_id = "t1"

    # 3. Deleted entity
    e3 = msg.entity.add()
    e3.id = "v3"
    e3.is_deleted = True
    e3.vehicle.position.latitude = 15.0
    e3.vehicle.position.longitude = 25.0

    parsed = parse_vehicle_positions(msg.SerializeToString())
    assert len(parsed.vehicles) == 1
    assert parsed.vehicles[0].entity_id == "v1"


def test_parse_rejects_empty_payload() -> None:
    """Verify empty payload raises RealtimeParseError."""
    with pytest.raises(RealtimeParseError, match="Received empty payload"):
        parse_vehicle_positions(b"")


def test_parse_rejects_invalid_protobuf() -> None:
    """Verify corrupted bytes raise RealtimeParseError."""
    with pytest.raises(
        RealtimeParseError, match="Corrupted GTFS-Realtime message|Failed to decode"
    ):
        parse_vehicle_positions(b"not-a-protobuf-stream-of-bytes-definitely-garbage")


def test_parse_rejects_missing_header() -> None:
    """Verify missing FeedHeader is rejected."""
    msg = gtfs_realtime_pb2.FeedMessage()
    e = msg.entity.add()
    e.id = "v1"
    # Serialize partial message without header
    with pytest.raises(
        RealtimeParseError,
        match="missing required FeedHeader|missing gtfs_realtime_version",
    ):
        parse_vehicle_positions(msg.SerializePartialToString())


def test_parse_rejects_differential_incrementality() -> None:
    """Verify DIFFERENTIAL incrementality is explicitly rejected."""
    payload = create_sample_feed_message(
        incrementality=gtfs_realtime_pb2.FeedHeader.Incrementality.DIFFERENTIAL
    )
    with pytest.raises(
        UnsupportedIncrementalityError,
        match="DIFFERENTIAL incrementality is not supported",
    ):
        parse_vehicle_positions(payload)


def test_parse_rejects_duplicate_entity_id() -> None:
    """Verify duplicate entity IDs in feed trigger RealtimeParseError."""
    entities = [
        {
            "id": "duplicate-id",
            "vehicle": {"position": {"latitude": 10.0, "longitude": 20.0}},
        },
        {
            "id": "duplicate-id",
            "vehicle": {"position": {"latitude": 11.0, "longitude": 21.0}},
        },
    ]
    payload = create_sample_feed_message(entities=entities)
    with pytest.raises(RealtimeParseError, match="Duplicate entity ID found"):
        parse_vehicle_positions(payload)


def test_parse_rejects_entity_missing_id() -> None:
    """Verify entity with blank or missing ID is rejected."""
    entities = [
        {"id": "   ", "vehicle": {"position": {"latitude": 10.0, "longitude": 20.0}}},
    ]
    payload = create_sample_feed_message(entities=entities)
    with pytest.raises(
        RealtimeParseError, match="FeedEntity missing required identifier"
    ):
        parse_vehicle_positions(payload)


def test_parse_rejects_vehicle_missing_position() -> None:
    """Verify vehicle entity without position field is rejected."""
    entities = [
        {"id": "v-no-pos", "vehicle": {"vehicle": {"id": "bus-1"}}},
    ]
    payload = create_sample_feed_message(entities=entities)
    with pytest.raises(RealtimeParseError, match="missing required position data"):
        parse_vehicle_positions(payload)


@pytest.mark.parametrize(
    ("lat", "lon"),
    [
        (95.0, 77.0),
        (-95.0, 77.0),
        (28.0, 185.0),
        (28.0, -185.0),
        (float("nan"), 77.0),
        (28.0, float("inf")),
    ],
)
def test_parse_rejects_coordinates_out_of_bounds(lat: float, lon: float) -> None:
    """Verify invalid or out-of-bounds coordinates raise RealtimeParseError."""
    entities = [
        {
            "id": "v-bad-coords",
            "vehicle": {"position": {"latitude": lat, "longitude": lon}},
        },
    ]
    payload = create_sample_feed_message(entities=entities)
    with pytest.raises(
        RealtimeParseError, match="Coordinates out of bounds|Non-finite coordinates"
    ):
        parse_vehicle_positions(payload)


def test_parse_rejects_invalid_bearing_and_speed() -> None:
    """Verify out-of-range bearing and negative speed raise RealtimeParseError."""
    # Bad bearing
    ent_bad_bearing = [
        {
            "id": "v1",
            "vehicle": {
                "position": {"latitude": 10.0, "longitude": 20.0, "bearing": 400.0}
            },
        },
    ]
    with pytest.raises(RealtimeParseError, match="Invalid bearing"):
        parse_vehicle_positions(create_sample_feed_message(entities=ent_bad_bearing))

    # Bad speed
    ent_bad_speed = [
        {
            "id": "v1",
            "vehicle": {
                "position": {"latitude": 10.0, "longitude": 20.0, "speed": -5.0}
            },
        },
    ]
    with pytest.raises(RealtimeParseError, match="Invalid speed"):
        parse_vehicle_positions(create_sample_feed_message(entities=ent_bad_speed))


# ---------------------------------------------------------------------------
# 2. Downloader Tests & Secret Masking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_downloader_masks_credentials_and_respects_size() -> None:
    """Verify that credentials in URL are masked and response size is capped."""
    test_bytes = create_sample_feed_message()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Length": str(len(test_bytes))}

    async def mock_aiter(chunk_size: int = 65536):
        yield test_bytes

    mock_resp.aiter_bytes = mock_aiter

    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient.stream", return_value=mock_stream):
        data = await download_realtime_feed(
            "https://transit.example.com/gtfs-rt?key=super_secret_token",
            api_key="secret-api-key",
            max_bytes=10000,
        )
        assert data == test_bytes


@pytest.mark.asyncio
async def test_downloader_size_exceeded_raises() -> None:
    """Verify downloading payload exceeding max_bytes raises RealtimeDownloadError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Length": "100000"}

    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient.stream", return_value=mock_stream):
        with pytest.raises(RealtimeDownloadError, match="exceeds limit"):
            await download_realtime_feed(
                "https://transit.example.com/gtfs-rt",
                max_bytes=500,
            )


@pytest.mark.asyncio
async def test_downloader_http_error_raises() -> None:
    """Verify HTTP status error raises RealtimeDownloadError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.headers = {}

    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient.stream", return_value=mock_stream):
        with pytest.raises(RealtimeDownloadError, match="HTTP 404 error"):
            await download_realtime_feed("https://transit.example.com/gtfs-rt")


# ---------------------------------------------------------------------------
# 3. Snapshot Atomic Persistence & Rollback Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_atomic_replacement_snapshot_persistence(
    async_test_session: AsyncSession,
) -> None:
    """Verify atomic snapshot replacement of vehicle positions for a feed."""
    session = async_test_session

    # Create test feed
    feed = TransitFeed(
        city_name="Metro City",
        slug="metro-city",
        static_gtfs_url="https://transit.example.com/gtfs.zip",
        realtime_vehicle_positions_url="https://transit.example.com/rt/vehicles",
    )
    session.add(feed)
    await session.commit()
    await session.refresh(feed)

    service = VehiclePositionIngestionService()

    # 1. Ingest initial snapshot of 2 vehicles
    snapshot1 = create_sample_feed_message(
        entities=[
            {
                "id": "v1",
                "vehicle": {"position": {"latitude": 28.5, "longitude": 77.1}},
            },
            {
                "id": "v2",
                "vehicle": {"position": {"latitude": 28.6, "longitude": 77.2}},
            },
        ]
    )
    count1 = await service.ingest_for_feed(session, feed, raw_bytes=snapshot1)
    assert count1 == 2

    # Verify 2 rows in DB
    result = await session.execute(
        select(VehiclePosition).where(VehiclePosition.feed_id == feed.id)
    )
    rows1 = result.scalars().all()
    assert len(rows1) == 2
    assert {r.entity_id for r in rows1} == {"v1", "v2"}

    # Verify last_realtime_poll_at updated
    await session.refresh(feed)
    assert feed.last_realtime_poll_at is not None
    poll_at_1 = feed.last_realtime_poll_at

    # 2. Ingest replacement snapshot of 3 vehicles (v3, v4, v5)
    snapshot2 = create_sample_feed_message(
        entities=[
            {
                "id": "v3",
                "vehicle": {"position": {"latitude": 28.7, "longitude": 77.3}},
            },
            {
                "id": "v4",
                "vehicle": {"position": {"latitude": 28.8, "longitude": 77.4}},
            },
            {
                "id": "v5",
                "vehicle": {"position": {"latitude": 28.9, "longitude": 77.5}},
            },
        ]
    )
    count2 = await service.ingest_for_feed(session, feed, raw_bytes=snapshot2)
    assert count2 == 3

    # Verify exactly 3 rows in DB (old v1 and v2 are removed)
    result = await session.execute(
        select(VehiclePosition).where(VehiclePosition.feed_id == feed.id)
    )
    rows2 = result.scalars().all()
    assert len(rows2) == 3
    assert {r.entity_id for r in rows2} == {"v3", "v4", "v5"}

    # Verify last_realtime_poll_at updated again
    await session.refresh(feed)
    assert feed.last_realtime_poll_at >= poll_at_1


@pytest.mark.asyncio
async def test_rollback_preserves_previous_snapshot_on_parse_error(
    async_test_session: AsyncSession,
) -> None:
    """Verify previous snapshot is preserved when subsequent feed parsing fails."""
    session = async_test_session

    feed = TransitFeed(
        city_name="Metro City",
        slug="metro-city",
        static_gtfs_url="https://transit.example.com/gtfs.zip",
        realtime_vehicle_positions_url="https://transit.example.com/rt/vehicles",
    )
    session.add(feed)
    await session.commit()
    await session.refresh(feed)

    service = VehiclePositionIngestionService()

    # Initial valid snapshot
    valid_payload = create_sample_feed_message(
        entities=[
            {
                "id": "v1",
                "vehicle": {"position": {"latitude": 28.5, "longitude": 77.1}},
            },
        ]
    )
    await service.ingest_for_feed(session, feed, raw_bytes=valid_payload)
    await session.refresh(feed)
    original_poll_at = feed.last_realtime_poll_at

    # Attempt to ingest invalid payload (DIFFERENTIAL)
    diff_payload = create_sample_feed_message(
        incrementality=gtfs_realtime_pb2.FeedHeader.Incrementality.DIFFERENTIAL
    )
    with pytest.raises(UnsupportedIncrementalityError):
        await service.ingest_for_feed(session, feed, raw_bytes=diff_payload)

    # Verify previous snapshot intact
    result = await session.execute(
        select(VehiclePosition).where(VehiclePosition.feed_id == feed.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].entity_id == "v1"

    # Verify last_realtime_poll_at was NOT modified
    await session.refresh(feed)
    assert feed.last_realtime_poll_at == original_poll_at


@pytest.mark.asyncio
async def test_rollback_preserves_previous_snapshot_on_persistence_error(
    async_test_session: AsyncSession,
) -> None:
    """Verify rollback preserves previous snapshot if database commit fails."""
    session = async_test_session

    feed = TransitFeed(
        city_name="Metro City",
        slug="metro-city",
        static_gtfs_url="https://transit.example.com/gtfs.zip",
        realtime_vehicle_positions_url="https://transit.example.com/rt/vehicles",
    )
    session.add(feed)
    await session.commit()
    await session.refresh(feed)

    service = VehiclePositionIngestionService()

    # Initial snapshot
    initial_payload = create_sample_feed_message(
        entities=[
            {
                "id": "v-init",
                "vehicle": {"position": {"latitude": 28.5, "longitude": 77.1}},
            },
        ]
    )
    await service.ingest_for_feed(session, feed, raw_bytes=initial_payload)

    # Next payload fails during commit
    next_payload = create_sample_feed_message(
        entities=[
            {
                "id": "v-fail",
                "vehicle": {"position": {"latitude": 28.6, "longitude": 77.2}},
            },
        ]
    )

    feed_id = feed.id
    with patch.object(
        session, "commit", side_effect=Exception("Database lock failure")
    ):
        with pytest.raises(RealtimePersistenceError, match="Failed to persist"):
            await service.ingest_for_feed(session, feed, raw_bytes=next_payload)

    # Verify initial snapshot is still in place
    result = await session.execute(
        select(VehiclePosition).where(VehiclePosition.feed_id == feed_id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].entity_id == "v-init"


# ---------------------------------------------------------------------------
# 4. CLI Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cli_poll_vehicles_missing_feed_arguments() -> None:
    """Verify CLI returns exit code 1 if neither --feed-id nor --slug is provided."""
    args = MagicMock()
    args.feed_id = None
    args.slug = None
    args.file = None

    exit_code = await run_poll_vehicles(args)
    assert exit_code == 1


@pytest.mark.asyncio
async def test_cli_poll_vehicles_nonexistent_file() -> None:
    """Verify CLI returns exit code 1 if local protobuf file does not exist."""
    args = MagicMock()
    args.feed_id = 1
    args.slug = None
    args.file = "/path/to/definitely/nonexistent/feed.pb"

    # Mock feed existence in db
    with patch("app.services.realtime.cli.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = TransitFeed(
            id=1, slug="metro", city_name="Metro", static_gtfs_url="url"
        )
        mock_session.execute.return_value = mock_result
        mock_factory.return_value.__aenter__.return_value = mock_session

        exit_code = await run_poll_vehicles(args)
        assert exit_code == 1
