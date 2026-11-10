"""Create vehicle_observations historical table with spatial GiST index.

Revision ID: 0004_vehicle_observations
Revises: 0003_vehicle_positions
Create Date: 2026-11-10 14:30:00.000000

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_vehicle_observations"
down_revision: str | None = "0003_vehicle_positions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_observations",
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
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vehicle_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feed_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["feed_id"], ["transit_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "feed_id",
            "entity_id",
            "observed_at",
            name="uq_vehicle_observations_feed_entity_observed_at",
        ),
    )
    op.create_index(
        "ix_vehicle_obs_feed_id",
        "vehicle_observations",
        ["feed_id"],
        unique=False,
    )
    op.create_index(
        "ix_vehicle_obs_feed_vehicle_time",
        "vehicle_observations",
        ["feed_id", "vehicle_id", "observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_vehicle_obs_feed_route_time",
        "vehicle_observations",
        ["feed_id", "route_id", "observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_vehicle_obs_feed_observed_at",
        "vehicle_observations",
        ["feed_id", "observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_vehicle_obs_point",
        "vehicle_observations",
        ["point"],
        unique=False,
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vehicle_obs_point",
        table_name="vehicle_observations",
        postgresql_using="gist",
    )
    op.drop_index("ix_vehicle_obs_feed_observed_at", table_name="vehicle_observations")
    op.drop_index("ix_vehicle_obs_feed_route_time", table_name="vehicle_observations")
    op.drop_index("ix_vehicle_obs_feed_vehicle_time", table_name="vehicle_observations")
    op.drop_index("ix_vehicle_obs_feed_id", table_name="vehicle_observations")
    op.drop_table("vehicle_observations")
