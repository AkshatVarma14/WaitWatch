"""WaitWatch API — Transit route, stop, and feed exploration schemas."""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Metadata describing a paginated collection."""

    total: int = Field(..., ge=0, description="Total matching records")
    page: int = Field(..., ge=1, description="Current page number (1-based)")
    page_size: int = Field(..., ge=1, le=100, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")
    has_next: bool = Field(..., description="Whether a next page exists")
    has_prev: bool = Field(..., description="Whether a previous page exists")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard envelope for paginated collection responses."""

    data: list[T]
    pagination: PaginationMeta


class ItemEnvelope(BaseModel, Generic[T]):
    """Standard envelope for single item responses."""

    data: T


class FeedSummaryResponse(BaseModel):
    """Summary of a configured transit feed / city."""

    model_config = ConfigDict(from_attributes=True)

    city_name: str = Field(..., description="City or region name")
    slug: str = Field(..., description="URL-safe feed identifier")
    feed_status: str = Field(..., description="Operational status (e.g. active)")
    is_live_tracking_enabled: bool = Field(
        ..., description="Whether live vehicle tracking is enabled"
    )
    last_static_import_at: datetime | None = Field(
        None, description="Timestamp of last static schedule import"
    )


class FeedDetailResponse(FeedSummaryResponse):
    """Full detail of a transit feed / city configuration."""

    static_gtfs_url: str = Field(..., description="Static GTFS feed URL")
    realtime_vehicle_positions_url: str | None = Field(
        None, description="GTFS-RT VehiclePositions URL"
    )
    realtime_trip_updates_url: str | None = Field(
        None, description="GTFS-RT TripUpdates URL"
    )
    realtime_alerts_url: str | None = Field(
        None, description="GTFS-RT ServiceAlerts URL"
    )
    last_realtime_poll_at: datetime | None = Field(
        None, description="Timestamp of last real-time poll"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class RouteResponse(BaseModel):
    """Public GTFS route summary."""

    model_config = ConfigDict(from_attributes=True)

    route_id: str = Field(..., description="GTFS route identifier")
    agency_id: str | None = Field(None, description="GTFS agency identifier if present")
    short_name: str | None = Field(
        None, description="Public route short name (e.g. '10')"
    )
    long_name: str | None = Field(
        None, description="Public route full descriptive name"
    )
    description: str | None = Field(None, description="Route description")
    route_type: int = Field(
        ..., description="GTFS route type (0=tram, 1=subway, 2=rail, 3=bus, etc.)"
    )
    route_url: str | None = Field(
        None, description="URL with information about this route"
    )
    route_color: str | None = Field(
        None, description="Hex color code for route display"
    )
    text_color: str | None = Field(
        None, description="Hex color code for route text display"
    )
    sort_order: int | None = Field(None, description="Display ordering index")


class RouteDetailResponse(RouteResponse):
    """Detailed GTFS route with agency details."""

    agency_name: str | None = Field(None, description="Operating agency name")
    agency_url: str | None = Field(None, description="Operating agency website")
    agency_timezone: str | None = Field(None, description="Agency IANA timezone")


class StopResponse(BaseModel):
    """Public GTFS stop summary."""

    model_config = ConfigDict(from_attributes=True)

    stop_id: str = Field(..., description="GTFS stop identifier")
    code: str | None = Field(None, description="Passenger-facing stop code")
    name: str = Field(..., description="Stop or station name")
    description: str | None = Field(None, description="Stop description")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 longitude")
    parent_station_id: str | None = Field(
        None, description="GTFS parent station stop_id"
    )
    location_type: int = Field(
        0, description="0=stop/platform, 1=station, 2=entrance/exit"
    )
    wheelchair_boarding: int = Field(
        0, description="0=no info, 1=accessible, 2=not accessible"
    )
    platform_code: str | None = Field(
        None, description="Platform identifier or track number"
    )
    timezone: str | None = Field(
        None, description="Stop timezone if different from agency"
    )


class StopDetailResponse(StopResponse):
    """Detailed GTFS stop."""

    pass


class NearbyStopResponse(StopResponse):
    """GTFS stop with computed distance from reference coordinates."""

    distance_meters: float = Field(
        ..., ge=0.0, description="Distance in meters from search point"
    )
