"""Shape point transit model for route geometry."""

from datetime import datetime
from typing import TYPE_CHECKING

from geoalchemy2 import Geography
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.feed import TransitFeed


class Shape(Base):
    """GTFS shape point describing the physical path taken by transit vehicles."""

    __tablename__ = "shapes"
    __table_args__ = (
        UniqueConstraint(
            "feed_id", "shape_id", "shape_pt_sequence", name="uq_shapes_feed_shape_seq"
        ),
        Index("ix_shapes_feed_shape_id", "feed_id", "shape_id"),
        Index("ix_shapes_feed_shape_seq", "feed_id", "shape_id", "shape_pt_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("transit_feeds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shape_id: Mapped[str] = mapped_column(String(255), nullable=False)
    shape_pt_lat: Mapped[float] = mapped_column(Float, nullable=False)
    shape_pt_lon: Mapped[float] = mapped_column(Float, nullable=False)
    shape_pt_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    shape_dist_traveled: Mapped[float | None] = mapped_column(Float, nullable=True)

    point = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    feed: Mapped["TransitFeed"] = relationship("TransitFeed", back_populates="shapes")
