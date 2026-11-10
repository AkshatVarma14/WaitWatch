"""Safe in-memory ZIP archive extraction and validation for GTFS feeds."""

import io
import os
import posixpath
import zipfile
from pathlib import Path

from app.services.gtfs.exceptions import GTFSSecurityError

# Safety thresholds for GTFS ZIP archives
DEFAULT_MAX_ARCHIVE_BYTES: int = 100 * 1024 * 1024  # 100 MB
DEFAULT_MAX_UNCOMPRESSED_BYTES: int = 500 * 1024 * 1024  # 500 MB
DEFAULT_MAX_COMPRESSION_RATIO: float = 100.0  # 100:1 ratio limit
DEFAULT_MAX_FILE_COUNT: int = 100

KNOWN_GTFS_FILES: frozenset[str] = frozenset(
    {
        "agency.txt",
        "routes.txt",
        "stops.txt",
        "trips.txt",
        "stop_times.txt",
        "calendar.txt",
        "calendar_dates.txt",
        "fare_attributes.txt",
        "fare_rules.txt",
        "shapes.txt",
        "frequencies.txt",
        "transfers.txt",
        "pathways.txt",
        "levels.txt",
        "feed_info.txt",
        "attributions.txt",
        "translations.txt",
    }
)


def _validate_entry_path(filename: str) -> str:
    """Validate entry filename against path traversal and malicious characters.

    Returns the normalized basename for matching GTFS tables.
    """
    if "\x00" in filename:
        raise GTFSSecurityError(
            f"Archive entry contains illegal null byte: {filename!r}"
        )

    # Reject absolute paths (POSIX and Windows)
    if (
        filename.startswith(("/", "\\"))
        or os.path.isabs(filename)
        or (len(filename) > 1 and filename[1] == ":")
    ):
        raise GTFSSecurityError(f"Archive entry contains absolute path: {filename!r}")

    # Normalize posix path and check for directory traversal
    norm = posixpath.normpath(filename.replace("\\", "/"))
    parts = norm.split("/")
    if ".." in parts:
        raise GTFSSecurityError(
            f"Archive entry contains directory traversal: {filename!r}"
        )

    return posixpath.basename(norm).lower()


def validate_zip_safety(
    archive: zipfile.ZipFile,
    *,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
    max_file_count: int = DEFAULT_MAX_FILE_COUNT,
) -> None:
    """Validate archive against decompression bombs, path traversal, and encryption.

    Raises:
        GTFSSecurityError: If any security constraint is violated.
    """
    entries = archive.infolist()

    if len(entries) > max_file_count:
        raise GTFSSecurityError(
            f"Archive contains {len(entries)} entries, exceeding limit {max_file_count}"
        )

    total_uncompressed = 0

    for info in entries:
        # Check for encryption flag (bit 0 of flag_bits)
        if info.flag_bits & 0x1:
            raise GTFSSecurityError(
                f"Encrypted archive entries are not permitted: {info.filename}"
            )

        # Check path traversal
        _validate_entry_path(info.filename)

        total_uncompressed += info.file_size
        if total_uncompressed > max_uncompressed_bytes:
            raise GTFSSecurityError(
                f"Total uncompressed size ({total_uncompressed} bytes) exceeds limit "
                f"({max_uncompressed_bytes} bytes)"
            )

        # Compression ratio check (protect against zip bombs like 42.zip)
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > max_compression_ratio:
                raise GTFSSecurityError(
                    f"Suspicious compression ratio {ratio:.1f}:1 for entry "
                    f"{info.filename!r} (maximum allowed: {max_compression_ratio}:1)"
                )


def extract_gtfs_tables(
    source: bytes | io.BytesIO | Path | str,
    *,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
    max_file_count: int = DEFAULT_MAX_FILE_COUNT,
) -> dict[str, str]:
    """Safely inspect and extract GTFS text tables in memory.

    Args:
        source: Archive bytes, BytesIO, or file path.
        max_archive_bytes: Maximum allowed compressed archive size in bytes.
        max_uncompressed_bytes: Maximum allowed uncompressed size in bytes.
        max_compression_ratio: Maximum allowed compression ratio.
        max_file_count: Maximum entries allowed in archive.

    Returns:
        dict[str, str]: Mapping of lowercase GTFS table name (e.g. 'agency.txt')
                        to its decoded UTF-8 string content.

    Raises:
        GTFSSecurityError: If safety bounds are violated or zip is invalid.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_file():
            raise GTFSSecurityError(f"Archive file does not exist: {path}")
        size = path.stat().st_size
        if size > max_archive_bytes:
            raise GTFSSecurityError(
                f"Archive file size ({size} B) exceeds limit ({max_archive_bytes} B)"
            )
        file_obj: io.BytesIO | Path = path
    elif isinstance(source, bytes):
        if len(source) > max_archive_bytes:
            raise GTFSSecurityError(
                f"Archive buffer size ({len(source)} B) exceeds limit "
                f"({max_archive_bytes} B)"
            )
        file_obj = io.BytesIO(source)
    else:
        file_obj = source

    try:
        with zipfile.ZipFile(file_obj, mode="r") as archive:
            validate_zip_safety(
                archive,
                max_uncompressed_bytes=max_uncompressed_bytes,
                max_compression_ratio=max_compression_ratio,
                max_file_count=max_file_count,
            )

            tables: dict[str, str] = {}
            for info in archive.infolist():
                if info.is_dir():
                    continue
                basename = _validate_entry_path(info.filename)
                if basename in KNOWN_GTFS_FILES:
                    content_bytes = archive.read(info)
                    # Use utf-8-sig to automatically strip BOM if present
                    tables[basename] = content_bytes.decode("utf-8-sig")

            return tables
    except zipfile.BadZipFile as exc:
        raise GTFSSecurityError(f"Invalid or corrupted ZIP archive: {exc}") from exc
