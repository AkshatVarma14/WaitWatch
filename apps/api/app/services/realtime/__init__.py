"""WaitWatch GTFS-Realtime processing package."""

from app.services.realtime.downloader import (
    DEFAULT_MAX_REALTIME_BYTES,
    DEFAULT_REALTIME_TIMEOUT_SECONDS,
    download_realtime_feed,
)
from app.services.realtime.exceptions import (
    RealtimeDownloadError,
    RealtimeError,
    RealtimeParseError,
    RealtimePersistenceError,
    UnsupportedIncrementalityError,
)
from app.services.realtime.parser import (
    ParsedRealtimeFeed,
    ParsedVehiclePosition,
    parse_vehicle_positions,
)
from app.services.realtime.service import VehiclePositionIngestionService

__all__ = [
    "DEFAULT_MAX_REALTIME_BYTES",
    "DEFAULT_REALTIME_TIMEOUT_SECONDS",
    "ParsedRealtimeFeed",
    "ParsedVehiclePosition",
    "RealtimeDownloadError",
    "RealtimeError",
    "RealtimeParseError",
    "RealtimePersistenceError",
    "UnsupportedIncrementalityError",
    "VehiclePositionIngestionService",
    "download_realtime_feed",
    "parse_vehicle_positions",
]
