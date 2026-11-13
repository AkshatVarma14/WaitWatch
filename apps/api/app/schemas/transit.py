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

    id: int = Field(..., description="Internal database feed identifier")
    city_name: str = Field(..., description="City or region name")
    slug: str = Field(..., description="URL-safe feed identifier")
    feed_status: str = Field(..., description="Operational status (e.g. active)")
    is_live_tracking_enabled: bool = Field(
        ..., description="Whether live vehicle tracking is enabled"
    )
    last_static_import_at: datetime | None = Field(
        None, description="Timestamp of last static schedule import"
    )
    last_realtime_poll_at: datetime | None = Field(
        None, description="Timestamp of last real-time poll"
    )


class FeedDetailResponse(FeedSummaryResponse):
    """Full detail of a transit feed / city configuration."""

    static_gtfs_url: str | None = Field(
        None, description="Static GTFS feed URL, when available"
    )
    realtime_vehicle_positions_url: str | None = Field(
        None, description="GTFS-RT VehiclePositions URL"
    )
    realtime_trip_updates_url: str | None = Field(
        None, description="GTFS-RT TripUpdates URL"
    )
    realtime_alerts_url: str | None = Field(
        None, description="GTFS-RT ServiceAlerts URL"
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


class StopArrivalPrediction(BaseModel):
    """Predicted arrival for a trip/vehicle at a specific stop."""

    model_config = ConfigDict(from_attributes=True)

    feed_slug: str = Field(..., description="Feed slug identifier")
    feed_id: int = Field(..., description="Feed internal database identifier")
    stop_id: str = Field(..., description="GTFS stop identifier")
    trip_id: str = Field(..., description="GTFS trip identifier")
    route_id: str = Field(..., description="GTFS route identifier")
    route_short_name: str | None = Field(None, description="Public route short name")
    trip_headsign: str | None = Field(None, description="Trip headsign")
    vehicle_id: str | None = Field(None, description="Agency vehicle identifier")
    stop_sequence: int = Field(..., description="Stop sequence on this trip")
    scheduled_arrival_time: datetime = Field(
        ..., description="Scheduled arrival timestamp in UTC"
    )
    estimated_arrival_time: datetime = Field(
        ..., description="Estimated arrival timestamp in UTC"
    )
    delay_seconds: int = Field(
        0,
        description="Estimated delay in seconds (positive=late, 0=on time)",
    )
    prediction_source: str = Field(
        ...,
        description=(
            "Source of prediction ('SCHEDULE_ONLY', "
            "'HISTORY_ADJUSTED', or 'TRIP_UPDATE')"
        ),
    )
    source_observation_time: datetime | None = Field(
        None,
        description="Timestamp of the vehicle telemetry observation in UTC",
    )


class ShapePointResponse(BaseModel):
    """Geographic point in a GTFS shape."""

    model_config = ConfigDict(from_attributes=True)

    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 longitude")
    sequence: int = Field(..., ge=0, description="Point sequence within shape")
    distance_traveled: float | None = Field(
        None, description="Distance traveled along shape in feed units"
    )


class RouteShapeResponse(BaseModel):
    """Ordered shape polyline associated with a route."""

    model_config = ConfigDict(from_attributes=True)

    shape_id: str = Field(..., description="GTFS shape identifier")
    points: list[ShapePointResponse] = Field(
        default_factory=list, description="Chronologically ordered shape points"
    )


class RouteMapStopResponse(BaseModel):
    """Stop served by the route with sequence and coordinates."""

    model_config = ConfigDict(from_attributes=True)

    stop_id: str = Field(..., description="GTFS stop identifier")
    name: str = Field(..., description="Stop or station name")
    code: str | None = Field(None, description="Passenger-facing stop code")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 longitude")
    stop_sequence: int = Field(..., ge=0, description="Sequence on route trip")
    direction_id: int | None = Field(None, description="Travel direction identifier")
    wheelchair_boarding: int = Field(
        0, description="0=no info, 1=accessible, 2=not accessible"
    )


class RouteMapVehicleResponse(BaseModel):
    """Active vehicle position on this route."""

    model_config = ConfigDict(from_attributes=True)

    entity_id: str = Field(..., description="Realtime vehicle entity identifier")
    vehicle_id: str | None = Field(None, description="Agency vehicle identifier")
    vehicle_label: str | None = Field(
        None, description="Passenger-facing vehicle label"
    )
    route_id: str | None = Field(None, description="Provider route identifier")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 longitude")
    bearing: float | None = Field(
        None, ge=0.0, le=360.0, description="Heading in degrees"
    )
    speed: float | None = Field(None, ge=0.0, description="Speed in meters/second")
    current_status: int | None = Field(
        None, description="0=incoming, 1=stopped, 2=in_transit"
    )
    trip_id: str | None = Field(None, description="GTFS trip identifier")
    observed_at: datetime = Field(..., description="Observation timestamp in UTC")


class RouteMapResponse(BaseModel):
    """Payload for rendering route geometry, stops, and active vehicles on a map."""

    model_config = ConfigDict(from_attributes=True)

    feed_slug: str = Field(..., description="Feed slug identifier")
    route_id: str = Field(..., description="GTFS route identifier")
    route_short_name: str | None = Field(None, description="Public route short name")
    route_long_name: str | None = Field(None, description="Public route long name")
    route_color: str | None = Field(None, description="Hex color code (e.g. #0055A5)")
    text_color: str | None = Field(None, description="Hex text color code")
    shapes: list[RouteShapeResponse] = Field(
        default_factory=list,
        description="True GTFS shapes; empty list if shapes.txt is unavailable",
    )
    stops: list[RouteMapStopResponse] = Field(
        default_factory=list,
        description="Ordered stops served along this route",
    )
    vehicles: list[RouteMapVehicleResponse] = Field(
        default_factory=list,
        description="Fresh active vehicles currently assigned to this route",
    )


class StopPlanDetailResponse(BaseModel):
    """Origin or destination stop timing and details for an itinerary."""

    model_config = ConfigDict(from_attributes=True)

    stop_id: str = Field(..., description="GTFS stop identifier")
    name: str = Field(..., description="Stop or station name")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 longitude")
    stop_sequence: int = Field(..., ge=0, description="Stop sequence on trip")
    scheduled_time: str = Field(..., description="Scheduled time in HH:MM:SS format")
    estimated_time: str = Field(
        ...,
        description="Real-time adjusted or scheduled time in HH:MM:SS format",
    )
    delay_seconds: int | None = Field(
        None, description="Delay in seconds if real-time update available"
    )


class TripItineraryResponse(BaseModel):
    """A direct scheduled journey option between origin and destination."""

    model_config = ConfigDict(from_attributes=True)

    route_id: str = Field(..., description="GTFS route identifier")
    route_short_name: str | None = Field(
        None, description="Route short name (e.g. '10')"
    )
    route_long_name: str | None = Field(None, description="Route long name")
    route_color: str | None = Field(None, description="Route display color hex")
    text_color: str | None = Field(None, description="Route text display color hex")
    route_type: int = Field(..., description="GTFS route type")
    trip_id: str = Field(..., description="GTFS trip identifier")
    trip_headsign: str | None = Field(
        None, description="Passenger-facing trip headsign"
    )
    direction_id: int | None = Field(None, description="Direction of travel")

    origin: StopPlanDetailResponse = Field(
        ..., description="Origin stop details and departure time"
    )
    destination: StopPlanDetailResponse = Field(
        ..., description="Destination stop details and arrival time"
    )
    duration_minutes: int = Field(
        ..., ge=0, description="Estimated total trip duration in minutes"
    )
    intermediate_stops_count: int = Field(
        ...,
        ge=0,
        description="Number of intermediate stops between origin and destination",
    )
    realtime_status: str = Field(
        ...,
        description=(
            "Real-time delay status: SCHEDULED, REALTIME_ON_TIME, "
            "REALTIME_DELAYED, REALTIME_EARLY"
        ),
    )


class TripPlanResponse(BaseModel):
    """Direct trip plan response containing itineraries between two stops."""

    model_config = ConfigDict(from_attributes=True)

    feed_slug: str = Field(..., description="Feed slug identifier")
    origin_stop_id: str = Field(..., description="Origin GTFS stop identifier")
    destination_stop_id: str = Field(
        ..., description="Destination GTFS stop identifier"
    )
    target_date: str = Field(..., description="Target travel date in YYYY-MM-DD format")
    target_time: str = Field(
        ..., description="Target departure time in HH:MM:SS format"
    )
    itineraries: list[TripItineraryResponse] = Field(
        default_factory=list,
        description="Direct itineraries ordered by departure time",
    )
