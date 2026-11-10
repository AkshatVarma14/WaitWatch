"""GTFS Ingestion Exceptions."""


class GTFSIngestionError(Exception):
    """Base exception for all GTFS ingestion errors."""

    pass


class GTFSSecurityError(GTFSIngestionError):
    """Raised when an archive fails security validations (zip bomb, traversal, etc)."""

    pass


class GTFSDownloadError(GTFSIngestionError):
    """Raised when downloading a feed archive fails (network, status code, size)."""

    pass


class GTFSValidationError(GTFSIngestionError):
    """Raised when GTFS CSV files violate syntax, schema, or relational constraints."""

    pass


class GTFSPersistenceError(GTFSIngestionError):
    """Raised when persisting transit records to the database fails."""

    pass
