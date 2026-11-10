"""WaitWatch API — Pydantic schemas."""

from app.schemas.health import HealthResponse
from app.schemas.transit import (
    FeedDetailResponse,
    FeedSummaryResponse,
    ItemEnvelope,
    NearbyStopResponse,
    PaginatedResponse,
    PaginationMeta,
    RouteDetailResponse,
    RouteResponse,
    StopDetailResponse,
    StopResponse,
)

__all__ = [
    "FeedDetailResponse",
    "FeedSummaryResponse",
    "HealthResponse",
    "ItemEnvelope",
    "NearbyStopResponse",
    "PaginatedResponse",
    "PaginationMeta",
    "RouteDetailResponse",
    "RouteResponse",
    "StopDetailResponse",
    "StopResponse",
]
