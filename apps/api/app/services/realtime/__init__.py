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
    ParsedStopTimeEvent,
    ParsedStopTimeUpdate,
    ParsedTripUpdate,
    ParsedTripUpdatesFeed,
    ParsedVehiclePosition,
    parse_trip_updates,
    parse_vehicle_positions,
)
from app.services.realtime.query import get_recent_observations
from app.services.realtime.service import VehiclePositionIngestionService
from app.services.realtime.trip_update_service import TripUpdateIngestionService

__all__ = [
    "DEFAULT_MAX_REALTIME_BYTES",
    "DEFAULT_REALTIME_TIMEOUT_SECONDS",
    "ParsedRealtimeFeed",
    "ParsedStopTimeEvent",
    "ParsedStopTimeUpdate",
    "ParsedTripUpdate",
    "ParsedTripUpdatesFeed",
    "ParsedVehiclePosition",
    "RealtimeDownloadError",
    "RealtimeError",
    "RealtimeParseError",
    "RealtimePersistenceError",
    "TripUpdateIngestionService",
    "UnsupportedIncrementalityError",
    "VehiclePositionIngestionService",
    "download_realtime_feed",
    "get_recent_observations",
    "parse_trip_updates",
    "parse_vehicle_positions",
]
