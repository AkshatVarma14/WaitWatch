"""Allow realtime-only feeds and query-based provider API keys.

Revision ID: 0007_live_only_feeds
Revises: 0006_trip_updates
Create Date: 2026-11-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_live_only_feeds"
down_revision: str | None = "0006_trip_updates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column(
        "transit_feeds",
        "static_gtfs_url",
        existing_type=sa.String(length=2048),
        nullable=True,
    )
    op.add_column(
        "transit_feeds",
        sa.Column("api_key_query_param", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transit_feeds", "api_key_query_param")
    op.execute(
        "UPDATE transit_feeds SET static_gtfs_url = '' WHERE static_gtfs_url IS NULL"
    )
    op.alter_column(
        "transit_feeds",
        "static_gtfs_url",
        existing_type=sa.String(length=2048),
        nullable=False,
    )
