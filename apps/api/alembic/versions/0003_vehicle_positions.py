"""Create vehicle_positions snapshot table with spatial GiST index.

Revision ID: 0003_vehicle_positions
Revises: 0002_optional_agency_id
Create Date: 2026-11-10 14:15:00.000000

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_vehicle_positions"
down_revision: str | None = "0002_optional_agency_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("vehicle_id", sa.String(length=255), nullable=True),
        sa.Column("vehicle_label", sa.String(length=255), nullable=True),
        sa.Column("license_plate", sa.String(length=255), nullable=True),
        sa.Column("trip_id", sa.String(length=255), nullable=True),
        sa.Column("route_id", sa.String(length=255), nullable=True),
        sa.Column("direction_id", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.String(length=10), nullable=True),
        sa.Column("start_date", sa.String(length=10), nullable=True),
        sa.Column("schedule_relationship", sa.Integer(), nullable=True),
        sa.Column("stop_id", sa.String(length=255), nullable=True),
        sa.Column("current_stop_sequence", sa.Integer(), nullable=True),
        sa.Column("current_status", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "point",
            geoalchemy2.types.Geography(
                geometry_type="POINT", srid=4326, spatial_index=False
            ),
            nullable=True,
        ),
        sa.Column("bearing", sa.Float(), nullable=True),
        sa.Column("odometer", sa.Float(), nullable=True),
        sa.Column("speed", sa.Float(), nullable=True),
        sa.Column("congestion_level", sa.Integer(), nullable=True),
        sa.Column("occupancy_status", sa.Integer(), nullable=True),
        sa.Column("occupancy_percentage", sa.Integer(), nullable=True),
        sa.Column("feed_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vehicle_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["feed_id"], ["transit_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "feed_id", "entity_id", name="uq_vehicle_positions_feed_entity_id"
        ),
    )
    op.create_index(
        "ix_vehicle_positions_feed_id",
        "vehicle_positions",
        ["feed_id"],
        unique=False,
    )
    op.create_index(
        "ix_vehicle_positions_feed_route",
        "vehicle_positions",
        ["feed_id", "route_id"],
        unique=False,
    )
    op.create_index(
        "ix_vehicle_positions_feed_vehicle",
        "vehicle_positions",
        ["feed_id", "vehicle_id"],
        unique=False,
    )
    op.create_index(
        "ix_vehicle_positions_point",
        "vehicle_positions",
        ["point"],
        unique=False,
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vehicle_positions_point",
        table_name="vehicle_positions",
        postgresql_using="gist",
    )
    op.drop_index("ix_vehicle_positions_feed_vehicle", table_name="vehicle_positions")
    op.drop_index("ix_vehicle_positions_feed_route", table_name="vehicle_positions")
    op.drop_index("ix_vehicle_positions_feed_id", table_name="vehicle_positions")
    op.drop_table("vehicle_positions")
