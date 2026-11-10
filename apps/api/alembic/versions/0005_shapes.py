"""Create shapes table for route geometry with PostGIS spatial index.

Revision ID: 0005_shapes
Revises: 0004_vehicle_observations
Create Date: 2026-11-10 16:15:00.000000

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_shapes"
down_revision: str | None = "0004_vehicle_observations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shapes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("shape_id", sa.String(length=255), nullable=False),
        sa.Column("shape_pt_lat", sa.Float(), nullable=False),
        sa.Column("shape_pt_lon", sa.Float(), nullable=False),
        sa.Column("shape_pt_sequence", sa.Integer(), nullable=False),
        sa.Column("shape_dist_traveled", sa.Float(), nullable=True),
        sa.Column(
            "point",
            geoalchemy2.types.Geography(
                geometry_type="POINT", srid=4326, spatial_index=False
            ),
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
        sa.ForeignKeyConstraint(["feed_id"], ["transit_feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "feed_id",
            "shape_id",
            "shape_pt_sequence",
            name="uq_shapes_feed_shape_seq",
        ),
    )
    op.create_index(
        "ix_shapes_feed_id",
        "shapes",
        ["feed_id"],
        unique=False,
    )
    op.create_index(
        "ix_shapes_feed_shape_id",
        "shapes",
        ["feed_id", "shape_id"],
        unique=False,
    )
    op.create_index(
        "ix_shapes_feed_shape_seq",
        "shapes",
        ["feed_id", "shape_id", "shape_pt_sequence"],
        unique=False,
    )
    op.create_index(
        "ix_shapes_point",
        "shapes",
        ["point"],
        unique=False,
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_shapes_point",
        table_name="shapes",
        postgresql_using="gist",
    )
    op.drop_index("ix_shapes_feed_shape_seq", table_name="shapes")
    op.drop_index("ix_shapes_feed_shape_id", table_name="shapes")
    op.drop_index("ix_shapes_feed_id", table_name="shapes")
    op.drop_table("shapes")
