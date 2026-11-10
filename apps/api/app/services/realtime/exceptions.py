"""Exceptions for GTFS-Realtime vehicle position ingestion."""


class RealtimeError(Exception):
    """Base exception for all GTFS-Realtime operations."""

    pass


class RealtimeDownloadError(RealtimeError):
    """Raised when fetching a realtime feed fails, times out, or exceeds limits."""

    pass


class RealtimeParseError(RealtimeError):
    """Raised when parsing or validating a GTFS-Realtime message fails."""

    pass


class UnsupportedIncrementalityError(RealtimeParseError):
    """Raised when feed incrementality is DIFFERENTIAL or unsupported."""

    pass


class RealtimePersistenceError(RealtimeError):
    """Raised when database snapshot persistence fails."""

    pass
