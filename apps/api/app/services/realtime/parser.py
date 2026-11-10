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


@dataclass(frozen=True, slots=True)
class ParsedStopTimeEvent:
    """Arrival or departure time event for a stop."""

    time: datetime | None = None
    delay: int | None = None
    uncertainty: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedStopTimeUpdate:
    """Real-time arrival and departure update for a single stop along a trip."""

    stop_sequence: int | None = None
    stop_id: str | None = None
    arrival: ParsedStopTimeEvent | None = None
    departure: ParsedStopTimeEvent | None = None
    schedule_relationship: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedTripUpdate:
    """Validated in-memory trip update from GTFS-Realtime."""

    entity_id: str
    trip_id: str
    route_id: str | None = None
    direction_id: int | None = None
    start_time: str | None = None
    start_date: str | None = None
    schedule_relationship: int | None = None
    vehicle_id: str | None = None
    vehicle_label: str | None = None
    vehicle_license_plate: str | None = None
    timestamp: datetime | None = None
    delay: int | None = None
    stop_time_updates: tuple[ParsedStopTimeUpdate, ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedTripUpdatesFeed:
    """Validated feed message containing header metadata and trip updates."""

    gtfs_realtime_version: str
    feed_timestamp: datetime | None
    trip_updates: list[ParsedTripUpdate]


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


def parse_trip_updates(payload: bytes) -> ParsedTripUpdatesFeed:
    """Decode and validate a GTFS-Realtime Protocol Buffer payload for TripUpdates.

    Args:
        payload: Raw protobuf bytes from the GTFS-RT TripUpdates endpoint.

    Returns:
        ParsedTripUpdatesFeed: Container with validated header and trip update records.

    Raises:
        RealtimeParseError: On invalid protobuf syntax, duplicate entities,
            or corrupted timestamp/delay fields.
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

    # 2. Validate FeedEntities and extract trip updates
    seen_entity_ids: set[str] = set()
    trip_updates: list[ParsedTripUpdate] = []

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

        # Ignore deleted entities or entities without trip updates
        # (e.g. vehicle positions or alerts if included in combined feeds)
        if entity.is_deleted or not entity.HasField("trip_update"):
            continue

        tu = entity.trip_update

        # TripDescriptor is required for TripUpdate
        if not tu.HasField("trip"):
            raise RealtimeParseError(
                f"TripUpdate in entity '{entity_id}' missing required trip descriptor"
            )

        t_desc = tu.trip
        trip_id = t_desc.trip_id.strip() if t_desc.trip_id else None
        if not trip_id:
            raise RealtimeParseError(
                f"TripUpdate in entity '{entity_id}' missing trip_id"
            )

        route_id = t_desc.route_id.strip() if t_desc.route_id else None
        direction_id = (
            int(t_desc.direction_id) if t_desc.HasField("direction_id") else None
        )
        start_time = t_desc.start_time.strip() if t_desc.start_time else None
        start_date = t_desc.start_date.strip() if t_desc.start_date else None
        schedule_relationship = (
            int(t_desc.schedule_relationship)
            if t_desc.HasField("schedule_relationship")
            else None
        )

        # VehicleDescriptor (optional)
        vehicle_id: str | None = None
        vehicle_label: str | None = None
        license_plate: str | None = None
        if tu.HasField("vehicle"):
            v_desc = tu.vehicle
            vehicle_id = v_desc.id.strip() if v_desc.id else None
            vehicle_label = v_desc.label.strip() if v_desc.label else None
            license_plate = (
                v_desc.license_plate.strip() if v_desc.license_plate else None
            )

        # Trip update timestamp
        update_timestamp: datetime | None = None
        if tu.HasField("timestamp") and tu.timestamp > 0:
            if tu.timestamp > MAX_TIMESTAMP_SECONDS:
                raise RealtimeParseError(
                    f"TripUpdate timestamp {tu.timestamp} for '{entity_id}' is invalid"
                )
            try:
                update_timestamp = datetime.fromtimestamp(tu.timestamp, tz=UTC)
            except (ValueError, OverflowError, OSError) as exc:
                raise RealtimeParseError(
                    f"Invalid trip timestamp for entity '{entity_id}': {exc}"
                ) from exc

        # Trip-level delay
        trip_delay: int | None = int(tu.delay) if tu.HasField("delay") else None

        # StopTimeUpdate entries
        stop_updates: list[ParsedStopTimeUpdate] = []
        for stu in tu.stop_time_update:
            stop_sequence = (
                int(stu.stop_sequence) if stu.HasField("stop_sequence") else None
            )
            stop_id = stu.stop_id.strip() if stu.stop_id else None
            if stop_sequence is None and not stop_id:
                raise RealtimeParseError(
                    f"StopTimeUpdate in entity '{entity_id}' missing both "
                    "stop_sequence and stop_id"
                )

            # Arrival event
            arrival_event: ParsedStopTimeEvent | None = None
            if stu.HasField("arrival"):
                arr = stu.arrival
                arr_time: datetime | None = None
                if arr.HasField("time") and arr.time > 0:
                    if arr.time > MAX_TIMESTAMP_SECONDS:
                        raise RealtimeParseError(
                            f"Arrival time {arr.time} in entity '{entity_id}' "
                            "is out of bounds"
                        )
                    try:
                        arr_time = datetime.fromtimestamp(arr.time, tz=UTC)
                    except (ValueError, OverflowError, OSError) as exc:
                        raise RealtimeParseError(
                            f"Invalid arrival time in entity '{entity_id}': {exc}"
                        ) from exc
                arr_delay = int(arr.delay) if arr.HasField("delay") else None
                arr_unc = int(arr.uncertainty) if arr.HasField("uncertainty") else None
                arrival_event = ParsedStopTimeEvent(
                    time=arr_time,
                    delay=arr_delay,
                    uncertainty=arr_unc,
                )

            # Departure event
            departure_event: ParsedStopTimeEvent | None = None
            if stu.HasField("departure"):
                dep = stu.departure
                dep_time: datetime | None = None
                if dep.HasField("time") and dep.time > 0:
                    if dep.time > MAX_TIMESTAMP_SECONDS:
                        raise RealtimeParseError(
                            f"Departure time {dep.time} in entity '{entity_id}' "
                            "is out of bounds"
                        )
                    try:
                        dep_time = datetime.fromtimestamp(dep.time, tz=UTC)
                    except (ValueError, OverflowError, OSError) as exc:
                        raise RealtimeParseError(
                            f"Invalid departure time in entity '{entity_id}': {exc}"
                        ) from exc
                dep_delay = int(dep.delay) if dep.HasField("delay") else None
                dep_unc = int(dep.uncertainty) if dep.HasField("uncertainty") else None
                departure_event = ParsedStopTimeEvent(
                    time=dep_time,
                    delay=dep_delay,
                    uncertainty=dep_unc,
                )

            stu_rel = (
                int(stu.schedule_relationship)
                if stu.HasField("schedule_relationship")
                else None
            )

            stop_updates.append(
                ParsedStopTimeUpdate(
                    stop_sequence=stop_sequence,
                    stop_id=stop_id,
                    arrival=arrival_event,
                    departure=departure_event,
                    schedule_relationship=stu_rel,
                )
            )

        trip_updates.append(
            ParsedTripUpdate(
                entity_id=entity_id,
                trip_id=trip_id,
                route_id=route_id,
                direction_id=direction_id,
                start_time=start_time,
                start_date=start_date,
                schedule_relationship=schedule_relationship,
                vehicle_id=vehicle_id,
                vehicle_label=vehicle_label,
                vehicle_license_plate=license_plate,
                timestamp=update_timestamp,
                delay=trip_delay,
                stop_time_updates=tuple(stop_updates),
            )
        )

    logger.info(
        "Parsed %d trip updates from GTFS-RT feed (header time: %s)",
        len(trip_updates),
        feed_timestamp,
    )
    return ParsedTripUpdatesFeed(
        gtfs_realtime_version=version,
        feed_timestamp=feed_timestamp,
        trip_updates=trip_updates,
    )
