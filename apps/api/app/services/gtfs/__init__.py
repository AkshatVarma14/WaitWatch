"""GTFS Static Ingestion Service package."""

from app.services.gtfs.archive import (
    DEFAULT_MAX_ARCHIVE_BYTES,
    DEFAULT_MAX_COMPRESSION_RATIO,
    DEFAULT_MAX_FILE_COUNT,
    DEFAULT_MAX_UNCOMPRESSED_BYTES,
    extract_gtfs_tables,
    validate_zip_safety,
)
from app.services.gtfs.downloader import download_gtfs_feed, mask_url_credentials
from app.services.gtfs.exceptions import (
    GTFSDownloadError,
    GTFSIngestionError,
    GTFSPersistenceError,
    GTFSSecurityError,
    GTFSValidationError,
)
from app.services.gtfs.importer import IngestionStats, persist_feed_data
from app.services.gtfs.parser import (
    ParsedAgency,
    ParsedCalendar,
    ParsedCalendarDate,
    ParsedFeedData,
    ParsedRoute,
    ParsedStop,
    ParsedStopTime,
    ParsedTrip,
    parse_gtfs_tables,
)
from app.services.gtfs.service import GTFSIngestionService

__all__ = [
    "DEFAULT_MAX_ARCHIVE_BYTES",
    "DEFAULT_MAX_COMPRESSION_RATIO",
    "DEFAULT_MAX_FILE_COUNT",
    "DEFAULT_MAX_UNCOMPRESSED_BYTES",
    "GTFSDownloadError",
    "GTFSIngestionError",
    "GTFSIngestionService",
    "GTFSPersistenceError",
    "GTFSSecurityError",
    "GTFSValidationError",
    "IngestionStats",
    "ParsedAgency",
    "ParsedCalendar",
    "ParsedCalendarDate",
    "ParsedFeedData",
    "ParsedRoute",
    "ParsedStop",
    "ParsedStopTime",
    "ParsedTrip",
    "download_gtfs_feed",
    "extract_gtfs_tables",
    "mask_url_credentials",
    "parse_gtfs_tables",
    "persist_feed_data",
    "validate_zip_safety",
]
