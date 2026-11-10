"""Create trip_updates table for GTFS-Realtime trip updates and stop predictions.

Revision ID: 0006_trip_updates
Revises: 0005_shapes
Create Date: 2026-11-10 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_trip_updates"
down_revision: str | None = "0005_shapes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trip_updates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("trip_id", sa.String(length=255), nullable=False),
        sa.Column("route_id", sa.String(length=255), nullable=True),
        sa.Column("direction_id", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.String(length=10), nullable=True),
        sa.Column("start_date", sa.String(length=10), nullable=True),
        sa.Column("schedule_relationship", sa.Integer(), nullable=True),
        sa.Column("vehicle_id", sa.String(length=255), nullable=True),
        sa.Column("vehicle_label", sa.String(length=255), nullable=True),
        sa.Column("vehicle_license_plate", sa.String(length=255), nullable=True),
        sa.Column("stop_sequence", sa.Integer(), nullable=True),
        sa.Column("stop_id", sa.String(length=255), nullable=True),
        sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrival_delay", sa.Integer(), nullable=True),
        sa.Column("arrival_uncertainty", sa.Integer(), nullable=True),
        sa.Column("departure_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("departure_delay", sa.Integer(), nullable=True),
        sa.Column("departure_uncertainty", sa.Integer(), nullable=True),
        sa.Column("stop_schedule_relationship", sa.Integer(), nullable=True),
        sa.Column("trip_delay", sa.Integer(), nullable=True),
        sa.Column("update_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feed_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
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
        sa.ForeignKeyConstraint(["feed_id"], ["transit_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trip_updates_feed_id",
        "trip_updates",
        ["feed_id"],
        unique=False,
    )
    op.create_index(
        "ix_trip_updates_feed_trip",
        "trip_updates",
        ["feed_id", "trip_id"],
        unique=False,
    )
    op.create_index(
        "ix_trip_updates_feed_stop",
        "trip_updates",
        ["feed_id", "stop_id"],
        unique=False,
    )
    op.create_index(
        "ix_trip_updates_feed_entity",
        "trip_updates",
        ["feed_id", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_trip_updates_trip_stop",
        "trip_updates",
        ["feed_id", "trip_id", "stop_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trip_updates_trip_stop", table_name="trip_updates")
    op.drop_index("ix_trip_updates_feed_entity", table_name="trip_updates")
    op.drop_index("ix_trip_updates_feed_stop", table_name="trip_updates")
    op.drop_index("ix_trip_updates_feed_trip", table_name="trip_updates")
    op.drop_index("ix_trip_updates_feed_id", table_name="trip_updates")
    op.drop_table("trip_updates")
