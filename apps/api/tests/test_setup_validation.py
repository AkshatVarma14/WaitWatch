"""Unit and integration tests for setup validation, archive checks, and idempotency."""

import io
import zipfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.session import Base
from app.models.feed import TransitFeed
from app.services.gtfs.archive import (
    REQUIRED_GTFS_FILES,
    compute_archive_sha256,
    validate_archive,
)
from app.services.gtfs.cli import run_register_feed, run_validate_archive
from app.services.gtfs.downloader import (
    download_gtfs_archive_to_file,
    download_gtfs_feed,
)
from app.services.gtfs.exceptions import (
    GTFSDownloadError,
    GTFSSecurityError,
    GTFSValidationError,
)


def _create_minimal_gtfs_zip(
    tables: dict[str, str] | None = None,
    exclude: set[str] | None = None,
) -> bytes:
    """Helper to generate an in-memory GTFS zip archive with specified tables."""
    default_tables = {
        "agency.txt": (
            "agency_id,agency_name,agency_url,agency_timezone\n"
            "DTC,Delhi Transport Corp,https://dtc.delhi.gov.in,Asia/Kolkata\n"
        ),
        "routes.txt": (
            "route_id,agency_id,route_short_name,route_long_name,route_type\n"
            "101,DTC,101,Route 101,3\n"
        ),
        "stops.txt": (
            "stop_id,stop_name,stop_lat,stop_lon\n"
            "S1,Stop 1,28.6139,77.2090\n"
            "S2,Stop 2,28.6200,77.2150\n"
        ),
        "trips.txt": ("route_id,service_id,trip_id\n101,DAILY,T101_1\n"),
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "T101_1,08:00:00,08:00:00,S1,1\n"
            "T101_1,08:15:00,08:15:00,S2,2\n"
        ),
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
            "start_date,end_date\n"
            "DAILY,1,1,1,1,1,1,1,20250101,20301231\n"
        ),
    }
    if tables:
        default_tables.update(tables)
    if exclude:
        for key in exclude:
            default_tables.pop(key, None)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, content in default_tables.items():
            zf.writestr(fname, content.encode("utf-8"))
    return buf.getvalue()


# -----------------------------------------------------------------------------
# 1. Configuration Validation Tests
# -----------------------------------------------------------------------------


def test_env_placeholder_detection() -> None:
    """Detect default insecure placeholder passwords in configuration."""
    insecure_passwords = [
        "replace_with_a_secure_password",
        "your_password_here",
        "",
        "   ",
    ]
    for pwd in insecure_passwords:
        is_placeholder = bool(
            not pwd.strip()
            or pwd.strip().startswith("replace_")
            or pwd.strip().startswith("your_")
        )
        assert is_placeholder, f"Expected {pwd!r} to be recognized as placeholder"

    safe_password = "K8x#mP9$vL2!qR5@"
    is_safe = not (
        not safe_password.strip()
        or safe_password.strip().startswith("replace_")
        or safe_password.strip().startswith("your_")
    )
    assert is_safe


def test_api_key_env_var_identifier_validation() -> None:
    """Ensure API key settings specify environment variable names, not raw secrets."""
    import re

    pattern = r"^[A-Za-z_][A-Za-z0-9_]*$"
    valid_names = ["DELHI_TRANSIT_API_KEY", "TRANSIT_KEY", "_PRIVATE_KEY", "KEY123"]
    for name in valid_names:
        assert re.fullmatch(pattern, name) is not None

    invalid_names = [
        "raw-secret-key-12345",
        "key with spaces",
        "123KEY",
        "https://example.com/api",
    ]
    for name in invalid_names:
        assert re.fullmatch(pattern, name) is None


# -----------------------------------------------------------------------------
# 2. Missing Archive Tests
# -----------------------------------------------------------------------------


def test_validate_archive_missing_file_raises_security_error(tmp_path: Path) -> None:
    """Validating a non-existent archive file raises an explicit GTFSSecurityError."""
    missing_file = tmp_path / "non_existent_feed.zip"
    with pytest.raises(GTFSSecurityError, match="does not exist"):
        validate_archive(missing_file)


def test_cli_validate_archive_missing_file_returns_nonzero(tmp_path: Path) -> None:
    """CLI validate-archive returns exit code 1 when the file is missing."""
    missing_file = tmp_path / "non_existent_feed.zip"
    args = Namespace(file=str(missing_file), expected_sha256=None)
    assert run_validate_archive(args) == 1


# -----------------------------------------------------------------------------
# 3. Checksum Verification Tests
# -----------------------------------------------------------------------------


def test_validate_archive_checksum_match(tmp_path: Path) -> None:
    """Validating an archive with matching SHA-256 succeeds."""
    archive_bytes = _create_minimal_gtfs_zip()
    archive_file = tmp_path / "feed.zip"
    archive_file.write_bytes(archive_bytes)

    actual_hash = compute_archive_sha256(archive_file)
    assert len(actual_hash) == 64

    # Case-insensitive match check
    tables = validate_archive(archive_file, expected_sha256=actual_hash.upper())
    assert len(tables) >= 5
    for req in REQUIRED_GTFS_FILES:
        assert req in tables


def test_validate_archive_checksum_mismatch(tmp_path: Path) -> None:
    """Validating an archive with mismatched SHA-256 raises GTFSSecurityError."""
    archive_bytes = _create_minimal_gtfs_zip()
    archive_file = tmp_path / "feed.zip"
    archive_file.write_bytes(archive_bytes)

    wrong_hash = "0000000000000000000000000000000000000000000000000000000000000000"
    with pytest.raises(GTFSSecurityError, match="checksum mismatch"):
        validate_archive(archive_file, expected_sha256=wrong_hash)


def test_cli_validate_archive_checksum_mismatch_returns_nonzero(tmp_path: Path) -> None:
    """CLI validate-archive returns 1 on checksum mismatch."""
    archive_bytes = _create_minimal_gtfs_zip()
    archive_file = tmp_path / "feed.zip"
    archive_file.write_bytes(archive_bytes)

    wrong_hash = "1111111111111111111111111111111111111111111111111111111111111111"
    args = Namespace(file=str(archive_file), expected_sha256=wrong_hash)
    assert run_validate_archive(args) == 1


# -----------------------------------------------------------------------------
# 4. ZIP Integrity & Required Schema Tables Tests
# -----------------------------------------------------------------------------


def test_validate_archive_corrupt_zip(tmp_path: Path) -> None:
    """Corrupted binary data raises GTFSSecurityError."""
    corrupt_file = tmp_path / "corrupt.zip"
    corrupt_file.write_bytes(b"PK\x03\x04This is not a real zip archive file.")

    with pytest.raises(GTFSSecurityError, match="corrupted ZIP archive"):
        validate_archive(corrupt_file)


def test_validate_archive_missing_required_gtfs_tables(tmp_path: Path) -> None:
    """An archive missing mandatory tables raises GTFSValidationError."""
    incomplete_bytes = _create_minimal_gtfs_zip(exclude={"stop_times.txt", "trips.txt"})
    incomplete_file = tmp_path / "incomplete.zip"
    incomplete_file.write_bytes(incomplete_bytes)

    with pytest.raises(GTFSValidationError) as exc_info:
        validate_archive(incomplete_file)

    msg = str(exc_info.value)
    assert "missing required GTFS files" in msg
    assert "stop_times.txt" in msg
    assert "trips.txt" in msg


def test_cli_validate_archive_incomplete_returns_nonzero(tmp_path: Path) -> None:
    """CLI validate-archive returns 1 when required tables are missing."""
    incomplete_bytes = _create_minimal_gtfs_zip(exclude={"agency.txt"})
    incomplete_file = tmp_path / "no_agency.zip"
    incomplete_file.write_bytes(incomplete_bytes)

    args = Namespace(file=str(incomplete_file), expected_sha256=None)
    assert run_validate_archive(args) == 1


# -----------------------------------------------------------------------------
# 5. Failed Download & Partial File Cleanup Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_http_error_raises_gtfs_download_error() -> None:
    """HTTP 404 or 500 error raises a clean GTFSDownloadError."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient.stream", return_value=mock_stream):
        with pytest.raises(GTFSDownloadError, match="HTTP 404"):
            await download_gtfs_feed("https://example.com/missing.zip")


@pytest.mark.asyncio
async def test_download_network_timeout_raises_gtfs_download_error() -> None:
    """Network timeout raises GTFSDownloadError."""
    with patch(
        "httpx.AsyncClient.stream",
        side_effect=httpx.TimeoutException("Connection timed out"),
    ):
        with pytest.raises(GTFSDownloadError, match="timed out"):
            await download_gtfs_feed(
                "https://example.com/feed.zip", timeout_seconds=5.0
            )


@pytest.mark.asyncio
async def test_download_to_file_removes_partial_on_failure(tmp_path: Path) -> None:
    """When download_gtfs_archive_to_file fails, the .part temporary file is deleted."""
    dest_file = tmp_path / "feed.zip"
    part_file = tmp_path / "feed.zip.part"

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient.stream", return_value=mock_stream):
        with pytest.raises(GTFSDownloadError):
            await download_gtfs_archive_to_file(
                "https://example.com/server_error.zip",
                destination=dest_file,
            )

    assert not dest_file.exists()
    assert not part_file.exists()


@pytest.mark.asyncio
async def test_download_to_file_success_atomic_replacement(tmp_path: Path) -> None:
    """Successful download writes archive content and cleans temporary file."""
    dest_file = tmp_path / "feed.zip"
    content = _create_minimal_gtfs_zip()

    async def mock_aiter():
        yield content

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-length": str(len(content))}
    mock_response.aiter_bytes = mock_aiter

    mock_stream = MagicMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient.stream", return_value=mock_stream):
        result = await download_gtfs_archive_to_file(
            "https://example.com/valid.zip",
            destination=dest_file,
        )

    assert result == dest_file
    assert dest_file.exists()
    assert dest_file.read_bytes() == content
    assert not (tmp_path / "feed.zip.part").exists()


# -----------------------------------------------------------------------------
# 6. Idempotent Feed Registration Tests
# -----------------------------------------------------------------------------


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


def _feed_args(
    slug: str = "idempotent-city",
    city_name: str = "Idempotent City",
    allow_existing: bool = False,
) -> Namespace:
    return Namespace(
        slug=slug,
        city_name=city_name,
        static_url="https://agency.example/gtfs.zip",
        vehicle_positions_url="",
        trip_updates_url="",
        alerts_url="",
        api_key_env_var="",
        api_key_query_param="",
        enable_live_tracking=False,
        allow_existing=allow_existing,
    )


@pytest.mark.asyncio
async def test_register_feed_idempotent_with_allow_existing(
    async_test_session: AsyncSession,
) -> None:
    """Calling run_register_feed with --allow-existing succeeds idempotently."""
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=async_test_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.gtfs.cli.async_session_factory", mock_factory):
        # 1. First registration succeeds
        rc1 = await run_register_feed(_feed_args(allow_existing=True))
        assert rc1 == 0

        # 2. Second registration with allow_existing=True succeeds idempotently
        rc2 = await run_register_feed(
            _feed_args(city_name="Modified City Name", allow_existing=True)
        )
        assert rc2 == 0

        # 3. Repeated registration without allow_existing returns 1
        rc3 = await run_register_feed(_feed_args(allow_existing=False))
        assert rc3 == 1

    # Verify exactly one feed exists and original name was preserved
    feeds = (
        (
            await async_test_session.execute(
                select(TransitFeed).where(TransitFeed.slug == "idempotent-city")
            )
        )
        .scalars()
        .all()
    )
    assert len(feeds) == 1
    assert feeds[0].city_name == "Idempotent City"
