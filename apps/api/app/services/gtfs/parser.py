"""GTFS Schedule CSV parsing and relational validation."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime

from app.services.gtfs.exceptions import GTFSValidationError

# Regex for GTFS HH:MM:SS service-day times (permits hours >= 24)
GTFS_TIME_REGEX = re.compile(r"^(\d{1,2}):([0-5]\d):([0-5]\d)$")


@dataclass(slots=True)
class ParsedAgency:
    """Parsed agency record."""

    agency_id: str | None
    name: str
    url: str
    timezone: str
    phone: str | None = None
    lang: str | None = None
    fare_url: str | None = None
    email: str | None = None


@dataclass(slots=True)
class ParsedRoute:
    """Parsed route record."""

    route_id: str
    agency_id: str | None
    short_name: str | None
    long_name: str | None
    description: str | None
    route_type: int
    route_url: str | None = None
    route_color: str | None = None
    text_color: str | None = None
    sort_order: int | None = None


@dataclass(slots=True)
class ParsedStop:
    """Parsed stop record."""

    stop_id: str
    code: str | None
    name: str
    description: str | None
    latitude: float
    longitude: float
    parent_station: str | None = None
    location_type: int = 0
    wheelchair_boarding: int = 0
    platform_code: str | None = None
    timezone: str | None = None


@dataclass(slots=True)
class ParsedCalendar:
    """Parsed regular weekly calendar record."""

    service_id: str
    monday: bool
    tuesday: bool
    wednesday: bool
    thursday: bool
    friday: bool
    saturday: bool
    sunday: bool
    start_date: date
    end_date: date


@dataclass(slots=True)
class ParsedCalendarDate:
    """Parsed calendar exception record."""

    service_id: str
    date: date
    exception_type: int


@dataclass(slots=True)
class ParsedTrip:
    """Parsed trip record."""

    trip_id: str
    route_id: str
    service_id: str
    trip_headsign: str | None = None
    trip_short_name: str | None = None
    direction_id: int | None = None
    block_id: str | None = None
    shape_id: str | None = None
    wheelchair_accessible: int = 0
    bikes_allowed: int = 0


@dataclass(slots=True)
class ParsedStopTime:
    """Parsed stop time record."""

    trip_id: str
    stop_id: str
    arrival_time: str
    departure_time: str
    stop_sequence: int
    stop_headsign: str | None = None
    pickup_type: int = 0
    drop_off_type: int = 0
    shape_dist_traveled: float | None = None
    timepoint: int = 1


@dataclass(slots=True)
class ParsedFeedData:
    """All validated GTFS entities parsed from a feed."""

    agencies: list[ParsedAgency]
    routes: list[ParsedRoute]
    stops: list[ParsedStop]
    calendars: list[ParsedCalendar]
    calendar_dates: list[ParsedCalendarDate]
    trips: list[ParsedTrip]
    stop_times: list[ParsedStopTime]


def _read_csv_rows(content: str, filename: str) -> list[dict[str, str]]:
    """Parse CSV text into list of sanitized dictionaries."""
    sanitized = content.lstrip("\ufeff")
    stream = io.StringIO(sanitized)
    reader = csv.DictReader(stream)

    if not reader.fieldnames:
        raise GTFSValidationError(f"File {filename} is empty or has no header line")

    # Clean fieldnames (strip whitespace)
    cleaned_fields = [f.strip() for f in reader.fieldnames if f]
    reader.fieldnames = cleaned_fields

    rows: list[dict[str, str]] = []
    for _row_idx, raw_row in enumerate(reader, start=2):
        row = {
            (k.strip() if k else ""): (v.strip() if v else "")
            for k, v in raw_row.items()
            if k is not None
        }
        rows.append(row)
    return rows


def _parse_time(time_str: str, field_name: str, row_idx: int) -> str:
    """Validate and normalize GTFS service-day time string to HH:MM:SS."""
    if not time_str:
        raise GTFSValidationError(
            f"Row {row_idx}: {field_name} is required and cannot be empty"
        )
    match = GTFS_TIME_REGEX.match(time_str)
    if not match:
        raise GTFSValidationError(
            f"Row {row_idx}: Invalid {field_name} {time_str!r}; expected HH:MM:SS"
        )
    hour, minute, second = match.groups()
    return f"{int(hour):02d}:{minute}:{second}"


def _parse_date(date_str: str, field_name: str, row_idx: int) -> date:
    """Parse GTFS YYYYMMDD date."""
    if not date_str or len(date_str) != 8 or not date_str.isdigit():
        raise GTFSValidationError(
            f"Row {row_idx}: Invalid {field_name} {date_str!r}; expected YYYYMMDD"
        )
    try:
        return datetime.strptime(date_str, "%Y%m%d").date()
    except ValueError as exc:
        raise GTFSValidationError(
            f"Row {row_idx}: Invalid calendar date {date_str!r}: {exc}"
        ) from exc


def _parse_color(color_str: str | None) -> str | None:
    """Normalize hex color string to #RRGGBB."""
    if not color_str:
        return None
    val = color_str.strip().lstrip("#")
    if len(val) == 6:
        return f"#{val.upper()}"
    return f"#{val[:6].upper()}" if val else None


def parse_gtfs_tables(tables: dict[str, str]) -> ParsedFeedData:
    """Validate and parse extracted GTFS text tables.

    Args:
        tables: Mapping of table names ('agency.txt', etc.) to text contents.

    Returns:
        ParsedFeedData: Validated GTFS entities ready for persistence.

    Raises:
        GTFSValidationError: On missing required files/headers or invalid data.
    """
    # 1. Check required tables
    required_files = [
        "agency.txt",
        "routes.txt",
        "stops.txt",
        "trips.txt",
        "stop_times.txt",
    ]
    for req in required_files:
        if req not in tables or not tables[req].strip():
            raise GTFSValidationError(f"Required GTFS file missing or empty: {req}")

    has_calendar = "calendar.txt" in tables and bool(tables["calendar.txt"].strip())
    has_calendar_dates = "calendar_dates.txt" in tables and bool(
        tables["calendar_dates.txt"].strip()
    )

    if not has_calendar and not has_calendar_dates:
        raise GTFSValidationError(
            "GTFS feed must include 'calendar.txt' or 'calendar_dates.txt'"
        )

    # 2. Parse agency.txt
    agency_rows = _read_csv_rows(tables["agency.txt"], "agency.txt")
    if not agency_rows:
        raise GTFSValidationError("agency.txt must contain at least one agency record")

    is_single_agency = len(agency_rows) == 1
    agencies: list[ParsedAgency] = []
    agency_ids_seen: set[str] = set()

    for row_idx, row in enumerate(agency_rows, start=2):
        name = row.get("agency_name", "")
        url = row.get("agency_url", "")
        timezone = row.get("agency_timezone", "")
        raw_agency_id = row.get("agency_id", "").strip() or None

        if not name or not url or not timezone:
            raise GTFSValidationError(
                f"agency.txt row {row_idx}: name, url, and timezone are required"
            )

        if not is_single_agency and not raw_agency_id:
            raise GTFSValidationError(
                f"agency.txt row {row_idx}: agency_id required for multi-agency"
            )

        if raw_agency_id:
            if raw_agency_id in agency_ids_seen:
                raise GTFSValidationError(
                    f"agency.txt row {row_idx}: Duplicate agency_id {raw_agency_id!r}"
                )
            agency_ids_seen.add(raw_agency_id)

        agencies.append(
            ParsedAgency(
                agency_id=raw_agency_id,
                name=name,
                url=url,
                timezone=timezone,
                phone=row.get("agency_phone") or None,
                lang=row.get("agency_lang") or None,
                fare_url=row.get("agency_fare_url") or None,
                email=row.get("agency_email") or None,
            )
        )

    sole_agency_id = agencies[0].agency_id if is_single_agency else None

    # 3. Parse routes.txt
    route_rows = _read_csv_rows(tables["routes.txt"], "routes.txt")
    if not route_rows:
        raise GTFSValidationError("routes.txt must contain at least one route")

    routes: list[ParsedRoute] = []
    route_ids_seen: set[str] = set()

    for row_idx, row in enumerate(route_rows, start=2):
        route_id = row.get("route_id", "")
        if not route_id:
            raise GTFSValidationError(f"routes.txt row {row_idx}: route_id is required")
        if route_id in route_ids_seen:
            raise GTFSValidationError(
                f"routes.txt row {row_idx}: Duplicate route_id {route_id!r}"
            )
        route_ids_seen.add(route_id)

        raw_route_type = row.get("route_type", "")
        if not raw_route_type.isdigit() and not (
            raw_route_type.startswith("-") and raw_route_type[1:].isdigit()
        ):
            raise GTFSValidationError(
                f"routes.txt row {row_idx}: route_type must be int ({raw_route_type!r})"
            )
        route_type = int(raw_route_type)

        short_name = row.get("route_short_name") or None
        long_name = row.get("route_long_name") or None
        if not short_name and not long_name:
            raise GTFSValidationError(
                f"routes.txt row {row_idx}: short_name or long_name required"
            )

        route_agency_id = row.get("agency_id", "").strip() or None
        if is_single_agency:
            # If agency_id omitted in single-agency feed, resolve to sole agency
            if not route_agency_id:
                route_agency_id = sole_agency_id
            elif sole_agency_id and route_agency_id != sole_agency_id:
                raise GTFSValidationError(
                    f"routes.txt row {row_idx}: Route agency_id {route_agency_id!r} "
                    f"does not match sole agency_id {sole_agency_id!r}"
                )
        else:
            if not route_agency_id:
                raise GTFSValidationError(
                    f"routes.txt row {row_idx}: agency_id required in multi-agency"
                )
            if route_agency_id not in agency_ids_seen:
                raise GTFSValidationError(
                    f"routes.txt row {row_idx}: Unknown agency_id {route_agency_id!r}"
                )

        sort_order_raw = row.get("route_sort_order", "")
        sort_order = int(sort_order_raw) if sort_order_raw.isdigit() else None

        routes.append(
            ParsedRoute(
                route_id=route_id,
                agency_id=route_agency_id,
                short_name=short_name,
                long_name=long_name,
                description=row.get("route_desc") or None,
                route_type=route_type,
                route_url=row.get("route_url") or None,
                route_color=_parse_color(row.get("route_color")),
                text_color=_parse_color(row.get("route_text_color")),
                sort_order=sort_order,
            )
        )

    # 4. Parse stops.txt
    stop_rows = _read_csv_rows(tables["stops.txt"], "stops.txt")
    if not stop_rows:
        raise GTFSValidationError("stops.txt must contain at least one stop")

    stops: list[ParsedStop] = []
    stop_ids_seen: set[str] = set()

    for row_idx, row in enumerate(stop_rows, start=2):
        stop_id = row.get("stop_id", "")
        if not stop_id:
            raise GTFSValidationError(f"stops.txt row {row_idx}: stop_id is required")
        if stop_id in stop_ids_seen:
            raise GTFSValidationError(
                f"stops.txt row {row_idx}: Duplicate stop_id {stop_id!r}"
            )
        stop_ids_seen.add(stop_id)

        name = row.get("stop_name", "")
        if not name:
            raise GTFSValidationError(f"stops.txt row {row_idx}: stop_name is required")

        lat_raw = row.get("stop_lat", "")
        lon_raw = row.get("stop_lon", "")
        try:
            latitude = float(lat_raw)
            longitude = float(lon_raw)
        except (ValueError, TypeError) as exc:
            raise GTFSValidationError(
                f"stops.txt row {row_idx}: stop_lat and stop_lon must be valid numbers"
            ) from exc

        if not (-90.0 <= latitude <= 90.0):
            raise GTFSValidationError(
                f"stops.txt row {row_idx}: latitude {latitude} out of bounds [-90, 90]"
            )
        if not (-180.0 <= longitude <= 180.0):
            raise GTFSValidationError(
                f"stops.txt row {row_idx}: longitude {longitude} out of bounds"
            )

        loc_type_raw = row.get("location_type", "")
        location_type = int(loc_type_raw) if loc_type_raw.isdigit() else 0

        wheelchair_raw = row.get("wheelchair_boarding", "")
        wheelchair_boarding = int(wheelchair_raw) if wheelchair_raw.isdigit() else 0

        stops.append(
            ParsedStop(
                stop_id=stop_id,
                code=row.get("stop_code") or None,
                name=name,
                description=row.get("stop_desc") or None,
                latitude=latitude,
                longitude=longitude,
                parent_station=row.get("parent_station", "").strip() or None,
                location_type=location_type,
                wheelchair_boarding=wheelchair_boarding,
                platform_code=row.get("platform_code") or None,
                timezone=row.get("stop_timezone") or None,
            )
        )

    # Validate parent_station references
    for stop in stops:
        if stop.parent_station and stop.parent_station not in stop_ids_seen:
            raise GTFSValidationError(
                f"Stop {stop.stop_id!r} has unknown parent {stop.parent_station!r}"
            )

    # 5. Parse calendar.txt
    calendars: list[ParsedCalendar] = []
    service_ids_seen: set[str] = set()

    if has_calendar:
        calendar_rows = _read_csv_rows(tables["calendar.txt"], "calendar.txt")
        for row_idx, row in enumerate(calendar_rows, start=2):
            service_id = row.get("service_id", "")
            if not service_id:
                raise GTFSValidationError(
                    f"calendar.txt row {row_idx}: service_id is required"
                )
            if service_id in service_ids_seen:
                raise GTFSValidationError(
                    f"calendar.txt row {row_idx}: Duplicate service_id {service_id!r}"
                )
            service_ids_seen.add(service_id)

            days = {
                d: row.get(d, "").strip() == "1"
                for d in (
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday",
                    "sunday",
                )
            }
            start_date = _parse_date(row.get("start_date", ""), "start_date", row_idx)
            end_date = _parse_date(row.get("end_date", ""), "end_date", row_idx)

            if start_date > end_date:
                raise GTFSValidationError(
                    f"calendar.txt row {row_idx}: start {start_date} > end {end_date}"
                )

            calendars.append(
                ParsedCalendar(
                    service_id=service_id,
                    monday=days["monday"],
                    tuesday=days["tuesday"],
                    wednesday=days["wednesday"],
                    thursday=days["thursday"],
                    friday=days["friday"],
                    saturday=days["saturday"],
                    sunday=days["sunday"],
                    start_date=start_date,
                    end_date=end_date,
                )
            )

    # 6. Parse calendar_dates.txt
    calendar_dates: list[ParsedCalendarDate] = []
    cal_date_pairs: set[tuple[str, date]] = set()

    if has_calendar_dates:
        cal_date_rows = _read_csv_rows(
            tables["calendar_dates.txt"], "calendar_dates.txt"
        )
        for row_idx, row in enumerate(cal_date_rows, start=2):
            service_id = row.get("service_id", "")
            if not service_id:
                raise GTFSValidationError(
                    f"calendar_dates.txt row {row_idx}: service_id is required"
                )
            dt = _parse_date(row.get("date", ""), "date", row_idx)

            pair = (service_id, dt)
            if pair in cal_date_pairs:
                raise GTFSValidationError(
                    f"calendar_dates.txt row {row_idx}: Duplicate pair {pair!r}"
                )
            cal_date_pairs.add(pair)
            service_ids_seen.add(service_id)

            exc_type_raw = row.get("exception_type", "")
            if exc_type_raw not in ("1", "2"):
                raise GTFSValidationError(
                    f"calendar_dates.txt row {row_idx}: exception_type must be 1/2"
                )

            calendar_dates.append(
                ParsedCalendarDate(
                    service_id=service_id,
                    date=dt,
                    exception_type=int(exc_type_raw),
                )
            )

    # 7. Parse trips.txt
    trip_rows = _read_csv_rows(tables["trips.txt"], "trips.txt")
    if not trip_rows:
        raise GTFSValidationError("trips.txt must contain at least one trip")

    trips: list[ParsedTrip] = []
    trip_ids_seen: set[str] = set()

    for row_idx, row in enumerate(trip_rows, start=2):
        trip_id = row.get("trip_id", "")
        if not trip_id:
            raise GTFSValidationError(f"trips.txt row {row_idx}: trip_id is required")
        if trip_id in trip_ids_seen:
            raise GTFSValidationError(
                f"trips.txt row {row_idx}: Duplicate trip_id {trip_id!r}"
            )
        trip_ids_seen.add(trip_id)

        route_id = row.get("route_id", "")
        if not route_id:
            raise GTFSValidationError(f"trips.txt row {row_idx}: route_id is required")
        if route_id not in route_ids_seen:
            raise GTFSValidationError(
                f"trips.txt row {row_idx}: unknown route_id {route_id!r}"
            )

        service_id = row.get("service_id", "")
        if not service_id:
            raise GTFSValidationError(
                f"trips.txt row {row_idx}: service_id is required"
            )
        if service_id not in service_ids_seen:
            raise GTFSValidationError(
                f"trips.txt row {row_idx}: unknown service_id {service_id!r}"
            )

        direction_raw = row.get("direction_id", "")
        direction_id = int(direction_raw) if direction_raw in ("0", "1") else None

        wheelchair_raw = row.get("wheelchair_accessible", "")
        wheelchair_acc = int(wheelchair_raw) if wheelchair_raw.isdigit() else 0

        bikes_raw = row.get("bikes_allowed", "")
        bikes_allowed = int(bikes_raw) if bikes_raw.isdigit() else 0

        trips.append(
            ParsedTrip(
                trip_id=trip_id,
                route_id=route_id,
                service_id=service_id,
                trip_headsign=row.get("trip_headsign") or None,
                trip_short_name=row.get("trip_short_name") or None,
                direction_id=direction_id,
                block_id=row.get("block_id") or None,
                shape_id=row.get("shape_id") or None,
                wheelchair_accessible=wheelchair_acc,
                bikes_allowed=bikes_allowed,
            )
        )

    # 8. Parse stop_times.txt
    stop_time_rows = _read_csv_rows(tables["stop_times.txt"], "stop_times.txt")
    if not stop_time_rows:
        raise GTFSValidationError(
            "stop_times.txt must contain at least one stop_time record"
        )

    stop_times: list[ParsedStopTime] = []
    trip_seq_pairs: set[tuple[str, int]] = set()

    for row_idx, row in enumerate(stop_time_rows, start=2):
        trip_id = row.get("trip_id", "")
        if not trip_id:
            raise GTFSValidationError(
                f"stop_times.txt row {row_idx}: trip_id is required"
            )
        if trip_id not in trip_ids_seen:
            raise GTFSValidationError(
                f"stop_times.txt row {row_idx}: References unknown trip_id {trip_id!r}"
            )

        stop_id = row.get("stop_id", "")
        if not stop_id:
            raise GTFSValidationError(
                f"stop_times.txt row {row_idx}: stop_id is required"
            )
        if stop_id not in stop_ids_seen:
            raise GTFSValidationError(
                f"stop_times.txt row {row_idx}: References unknown stop_id {stop_id!r}"
            )

        seq_raw = row.get("stop_sequence", "")
        if not seq_raw.isdigit():
            raise GTFSValidationError(
                f"stop_times.txt row {row_idx}: invalid stop_sequence {seq_raw!r}"
            )
        stop_sequence = int(seq_raw)

        pair = (trip_id, stop_sequence)
        if pair in trip_seq_pairs:
            raise GTFSValidationError(
                f"stop_times.txt row {row_idx}: Duplicate sequence pair {pair!r}"
            )
        trip_seq_pairs.add(pair)

        arr_time = _parse_time(row.get("arrival_time", ""), "arrival_time", row_idx)
        dep_time = _parse_time(row.get("departure_time", ""), "departure_time", row_idx)

        pickup_raw = row.get("pickup_type", "")
        pickup_type = int(pickup_raw) if pickup_raw.isdigit() else 0

        drop_off_raw = row.get("drop_off_type", "")
        drop_off_type = int(drop_off_raw) if drop_off_raw.isdigit() else 0

        dist_raw = row.get("shape_dist_traveled", "")
        try:
            shape_dist = float(dist_raw) if dist_raw else None
        except ValueError:
            shape_dist = None

        timepoint_raw = row.get("timepoint", "")
        timepoint = int(timepoint_raw) if timepoint_raw.isdigit() else 1

        stop_times.append(
            ParsedStopTime(
                trip_id=trip_id,
                stop_id=stop_id,
                arrival_time=arr_time,
                departure_time=dep_time,
                stop_sequence=stop_sequence,
                stop_headsign=row.get("stop_headsign") or None,
                pickup_type=pickup_type,
                drop_off_type=drop_off_type,
                shape_dist_traveled=shape_dist,
                timepoint=timepoint,
            )
        )

    return ParsedFeedData(
        agencies=agencies,
        routes=routes,
        stops=stops,
        calendars=calendars,
        calendar_dates=calendar_dates,
        trips=trips,
        stop_times=stop_times,
    )
