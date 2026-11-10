"""Unit tests for transit data models, relationships, and metadata."""

from sqlalchemy import inspect

from app.database.session import Base
from app.models import (
    Agency,
    Calendar,
    CalendarDate,
    Route,
    Stop,
    StopTime,
    TransitFeed,
    Trip,
    VehicleObservation,
    VehiclePosition,
)


def test_metadata_contains_all_models() -> None:
    """Verify all transit tables including vehicle_observations are registered."""
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "transit_feeds",
        "agencies",
        "routes",
        "stops",
        "trips",
        "stop_times",
        "calendars",
        "calendar_dates",
        "vehicle_positions",
        "vehicle_observations",
    }
    assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"


def test_transit_feed_model_structure() -> None:
    """Verify columns, constraints, and relationships on TransitFeed."""
    mapper = inspect(TransitFeed)
    columns = {c.name for c in mapper.columns}
    assert {
        "id",
        "city_name",
        "slug",
        "static_gtfs_url",
        "realtime_vehicle_positions_url",
        "api_key_env_var",
        "feed_status",
        "is_live_tracking_enabled",
        "created_at",
        "updated_at",
    }.issubset(columns)

    relationships = {r.key for r in mapper.relationships}
    assert {
        "agencies",
        "routes",
        "stops",
        "trips",
        "calendars",
        "calendar_dates",
    }.issubset(relationships)


def test_agency_model_structure() -> None:
    """Verify columns, constraints, and relationships on Agency."""
    mapper = inspect(Agency)
    columns = {c.name for c in mapper.columns}
    assert {
        "id",
        "feed_id",
        "agency_id",
        "name",
        "url",
        "timezone",
        "phone",
    }.issubset(columns)
    assert mapper.columns["agency_id"].nullable is True

    relationships = {r.key for r in mapper.relationships}
    assert {"feed", "routes"}.issubset(relationships)

    # Check unique constraint on (feed_id, agency_id)
    table = Base.metadata.tables["agencies"]
    unique_col_sets = [
        set(c.name for c in uq.columns)
        for uq in table.constraints
        if hasattr(uq, "columns")
    ]
    assert {"feed_id", "agency_id"} in unique_col_sets


def test_route_model_structure() -> None:
    """Verify columns, constraints, and relationships on Route."""
    mapper = inspect(Route)
    columns = {c.name for c in mapper.columns}
    assert {
        "id",
        "feed_id",
        "agency_id",
        "route_id",
        "short_name",
        "long_name",
        "route_type",
        "route_color",
        "text_color",
    }.issubset(columns)

    relationships = {r.key for r in mapper.relationships}
    assert {"feed", "agency", "trips"}.issubset(relationships)

    # Check unique constraint on (feed_id, route_id)
    table = Base.metadata.tables["routes"]
    unique_col_sets = [
        set(c.name for c in uq.columns)
        for uq in table.constraints
        if hasattr(uq, "columns")
    ]
    assert {"feed_id", "route_id"} in unique_col_sets


def test_stop_model_structure() -> None:
    """Verify columns, constraints, and relationships on Stop."""
    mapper = inspect(Stop)
    columns = {c.name for c in mapper.columns}
    assert {
        "id",
        "feed_id",
        "stop_id",
        "name",
        "latitude",
        "longitude",
        "point",
        "parent_station_id",
        "location_type",
        "wheelchair_boarding",
    }.issubset(columns)

    relationships = {r.key for r in mapper.relationships}
    assert {
        "feed",
        "parent_station",
        "child_stops",
        "stop_times",
    }.issubset(relationships)

    # Check unique constraint on (feed_id, stop_id)
    table = Base.metadata.tables["stops"]
    unique_col_sets = [
        set(c.name for c in uq.columns)
        for uq in table.constraints
        if hasattr(uq, "columns")
    ]
    assert {"feed_id", "stop_id"} in unique_col_sets


def test_trip_model_structure() -> None:
    """Verify columns, constraints, and relationships on Trip."""
    mapper = inspect(Trip)
    columns = {c.name for c in mapper.columns}
    assert {
        "id",
        "feed_id",
        "route_id",
        "service_id",
        "trip_id",
        "trip_headsign",
        "direction_id",
        "block_id",
        "shape_id",
    }.issubset(columns)

    relationships = {r.key for r in mapper.relationships}
    assert {"feed", "route", "stop_times"}.issubset(relationships)

    # Check unique constraint on (feed_id, trip_id)
    table = Base.metadata.tables["trips"]
    unique_col_sets = [
        set(c.name for c in uq.columns)
        for uq in table.constraints
        if hasattr(uq, "columns")
    ]
    assert {"feed_id", "trip_id"} in unique_col_sets


def test_stop_time_model_structure() -> None:
    """Verify columns, constraints, and relationships on StopTime."""
    mapper = inspect(StopTime)
    columns = {c.name for c in mapper.columns}
    assert {
        "id",
        "feed_id",
        "trip_id",
        "stop_id",
        "arrival_time",
        "departure_time",
        "stop_sequence",
        "pickup_type",
        "drop_off_type",
    }.issubset(columns)

    relationships = {r.key for r in mapper.relationships}
    assert {"feed", "trip", "stop"}.issubset(relationships)

    # Check unique constraint on (trip_id, stop_sequence)
    table = Base.metadata.tables["stop_times"]
    unique_col_sets = [
        set(c.name for c in uq.columns)
        for uq in table.constraints
        if hasattr(uq, "columns")
    ]
    assert {"trip_id", "stop_sequence"} in unique_col_sets


def test_calendar_and_date_model_structure() -> None:
    """Verify columns, constraints, and relationships on Calendar and CalendarDate."""
    cal_mapper = inspect(Calendar)
    cal_cols = {c.name for c in cal_mapper.columns}
    assert {
        "id",
        "feed_id",
        "service_id",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "start_date",
        "end_date",
    }.issubset(cal_cols)

    date_mapper = inspect(CalendarDate)
    date_cols = {c.name for c in date_mapper.columns}
    assert {"id", "feed_id", "service_id", "date", "exception_type"}.issubset(date_cols)


def test_model_in_memory_relationships() -> None:
    """Test object instantiation and bidirectional relationship linking."""
    feed = TransitFeed(
        city_name="Delhi",
        slug="delhi-dtc",
        static_gtfs_url="https://example.com/gtfs.zip",
        api_key_env_var="DELHI_TRANSIT_API_KEY",
    )
    agency = Agency(
        agency_id="DTC",
        name="Delhi Transport Corporation",
        url="https://dtc.delhi.gov.in",
        timezone="Asia/Kolkata",
    )
    feed.agencies.append(agency)
    assert agency.feed is feed

    route = Route(
        route_id="534",
        short_name="534",
        long_name="Mehrauli to Anand Vihar",
        route_type=3,
    )
    agency.routes.append(route)
    assert route.agency is agency

    trip = Trip(
        service_id="WEEKDAY",
        trip_id="TRIP_534_01",
        trip_headsign="Anand Vihar ISBT",
        direction_id=0,
    )
    route.trips.append(trip)
    assert trip.route is route

    stop = Stop(
        stop_id="STOP_001",
        name="Mehrauli Terminal",
        latitude=28.5175,
        longitude=77.1824,
    )
    feed.stops.append(stop)
    assert stop.feed is feed

    stop_time = StopTime(
        arrival_time="08:00:00",
        departure_time="08:00:00",
        stop_sequence=1,
    )
    trip.stop_times.append(stop_time)
    stop.stop_times.append(stop_time)
    assert stop_time.trip is trip
    assert stop_time.stop is stop

    vp = VehiclePosition(
        entity_id="entity_1",
        latitude=28.5175,
        longitude=77.1824,
    )
    feed.vehicle_positions.append(vp)
    assert vp.feed is feed


def test_vehicle_position_model_structure() -> None:
    """Verify columns, constraints, and types on VehiclePosition model."""
    mapper = inspect(VehiclePosition)
    columns = {c.name for c in mapper.columns}
    expected_cols = {
        "id",
        "feed_id",
        "entity_id",
        "vehicle_id",
        "vehicle_label",
        "license_plate",
        "trip_id",
        "route_id",
        "direction_id",
        "start_time",
        "start_date",
        "schedule_relationship",
        "stop_id",
        "current_stop_sequence",
        "current_status",
        "latitude",
        "longitude",
        "point",
        "bearing",
        "odometer",
        "speed",
        "congestion_level",
        "occupancy_status",
        "occupancy_percentage",
        "feed_timestamp",
        "vehicle_timestamp",
        "recorded_at",
    }
    assert expected_cols.issubset(columns)

    # Unique constraint on (feed_id, entity_id)
    unique_constraints = {
        tuple(col.name for col in uc.columns)
        for uc in mapper.persist_selectable.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("feed_id", "entity_id") in unique_constraints


def test_vehicle_observation_model_structure() -> None:
    """Verify columns, constraints, and types on VehicleObservation model."""
    mapper = inspect(VehicleObservation)
    columns = {c.name for c in mapper.columns}
    expected_cols = {
        "id",
        "feed_id",
        "entity_id",
        "vehicle_id",
        "vehicle_label",
        "license_plate",
        "trip_id",
        "route_id",
        "direction_id",
        "start_time",
        "start_date",
        "schedule_relationship",
        "stop_id",
        "current_stop_sequence",
        "current_status",
        "latitude",
        "longitude",
        "point",
        "bearing",
        "odometer",
        "speed",
        "congestion_level",
        "occupancy_status",
        "occupancy_percentage",
        "observed_at",
        "vehicle_timestamp",
        "feed_timestamp",
        "recorded_at",
    }
    assert expected_cols.issubset(columns)

    # Unique constraint on (feed_id, entity_id, observed_at)
    unique_constraints = {
        tuple(col.name for col in uc.columns)
        for uc in mapper.persist_selectable.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("feed_id", "entity_id", "observed_at") in unique_constraints
