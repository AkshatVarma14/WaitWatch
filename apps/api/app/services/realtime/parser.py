"""GTFS-Realtime Protocol Buffer parser and validator."""

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from app.services.realtime.exceptions import (
    RealtimeParseError,
    UnsupportedIncrementalityError,
)

logger = logging.getLogger(__name__)

# Maximum plausible timestamp: year 2100 in epoch seconds
MAX_TIMESTAMP_SECONDS = 4102444800


@dataclass(frozen=True, slots=True)
class ParsedVehiclePosition:
    """Validated in-memory vehicle position record from GTFS-Realtime."""

    entity_id: str
    latitude: float
    longitude: float
    vehicle_id: str | None = None
    vehicle_label: str | None = None
    license_plate: str | None = None
    trip_id: str | None = None
    route_id: str | None = None
    direction_id: int | None = None
    start_time: str | None = None
    start_date: str | None = None
    schedule_relationship: int | None = None
    stop_id: str | None = None
    current_stop_sequence: int | None = None
    current_status: int | None = None
    bearing: float | None = None
    odometer: float | None = None
    speed: float | None = None
    congestion_level: int | None = None
    occupancy_status: int | None = None
    occupancy_percentage: int | None = None
    vehicle_timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class ParsedRealtimeFeed:
    """Validated feed message containing header metadata and vehicle positions."""

    gtfs_realtime_version: str
    feed_timestamp: datetime | None
    vehicles: list[ParsedVehiclePosition]


def parse_vehicle_positions(payload: bytes) -> ParsedRealtimeFeed:
    """Decode and validate a GTFS-Realtime Protocol Buffer payload.

    Args:
        payload: Raw protobuf bytes from the GTFS-RT endpoint.

    Returns:
        ParsedRealtimeFeed: Container with validated header and vehicle records.

    Raises:
        RealtimeParseError: On invalid protobuf syntax, duplicate entities,
            or corrupted/out-of-bounds coordinates.
        UnsupportedIncrementalityError: If the feed uses DIFFERENTIAL mode.
    """
    if not payload:
        raise RealtimeParseError("Received empty payload for GTFS-Realtime feed")

    feed_message = gtfs_realtime_pb2.FeedMessage()
    try:
        feed_message.ParseFromString(payload)
    except DecodeError as exc:
        raise RealtimeParseError(
            f"Failed to decode protobuf FeedMessage: {exc}"
        ) from exc
    except Exception as exc:
        raise RealtimeParseError(f"Corrupted GTFS-Realtime message: {exc}") from exc

    # 1. Validate FeedHeader
    if not feed_message.HasField("header"):
        raise RealtimeParseError("FeedMessage missing required FeedHeader")

    header = feed_message.header
    version = header.gtfs_realtime_version
    if not version:
        raise RealtimeParseError("FeedHeader missing gtfs_realtime_version")

    # Incrementality validation: Reject DIFFERENTIAL feeds cleanly
    incrementality = header.incrementality
    if incrementality == gtfs_realtime_pb2.FeedHeader.Incrementality.DIFFERENTIAL:
        raise UnsupportedIncrementalityError(
            "DIFFERENTIAL incrementality is not supported; only FULL_DATASET accepted"
        )
    if incrementality != gtfs_realtime_pb2.FeedHeader.Incrementality.FULL_DATASET:
        raise UnsupportedIncrementalityError(
            f"Unsupported feed incrementality mode: {incrementality}"
        )

    # Feed header timestamp (timezone-aware UTC)
    feed_timestamp: datetime | None = None
    if header.HasField("timestamp") and header.timestamp > 0:
        if header.timestamp > MAX_TIMESTAMP_SECONDS:
            raise RealtimeParseError(
                f"FeedHeader timestamp {header.timestamp} is unreasonably far in future"
            )
        try:
            feed_timestamp = datetime.fromtimestamp(header.timestamp, tz=UTC)
        except (ValueError, OverflowError, OSError) as exc:
            raise RealtimeParseError(f"Invalid FeedHeader timestamp: {exc}") from exc

    # 2. Validate FeedEntities and extract vehicle positions
    seen_entity_ids: set[str] = set()
    vehicles: list[ParsedVehiclePosition] = []

    for entity in feed_message.entity:
        entity_id = entity.id
        if not entity_id or not entity_id.strip():
            raise RealtimeParseError("FeedEntity missing required identifier")

        entity_id = entity_id.strip()
        if entity_id in seen_entity_ids:
            raise RealtimeParseError(
                f"Duplicate entity ID found in feed: '{entity_id}'"
            )
        seen_entity_ids.add(entity_id)

        # Ignore deleted entities or entities without vehicle positions
        # (e.g. trip updates or alerts if included in combined feeds)
        if entity.is_deleted or not entity.HasField("vehicle"):
            continue

        vp = entity.vehicle

        # Position data is mandatory for vehicle positions
        if not vp.HasField("position"):
            raise RealtimeParseError(
                f"Vehicle entity '{entity_id}' missing required position data"
            )

        pos = vp.position
        lat = pos.latitude
        lon = pos.longitude

        if not (math.isfinite(lat) and math.isfinite(lon)):
            raise RealtimeParseError(
                f"Non-finite coordinates for vehicle '{entity_id}': "
                f"lat={lat}, lon={lon}"
            )

        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            raise RealtimeParseError(
                f"Coordinates out of bounds for vehicle '{entity_id}': "
                f"lat={lat}, lon={lon}"
            )

        # Bearing validation: degrees clockwise from North [0.0, 360.0]
        bearing: float | None = None
        if pos.HasField("bearing"):
            if not math.isfinite(pos.bearing) or not (0.0 <= pos.bearing <= 360.0):
                raise RealtimeParseError(
                    f"Invalid bearing for vehicle entity '{entity_id}': {pos.bearing}"
                )
            bearing = float(pos.bearing)

        # Speed validation: meters per second >= 0
        speed: float | None = None
        if pos.HasField("speed"):
            if not math.isfinite(pos.speed) or pos.speed < 0.0:
                raise RealtimeParseError(
                    f"Invalid speed for vehicle entity '{entity_id}': {pos.speed}"
                )
            speed = float(pos.speed)

        # Odometer validation: meters >= 0
        odometer: float | None = None
        if pos.HasField("odometer"):
            if not math.isfinite(pos.odometer) or pos.odometer < 0.0:
                raise RealtimeParseError(
                    f"Invalid odometer for vehicle entity '{entity_id}': {pos.odometer}"
                )
            odometer = float(pos.odometer)

        # Vehicle timestamp (distinct from feed header timestamp)
        vehicle_timestamp: datetime | None = None
        if vp.HasField("timestamp") and vp.timestamp > 0:
            if vp.timestamp > MAX_TIMESTAMP_SECONDS:
                raise RealtimeParseError(
                    f"Vehicle timestamp {vp.timestamp} for '{entity_id}' is invalid"
                )
            try:
                vehicle_timestamp = datetime.fromtimestamp(vp.timestamp, tz=UTC)
            except (ValueError, OverflowError, OSError) as exc:
                raise RealtimeParseError(
                    f"Invalid vehicle timestamp for entity '{entity_id}': {exc}"
                ) from exc

        # VehicleDescriptor fields
        vehicle_id: str | None = None
        vehicle_label: str | None = None
        license_plate: str | None = None
        if vp.HasField("vehicle"):
            v_desc = vp.vehicle
            vehicle_id = v_desc.id.strip() if v_desc.id else None
            vehicle_label = v_desc.label.strip() if v_desc.label else None
            license_plate = (
                v_desc.license_plate.strip() if v_desc.license_plate else None
            )

        # TripDescriptor fields
        trip_id: str | None = None
        route_id: str | None = None
        direction_id: int | None = None
        start_time: str | None = None
        start_date: str | None = None
        schedule_relationship: int | None = None
        if vp.HasField("trip"):
            t_desc = vp.trip
            trip_id = t_desc.trip_id.strip() if t_desc.trip_id else None
            route_id = t_desc.route_id.strip() if t_desc.route_id else None
            if t_desc.HasField("direction_id"):
                direction_id = int(t_desc.direction_id)
            start_time = t_desc.start_time.strip() if t_desc.start_time else None
            start_date = t_desc.start_date.strip() if t_desc.start_date else None
            if t_desc.HasField("schedule_relationship"):
                schedule_relationship = int(t_desc.schedule_relationship)

        # Stop info
        stop_id: str | None = vp.stop_id.strip() if vp.stop_id else None
        current_stop_sequence: int | None = (
            int(vp.current_stop_sequence)
            if vp.HasField("current_stop_sequence")
            else None
        )
        current_status: int | None = (
            int(vp.current_status) if vp.HasField("current_status") else None
        )

        # Congestion and occupancy
        congestion_level: int | None = (
            int(vp.congestion_level) if vp.HasField("congestion_level") else None
        )
        occupancy_status: int | None = (
            int(vp.occupancy_status) if vp.HasField("occupancy_status") else None
        )
        occupancy_percentage: int | None = (
            int(vp.occupancy_percentage)
            if vp.HasField("occupancy_percentage")
            else None
        )

        vehicles.append(
            ParsedVehiclePosition(
                entity_id=entity_id,
                latitude=round(float(lat), 6),
                longitude=round(float(lon), 6),
                vehicle_id=vehicle_id,
                vehicle_label=vehicle_label,
                license_plate=license_plate,
                trip_id=trip_id,
                route_id=route_id,
                direction_id=direction_id,
                start_time=start_time,
                start_date=start_date,
                schedule_relationship=schedule_relationship,
                stop_id=stop_id,
                current_stop_sequence=current_stop_sequence,
                current_status=current_status,
                bearing=bearing,
                odometer=odometer,
                speed=speed,
                congestion_level=congestion_level,
                occupancy_status=occupancy_status,
                occupancy_percentage=occupancy_percentage,
                vehicle_timestamp=vehicle_timestamp,
            )
        )

    logger.info(
        "Parsed %d vehicle positions from GTFS-RT feed (header time: %s)",
        len(vehicles),
        feed_timestamp,
    )
    return ParsedRealtimeFeed(
        gtfs_realtime_version=version,
        feed_timestamp=feed_timestamp,
        vehicles=vehicles,
    )
