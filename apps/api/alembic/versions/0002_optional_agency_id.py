"""Allow optional agency_id for single-agency GTFS feeds.

Revision ID: 0002_optional_agency_id
Revises: 0001_initial_transit_models
Create Date: 2026-11-10 13:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_optional_agency_id"
down_revision: str | None = "0001_initial_transit_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # GTFS schedule: agency_id is optional if feed contains only one agency
    op.alter_column(
        "agencies",
        "agency_id",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "agencies",
        "agency_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )
