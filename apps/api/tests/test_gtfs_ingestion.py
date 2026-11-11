"""Comprehensive tests for GTFS Static Ingestion Pipeline.

Tests archive safety, downloader resilience, CSV parsing & GTFS schedule
rules, and feed-scoped atomic database persistence.
"""

import argparse
import io
import zipfile
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.session import Base
from app.models import (
    Route,
    Shape,
    Stop,
    TransitFeed,
)
from app.services.gtfs.archive import (
    extract_gtfs_tables,
    validate_zip_safety,
)
from app.services.gtfs.downloader import download_gtfs_feed, mask_url_credentials
from app.services.gtfs.exceptions import (
    GTFSDownloadError,
    GTFSSecurityError,
    GTFSValidationError,
)
from app.services.gtfs.importer import persist_feed_data
from app.services.gtfs.parser import parse_gtfs_tables
from app.services.gtfs.service import GTFSIngestionService


def _create_synthetic_gtfs_zip(
    agency_csv: str | None = None,
    routes_csv: str | None = None,
    stops_csv: str | None = None,
    trips_csv: str | None = None,
    stop_times_csv: str | None = None,
    calendar_csv: str | None = None,
    calendar_dates_csv: str | None = None,
    shapes_csv: str | None = None,
) -> bytes:
    """Helper to build an in-memory valid or custom synthetic GTFS ZIP archive."""
    buf = io.BytesIO()

    # Defaults for a minimal valid single-agency feed
    if agency_csv is None:
        agency_csv = (
            "agency_name,agency_url,agency_timezone,agency_phone\n"
            "Metro Transit,https://metro.example.com,America/New_York,555-0100\n"
        )
    if routes_csv is None:
        routes_csv = (
            "route_id,route_short_name,route_long_name,route_type,route_color\n"
            "R1,Red,Red Line,1,#E31837\n"
        )
    if stops_csv is None:
        stops_csv = (
            "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station\n"
            "STATION1,Central Station,40.7128,-74.0060,1,\n"
            "PLATFORM1,Platform 1,40.7129,-74.0061,0,STATION1\n"
            "STOP2,North Station,40.7589,-73.9851,0,\n"
        )
    if calendar_csv is None and calendar_dates_csv is None:
        calendar_csv = (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "WEEKDAY,1,1,1,1,1,0,0,20260101,20261231\n"
        )
    if trips_csv is None:
        trips_csv = (
            "route_id,service_id,trip_id,trip_headsign,direction_id\n"
            "R1,WEEKDAY,T101,Northbound,0\n"
        )
    if stop_times_csv is None:
        stop_times_csv = (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "T101,08:00:00,08:00:00,PLATFORM1,1\n"
            "T101,08:15:00,08:15:00,STOP2,2\n"
        )

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if agency_csv is not None:
            z.writestr("agency.txt", agency_csv)
        if routes_csv is not None:
            z.writestr("routes.txt", routes_csv)
        if stops_csv is not None:
            z.writestr("stops.txt", stops_csv)
        if calendar_csv is not None:
            z.writestr("calendar.txt", calendar_csv)
        if calendar_dates_csv is not None:
            z.writestr("calendar_dates.txt", calendar_dates_csv)
        if trips_csv is not None:
            z.writestr("trips.txt", trips_csv)
        if stop_times_csv is not None:
            z.writestr("stop_times.txt", stop_times_csv)
        if shapes_csv is not None:
            z.writestr("shapes.txt", shapes_csv)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. Archive Safety Tests
# ---------------------------------------------------------------------------


def test_extract_valid_gtfs_archive() -> None:
    """Ensure a standard synthetic ZIP extracts valid tables cleanly."""
    zip_bytes = _create_synthetic_gtfs_zip()
    tables = extract_gtfs_tables(zip_bytes)
    assert "agency.txt" in tables
    assert "routes.txt" in tables
    assert "stops.txt" in tables
    assert "trips.txt" in tables
    assert "stop_times.txt" in tables
    assert "calendar.txt" in tables


def test_archive_rejects_corrupted_zip() -> None:
    """Ensure non-zip data raises GTFSSecurityError."""
    with pytest.raises(GTFSSecurityError, match="Invalid or corrupted ZIP"):
        extract_gtfs_tables(b"not-a-valid-zip-content")


def test_archive_rejects_oversized_archive() -> None:
    """Ensure archive exceeding max_archive_bytes is rejected."""
    with pytest.raises(GTFSSecurityError, match="exceeds limit"):
        extract_gtfs_tables(b"x" * 1024, max_archive_bytes=512)


def test_archive_rejects_path_traversal() -> None:
    """Ensure archive containing '../' traversal entries is rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.txt", "malicious")

    with pytest.raises(GTFSSecurityError, match="directory traversal"):
        extract_gtfs_tables(buf.getvalue())


def test_archive_rejects_absolute_path() -> None:
    """Ensure archive containing absolute paths is rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("/etc/passwd", "malicious")

    with pytest.raises(GTFSSecurityError, match="absolute path"):
        extract_gtfs_tables(buf.getvalue())


def test_archive_rejects_zip_bomb_compression_ratio() -> None:
    """Ensure entries with excessive compression ratios are rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("agency.txt", "0" * 200_000)

    with pytest.raises(GTFSSecurityError, match="Suspicious compression ratio"):
        extract_gtfs_tables(buf.getvalue(), max_compression_ratio=10.0)


def test_archive_rejects_encrypted_entry() -> None:
    """Ensure encrypted zip entries are rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("agency.txt", "data")
        for info in z.infolist():
            info.flag_bits |= 0x1

    with pytest.raises(GTFSSecurityError, match="Encrypted archive entries"):
        validate_zip_safety(zipfile.ZipFile(buf))


# ---------------------------------------------------------------------------
# 2. Downloader Tests
# ---------------------------------------------------------------------------


def test_mask_url_credentials() -> None:
    """Ensure credentials in URLs are sanitized for logs."""
    url = "https://user:supersecret@transit.example.com/gtfs.zip?api_key=mykey123&format=csv"
    masked = mask_url_credentials(url)
    assert "supersecret" not in masked
    assert "mykey123" not in masked
    assert "user:***@transit.example.com" in masked
    assert "api_key=***" in masked
    assert "format=csv" in masked


def _build_mock_client_stream(mock_response):
    """Helper to mock an AsyncClient streaming response."""
    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=mock_stream_cm)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return mock_client


@pytest.mark.asyncio
async def test_download_gtfs_feed_success() -> None:
    """Ensure download_gtfs_feed streams and returns bytes."""
    fake_content = b"PK\x03\x04fake-zip-data"

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-length": str(len(fake_content))}

    async def aiter_bytes():
        yield fake_content

    mock_response.aiter_bytes = aiter_bytes
    mock_client = _build_mock_client_stream(mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        data = await download_gtfs_feed(
            "https://transit.example.com/feed.zip", api_key="secret-key"
        )
        assert data == fake_content


@pytest.mark.asyncio
async def test_download_gtfs_feed_http_error() -> None:
    """Ensure HTTP errors raise GTFSDownloadError."""
    mock_response = AsyncMock()
    mock_response.status_code = 404
    mock_client = _build_mock_client_stream(mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(GTFSDownloadError, match="HTTP 404"):
            await download_gtfs_feed("https://transit.example.com/feed.zip")


@pytest.mark.asyncio
async def test_download_gtfs_feed_size_limit_exceeded() -> None:
    """Ensure downloads exceeding max_bytes are halted."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-length": "5000"}
    mock_client = _build_mock_client_stream(mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(GTFSDownloadError, match="exceeds limit"):
            await download_gtfs_feed(
                "https://transit.example.com/feed.zip", max_bytes=1000
            )


# ---------------------------------------------------------------------------
# 3. Parser & GTFS Schedule Validation Tests
# ---------------------------------------------------------------------------


def test_parser_valid_single_agency_without_agency_id() -> None:
    """Verify single-agency feed without agency_id is valid and resolves routes."""
    agency_csv = (
        "agency_name,agency_url,agency_timezone\n"
        "City Bus,https://citybus.org,America/Chicago\n"
    )
    routes_csv = (
        "route_id,route_short_name,route_long_name,route_type\nR1,10,Crosstown,3\n"
    )
    zip_bytes = _create_synthetic_gtfs_zip(agency_csv=agency_csv, routes_csv=routes_csv)
    tables = extract_gtfs_tables(zip_bytes)
    data = parse_gtfs_tables(tables)

    assert len(data.agencies) == 1
    assert data.agencies[0].agency_id is None
    assert len(data.routes) == 1
    assert data.routes[0].agency_id is None


def test_parser_valid_multi_agency_with_matching_ids() -> None:
    """Verify multi-agency feed requires and maps matching agency_id values."""
    agency_csv = (
        "agency_id,agency_name,agency_url,agency_timezone\n"
        "BUS,City Bus,https://citybus.org,America/Chicago\n"
        "RAIL,Commuter Rail,https://rail.org,America/Chicago\n"
    )
    routes_csv = (
        "route_id,agency_id,route_short_name,route_long_name,route_type\n"
        "B1,BUS,B1,Bus Route 1,3\n"
        "R1,RAIL,R1,Rail Route 1,2\n"
    )
    trips_csv = (
        "route_id,service_id,trip_id,trip_headsign\n"
        "B1,WEEKDAY,T101,Bus Trip\n"
        "R1,WEEKDAY,T102,Rail Trip\n"
    )
    stop_times_csv = (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T101,08:00:00,08:00:00,PLATFORM1,1\n"
        "T102,08:30:00,08:30:00,STOP2,1\n"
    )
    zip_bytes = _create_synthetic_gtfs_zip(
        agency_csv=agency_csv,
        routes_csv=routes_csv,
        trips_csv=trips_csv,
        stop_times_csv=stop_times_csv,
    )
    tables = extract_gtfs_tables(zip_bytes)
    data = parse_gtfs_tables(tables)

    assert len(data.agencies) == 2
    assert {a.agency_id for a in data.agencies} == {"BUS", "RAIL"}
    assert len(data.routes) == 2
    assert data.routes[0].agency_id == "BUS"
    assert data.routes[1].agency_id == "RAIL"


def test_parser_multi_agency_missing_agency_id_fails() -> None:
    """Ensure multi-agency feeds reject routes or agencies missing agency_id."""
    agency_csv = (
        "agency_id,agency_name,agency_url,agency_timezone\n"
        "BUS,City Bus,https://citybus.org,America/Chicago\n"
        ",Commuter Rail,https://rail.org,America/Chicago\n"
    )
    zip_bytes = _create_synthetic_gtfs_zip(agency_csv=agency_csv)
    tables = extract_gtfs_tables(zip_bytes)
    with pytest.raises(GTFSValidationError, match=r"agency_id.*required"):
        parse_gtfs_tables(tables)


def test_parser_preserves_post_midnight_service_day_times() -> None:
    """Ensure stop times like 24:15:00 and 25:35:00 are preserved as valid HH:MM:SS."""
    stop_times_csv = (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T101,24:15:00,24:15:00,PLATFORM1,1\n"
        "T101,25:35:00,25:35:00,STOP2,2\n"
    )
    zip_bytes = _create_synthetic_gtfs_zip(stop_times_csv=stop_times_csv)
    tables = extract_gtfs_tables(zip_bytes)
    data = parse_gtfs_tables(tables)

    assert data.stop_times[0].arrival_time == "24:15:00"
    assert data.stop_times[1].departure_time == "25:35:00"


def test_parser_valid_calendar_dates_only_feed() -> None:
    """Verify feed with calendar_dates.txt and no calendar.txt is accepted."""
    calendar_dates_csv = (
        "service_id,date,exception_type\nHOLIDAY,20261225,1\nHOLIDAY,20260101,1\n"
    )
    trips_csv = (
        "route_id,service_id,trip_id,trip_headsign\nR1,HOLIDAY,T101,Holiday Express\n"
    )
    zip_bytes = _create_synthetic_gtfs_zip(
        calendar_csv="",
        calendar_dates_csv=calendar_dates_csv,
        trips_csv=trips_csv,
    )
    tables = extract_gtfs_tables(zip_bytes)
    del tables["calendar.txt"]
    data = parse_gtfs_tables(tables)

    assert len(data.calendars) == 0
    assert len(data.calendar_dates) == 2
    assert data.calendar_dates[0].service_id == "HOLIDAY"
    assert data.calendar_dates[0].date == date(2026, 12, 25)


def test_parser_rejects_missing_both_calendar_and_calendar_dates() -> None:
    """Ensure error is raised if neither calendar file is present."""
    zip_bytes = _create_synthetic_gtfs_zip()
    tables = extract_gtfs_tables(zip_bytes)
    del tables["calendar.txt"]

    with pytest.raises(GTFSValidationError, match="calendar.txt.*calendar_dates.txt"):
        parse_gtfs_tables(tables)


def test_parser_rejects_invalid_coordinates() -> None:
    """Ensure latitude and longitude bounds [-90, 90] and [-180, 180] are enforced."""
    bad_stops_csv = (
        "stop_id,stop_name,stop_lat,stop_lon\nBAD_STOP,North Pole,95.0,0.0\n"
    )
    zip_bytes = _create_synthetic_gtfs_zip(stops_csv=bad_stops_csv)
    tables = extract_gtfs_tables(zip_bytes)
    with pytest.raises(GTFSValidationError, match="latitude 95.0 out of bounds"):
        parse_gtfs_tables(tables)


def test_parser_rejects_duplicate_route_id() -> None:
    """Ensure duplicate route_id values are rejected."""
    dup_routes_csv = (
        "route_id,route_short_name,route_long_name,route_type\n"
        "R1,Red,Red Line,1\n"
        "R1,Blue,Blue Line,1\n"
    )
    zip_bytes = _create_synthetic_gtfs_zip(routes_csv=dup_routes_csv)
    tables = extract_gtfs_tables(zip_bytes)
    with pytest.raises(GTFSValidationError, match="Duplicate route_id 'R1'"):
        parse_gtfs_tables(tables)


def test_parser_rejects_broken_foreign_keys() -> None:
    """Ensure stop_times referencing non-existent stop_id fails validation."""
    bad_stop_times = (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T101,08:00:00,08:00:00,NON_EXISTENT_STOP,1\n"
    )
    zip_bytes = _create_synthetic_gtfs_zip(stop_times_csv=bad_stop_times)
    tables = extract_gtfs_tables(zip_bytes)
    with pytest.raises(GTFSValidationError, match="References unknown stop_id"):
        parse_gtfs_tables(tables)


def test_parser_valid_shapes() -> None:
    """Verify parser parses shapes.txt with valid sequence, lat, lon, and distance."""
    shapes_csv = (
        "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence,shape_dist_traveled\n"
        "SHAPE1,40.7128,-74.0060,1,0.0\n"
        "SHAPE1,40.7200,-74.0010,2,850.5\n"
        "SHAPE2,40.7500,-73.9900,1,\n"
    )
    zip_bytes = _create_synthetic_gtfs_zip(shapes_csv=shapes_csv)
    tables = extract_gtfs_tables(zip_bytes)
    parsed = parse_gtfs_tables(tables)

    assert len(parsed.shapes) == 3
    s1 = parsed.shapes[0]
    assert s1.shape_id == "SHAPE1"
    assert s1.shape_pt_lat == 40.7128
    assert s1.shape_pt_lon == -74.0060
    assert s1.shape_pt_sequence == 1
    assert s1.shape_dist_traveled == 0.0

    s2 = parsed.shapes[1]
    assert s2.shape_dist_traveled == 850.5

    s3 = parsed.shapes[2]
    assert s3.shape_id == "SHAPE2"
    assert s3.shape_dist_traveled is None


def test_parser_rejects_invalid_shape_coordinates() -> None:
    """Verify parser rejects out-of-range shape coordinates."""
    shapes_csv = (
        "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
        "SHAPE1,95.0000,-74.0060,1\n"
    )
    zip_bytes = _create_synthetic_gtfs_zip(shapes_csv=shapes_csv)
    tables = extract_gtfs_tables(zip_bytes)
    with pytest.raises(GTFSValidationError, match="Coordinates out of range"):
        parse_gtfs_tables(tables)


def test_parser_rejects_duplicate_shape_sequence() -> None:
    """Verify parser rejects duplicate sequence numbers within the same shape_id."""
    shapes_csv = (
        "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
        "SHAPE1,40.7128,-74.0060,1\n"
        "SHAPE1,40.7200,-74.0010,1\n"
    )
    zip_bytes = _create_synthetic_gtfs_zip(shapes_csv=shapes_csv)
    tables = extract_gtfs_tables(zip_bytes)
    with pytest.raises(GTFSValidationError, match="Duplicate shape sequence"):
        parse_gtfs_tables(tables)


# ---------------------------------------------------------------------------
# 4. Database Persistence & Transactional Idempotency Tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def async_test_session():
    """Create an in-memory SQLite async engine with all tables initialized."""
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


@pytest.mark.asyncio
async def test_persist_feed_data_and_idempotent_replace(
    async_test_session: AsyncSession,
) -> None:
    """Verify full static feed import and idempotent re-import without conflicts."""
    session = async_test_session

    # 1. Create a TransitFeed record
    feed = TransitFeed(
        city_name="Metro City",
        slug="metro-city",
        static_gtfs_url="https://transit.example.com/gtfs.zip",
    )
    session.add(feed)
    await session.commit()
    feed_id = feed.id

    # 2. Ingest first version of feed
    zip_bytes_v1 = _create_synthetic_gtfs_zip()
    tables_v1 = extract_gtfs_tables(zip_bytes_v1)
    parsed_v1 = parse_gtfs_tables(tables_v1)

    stats_v1 = await persist_feed_data(session, feed_id, parsed_v1)
    await session.commit()

    assert stats_v1.agencies_count == 1
    assert stats_v1.routes_count == 1
    assert stats_v1.stops_count == 3
    assert stats_v1.trips_count == 1
    assert stats_v1.stop_times_count == 2

    # Verify Stop and parent station relationship in database
    stops_stmt = select(Stop).where(Stop.feed_id == feed_id)
    db_stops = (await session.execute(stops_stmt)).scalars().all()
    assert len(db_stops) == 3

    platform = next(s for s in db_stops if s.stop_id == "PLATFORM1")
    station = next(s for s in db_stops if s.stop_id == "STATION1")
    assert platform.parent_station_id == station.id

    # Verify TransitFeed metadata was updated
    updated_feed = await session.get(TransitFeed, feed_id)
    assert updated_feed.last_static_import_at is not None
    assert updated_feed.feed_status == "active"

    # 3. Idempotently ingest second version of feed with updated data
    routes_v2 = (
        "route_id,route_short_name,route_long_name,route_type,route_color\n"
        "R1,Red,Red Line Updated,1,#E31837\n"
        "R2,Green,Green Line,1,#00843D\n"
    )
    stops_v2 = (
        "stop_id,stop_name,stop_lat,stop_lon,location_type\n"
        "S10,Terminal A,40.7128,-74.0060,0\n"
        "S20,Terminal B,40.7589,-73.9851,0\n"
    )
    trips_v2 = "route_id,service_id,trip_id,trip_headsign\nR2,WEEKDAY,T201,Southbound\n"
    stop_times_v2 = (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T201,09:00:00,09:00:00,S10,1\n"
        "T201,09:20:00,09:20:00,S20,2\n"
    )

    zip_bytes_v2 = _create_synthetic_gtfs_zip(
        routes_csv=routes_v2,
        stops_csv=stops_v2,
        trips_csv=trips_v2,
        stop_times_csv=stop_times_v2,
    )
    tables_v2 = extract_gtfs_tables(zip_bytes_v2)
    parsed_v2 = parse_gtfs_tables(tables_v2)

    stats_v2 = await persist_feed_data(session, feed_id, parsed_v2)
    await session.commit()

    assert stats_v2.routes_count == 2
    assert stats_v2.stops_count == 2
    assert stats_v2.trips_count == 1
    assert stats_v2.stop_times_count == 2

    # Verify database only contains v2 records for feed_id
    routes_stmt = select(Route).where(Route.feed_id == feed_id)
    db_routes = (await session.execute(routes_stmt)).scalars().all()
    assert len(db_routes) == 2
    assert {r.route_id for r in db_routes} == {"R1", "R2"}


@pytest.mark.asyncio
async def test_persist_shapes_and_idempotent_replace(
    async_test_session: AsyncSession,
) -> None:
    """Ensure shapes are persisted and replaced idempotently on new import."""
    session = async_test_session

    feed = TransitFeed(
        city_name="Shape City",
        slug="shape-city",
        static_gtfs_url="https://transit.example.com/gtfs.zip",
    )
    session.add(feed)
    await session.commit()
    feed_id = feed.id

    # 1. Ingest feed with 2 shape points
    shapes_v1 = (
        "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence,shape_dist_traveled\n"
        "SHAPE_RED,40.7128,-74.0060,1,0.0\n"
        "SHAPE_RED,40.7200,-74.0010,2,800.0\n"
    )
    zip_bytes_v1 = _create_synthetic_gtfs_zip(shapes_csv=shapes_v1)
    tables_v1 = extract_gtfs_tables(zip_bytes_v1)
    parsed_v1 = parse_gtfs_tables(tables_v1)

    stats_v1 = await persist_feed_data(session, feed_id, parsed_v1)
    await session.commit()

    assert stats_v1.shapes_count == 2

    # Verify shapes stored in database
    shapes_stmt = (
        select(Shape)
        .where(Shape.feed_id == feed_id)
        .order_by(Shape.shape_pt_sequence.asc())
    )
    db_shapes = (await session.execute(shapes_stmt)).scalars().all()
    assert len(db_shapes) == 2
    assert db_shapes[0].shape_id == "SHAPE_RED"
    assert db_shapes[0].shape_pt_lat == 40.7128
    assert db_shapes[1].shape_pt_sequence == 2

    # 2. Re-ingest with updated shapes (3 points for SHAPE_BLUE)
    shapes_v2 = (
        "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
        "SHAPE_BLUE,37.7749,-122.4194,1\n"
        "SHAPE_BLUE,37.7800,-122.4100,2\n"
        "SHAPE_BLUE,37.7850,-122.4050,3\n"
    )
    zip_bytes_v2 = _create_synthetic_gtfs_zip(shapes_csv=shapes_v2)
    tables_v2 = extract_gtfs_tables(zip_bytes_v2)
    parsed_v2 = parse_gtfs_tables(tables_v2)

    stats_v2 = await persist_feed_data(session, feed_id, parsed_v2)
    await session.commit()

    assert stats_v2.shapes_count == 3

    # Old shapes should be removed and only new ones present
    db_shapes_v2 = (await session.execute(shapes_stmt)).scalars().all()
    assert len(db_shapes_v2) == 3
    assert all(s.shape_id == "SHAPE_BLUE" for s in db_shapes_v2)
    assert not any(s.shape_id == "SHAPE_RED" for s in db_shapes_v2)


@pytest.mark.asyncio
async def test_service_rollback_on_persistence_error(
    async_test_session: AsyncSession,
) -> None:
    """Ensure any error during ingestion triggers a complete transaction rollback."""
    session = async_test_session

    feed = TransitFeed(
        city_name="Rollback City",
        slug="rollback-city",
        static_gtfs_url="https://transit.example.com/gtfs.zip",
    )
    session.add(feed)
    await session.commit()
    feed_id = feed.id

    service = GTFSIngestionService(session)

    # First, import initial valid feed
    zip_bytes_v1 = _create_synthetic_gtfs_zip()
    await service.ingest_archive(feed_id, zip_bytes_v1)

    # Check that 1 route exists
    routes_count = len(
        (await session.execute(select(Route).where(Route.feed_id == feed_id)))
        .scalars()
        .all()
    )
    assert routes_count == 1

    # Now attempt to ingest invalid archive data that raises an error
    with pytest.raises(GTFSSecurityError):
        await service.ingest_archive(feed_id, b"corrupted-not-a-zip")

    # Verify session rolled back cleanly and prior route is still present
    routes_after = len(
        (await session.execute(select(Route).where(Route.feed_id == feed_id)))
        .scalars()
        .all()
    )
    assert routes_after == 1


# ---------------------------------------------------------------------------
# 5. CLI Interface Tests
# ---------------------------------------------------------------------------


def _register_feed_args(**overrides: object) -> argparse.Namespace:
    """Build valid feed-registration arguments with optional overrides."""
    values = {
        "slug": "demo-city",
        "city_name": "Demo City",
        "static_url": "https://data.example.com/demo/gtfs.zip",
        "vehicle_positions_url": "",
        "trip_updates_url": "",
        "alerts_url": "",
        "api_key_env_var": "DEMO_TRANSIT_API_KEY",
        "enable_live_tracking": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.mark.asyncio
async def test_cli_register_feed_stores_only_key_environment_reference(
    async_test_session: AsyncSession,
) -> None:
    """Register a feed and keep live tracking disabled unless explicitly enabled."""
    from app.services.gtfs.cli import run_register_feed

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=async_test_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.gtfs.cli.async_session_factory", mock_factory):
        code = await run_register_feed(_register_feed_args())

    assert code == 0
    feed = (
        await async_test_session.execute(
            select(TransitFeed).where(TransitFeed.slug == "demo-city")
        )
    ).scalar_one()
    assert feed.city_name == "Demo City"
    assert feed.api_key_env_var == "DEMO_TRANSIT_API_KEY"
    assert feed.is_live_tracking_enabled is False
    assert feed.feed_status == "active"


@pytest.mark.asyncio
async def test_cli_register_feed_duplicate_slug_makes_no_changes(
    async_test_session: AsyncSession,
) -> None:
    """A repeated slug is rejected without overwriting its existing configuration."""
    from app.services.gtfs.cli import run_register_feed

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=async_test_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.gtfs.cli.async_session_factory", mock_factory):
        assert await run_register_feed(_register_feed_args()) == 0
        assert (
            await run_register_feed(_register_feed_args(city_name="Changed City")) == 1
        )

    feeds = (
        (
            await async_test_session.execute(
                select(TransitFeed).where(TransitFeed.slug == "demo-city")
            )
        )
        .scalars()
        .all()
    )
    assert len(feeds) == 1
    assert feeds[0].city_name == "Demo City"


@pytest.mark.asyncio
async def test_cli_register_feed_rejects_embedded_credentials_and_unconfigured_live(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Do not persist credentials embedded in URLs or enable empty realtime feeds."""
    from app.services.gtfs.cli import run_register_feed

    mock_factory = MagicMock()
    with patch("app.services.gtfs.cli.async_session_factory", mock_factory):
        code = await run_register_feed(
            _register_feed_args(
                static_url="https://data.example.com/gtfs.zip?api_key=never-log-me"
            )
        )
        assert code == 1
        assert (
            await run_register_feed(_register_feed_args(enable_live_tracking=True)) == 1
        )

    assert "never-log-me" not in caplog.text
    mock_factory.assert_not_called()


@pytest.mark.asyncio
async def test_cli_ingest_missing_feed_id_or_slug() -> None:
    """Ensure CLI run_ingest returns error code 1 when no feed identifier given."""
    import argparse
    from unittest.mock import MagicMock

    from app.services.gtfs.cli import run_ingest

    args = argparse.Namespace(feed_id=None, slug=None, file=None, batch_size=1000)
    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.gtfs.cli.async_session_factory", mock_factory):
        code = await run_ingest(args)
        assert code == 1


@pytest.mark.asyncio
async def test_cli_ingest_nonexistent_file() -> None:
    """Ensure CLI run_ingest returns error code 1 when given invalid file path."""
    import argparse

    from app.services.gtfs.cli import run_ingest

    args = argparse.Namespace(
        feed_id=1, slug=None, file="non_existent_archive_file.zip", batch_size=1000
    )
    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.gtfs.cli.async_session_factory", mock_factory):
        code = await run_ingest(args)
        assert code == 1
