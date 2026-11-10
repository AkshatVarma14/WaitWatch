"""Initial transit models and PostGIS extension.

Revision ID: 0001_initial_transit_models
Revises:
Create Date: 2026-11-10 13:00:00.000000

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_transit_models"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 0. PostGIS Extension Setup
    # -------------------------------------------------------------------------
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    # -------------------------------------------------------------------------
    # 1. transit_feeds
    # -------------------------------------------------------------------------
    op.create_table(
        "transit_feeds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("city_name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("static_gtfs_url", sa.String(length=2048), nullable=False),
        sa.Column(
            "realtime_vehicle_positions_url",
            sa.String(length=2048),
            nullable=True,
        ),
        sa.Column(
            "realtime_trip_updates_url",
            sa.String(length=2048),
            nullable=True,
        ),
        sa.Column(
            "realtime_alerts_url",
            sa.String(length=2048),
            nullable=True,
        ),
        sa.Column("api_key_env_var", sa.String(length=100), nullable=True),
        sa.Column(
            "feed_status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "is_live_tracking_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "last_static_import_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_realtime_poll_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transit_feeds_slug", "transit_feeds", ["slug"], unique=True)

    # -------------------------------------------------------------------------
    # 2. agencies
    # -------------------------------------------------------------------------
    op.create_table(
        "agencies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("agency_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("lang", sa.String(length=10), nullable=True),
        sa.Column("fare_url", sa.String(length=2048), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["feed_id"], ["transit_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feed_id", "agency_id", name="uq_agencies_feed_agency_id"),
    )
    op.create_index("ix_agencies_feed_id", "agencies", ["feed_id"], unique=False)

    # -------------------------------------------------------------------------
    # 3. routes
    # -------------------------------------------------------------------------
    op.create_table(
        "routes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("agency_id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.String(length=255), nullable=False),
        sa.Column("short_name", sa.String(length=100), nullable=True),
        sa.Column("long_name", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(length=2048), nullable=True),
        sa.Column("route_type", sa.Integer(), nullable=False),
        sa.Column("route_url", sa.String(length=2048), nullable=True),
        sa.Column("route_color", sa.String(length=7), nullable=True),
        sa.Column("text_color", sa.String(length=7), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feed_id"], ["transit_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feed_id", "route_id", name="uq_routes_feed_route_id"),
    )
    op.create_index("ix_routes_feed_id", "routes", ["feed_id"], unique=False)
    op.create_index("ix_routes_agency_id", "routes", ["agency_id"], unique=False)
    op.create_index(
        "ix_routes_feed_route_type",
        "routes",
        ["feed_id", "route_type"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 4. stops
    # -------------------------------------------------------------------------
    op.create_table(
        "stops",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("stop_id", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2048), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "point",
            geoalchemy2.types.Geography(
                geometry_type="POINT", srid=4326, spatial_index=False
            ),
            nullable=True,
        ),
        sa.Column("parent_station_id", sa.Integer(), nullable=True),
        sa.Column("location_type", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "wheelchair_boarding",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("platform_code", sa.String(length=50), nullable=True),
        sa.Column("timezone", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["feed_id"], ["transit_feeds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_station_id"], ["stops.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feed_id", "stop_id", name="uq_stops_feed_stop_id"),
    )
    op.create_index("ix_stops_feed_id", "stops", ["feed_id"], unique=False)
    op.create_index(
        "ix_stops_parent_station_id",
        "stops",
        ["parent_station_id"],
        unique=False,
    )
    op.create_index("ix_stops_feed_name", "stops", ["feed_id", "name"], unique=False)
    op.create_index(
        "ix_stops_point",
        "stops",
        ["point"],
        unique=False,
        postgresql_using="gist",
    )

    # -------------------------------------------------------------------------
    # 5. trips
    # -------------------------------------------------------------------------
    op.create_table(
        "trips",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.String(length=255), nullable=False),
        sa.Column("trip_id", sa.String(length=255), nullable=False),
        sa.Column("trip_headsign", sa.String(length=255), nullable=True),
        sa.Column("trip_short_name", sa.String(length=100), nullable=True),
        sa.Column("direction_id", sa.Integer(), nullable=True),
        sa.Column("block_id", sa.String(length=255), nullable=True),
        sa.Column("shape_id", sa.String(length=255), nullable=True),
        sa.Column(
            "wheelchair_accessible",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("bikes_allowed", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["feed_id"], ["transit_feeds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feed_id", "trip_id", name="uq_trips_feed_trip_id"),
    )
    op.create_index("ix_trips_feed_id", "trips", ["feed_id"], unique=False)
    op.create_index("ix_trips_route_id", "trips", ["route_id"], unique=False)
    op.create_index("ix_trips_service_id", "trips", ["service_id"], unique=False)
    op.create_index(
        "ix_trips_feed_service_id",
        "trips",
        ["feed_id", "service_id"],
        unique=False,
    )
    op.create_index(
        "ix_trips_feed_shape_id",
        "trips",
        ["feed_id", "shape_id"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 6. stop_times
    # -------------------------------------------------------------------------
    op.create_table(
        "stop_times",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("stop_id", sa.Integer(), nullable=False),
        sa.Column("arrival_time", sa.String(length=8), nullable=False),
        sa.Column("departure_time", sa.String(length=8), nullable=False),
        sa.Column("stop_sequence", sa.Integer(), nullable=False),
        sa.Column("stop_headsign", sa.String(length=255), nullable=True),
        sa.Column("pickup_type", sa.Integer(), server_default="0", nullable=False),
        sa.Column("drop_off_type", sa.Integer(), server_default="0", nullable=False),
        sa.Column("shape_dist_traveled", sa.Float(), nullable=True),
        sa.Column("timepoint", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["feed_id"], ["transit_feeds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stop_id"], ["stops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trip_id", "stop_sequence", name="uq_stop_times_trip_sequence"
        ),
    )
    op.create_index("ix_stop_times_feed_id", "stop_times", ["feed_id"], unique=False)
    op.create_index("ix_stop_times_trip_id", "stop_times", ["trip_id"], unique=False)
    op.create_index("ix_stop_times_stop_id", "stop_times", ["stop_id"], unique=False)
    op.create_index(
        "ix_stop_times_stop_arrival",
        "stop_times",
        ["stop_id", "arrival_time"],
        unique=False,
    )
    op.create_index(
        "ix_stop_times_feed_trip",
        "stop_times",
        ["feed_id", "trip_id"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 7. calendars
    # -------------------------------------------------------------------------
    op.create_table(
        "calendars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.String(length=255), nullable=False),
        sa.Column(
            "monday",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "tuesday",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "wednesday",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "thursday",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "friday",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "saturday",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "sunday",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["feed_id"], ["transit_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "feed_id", "service_id", name="uq_calendars_feed_service_id"
        ),
    )
    op.create_index("ix_calendars_feed_id", "calendars", ["feed_id"], unique=False)
    op.create_index(
        "ix_calendars_feed_service_dates",
        "calendars",
        ["feed_id", "start_date", "end_date"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 8. calendar_dates
    # -------------------------------------------------------------------------
    op.create_table(
        "calendar_dates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.String(length=255), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("exception_type", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["feed_id"], ["transit_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "feed_id",
            "service_id",
            "date",
            name="uq_calendar_dates_feed_service_date",
        ),
    )
    op.create_index(
        "ix_calendar_dates_feed_id", "calendar_dates", ["feed_id"], unique=False
    )
    op.create_index(
        "ix_calendar_dates_feed_date",
        "calendar_dates",
        ["feed_id", "date"],
        unique=False,
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("calendar_dates")
    op.drop_table("calendars")
    op.drop_table("stop_times")
    op.drop_table("trips")
    op.drop_table("stops")
    op.drop_table("routes")
    op.drop_table("agencies")
    op.drop_table("transit_feeds")
