"""Trip transit model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
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
    from app.models.route import Route
    from app.models.stop_time import StopTime


class Trip(Base):
    """Specific transit journey along a route."""

    __tablename__ = "trips"
    __table_args__ = (
        UniqueConstraint("feed_id", "trip_id", name="uq_trips_feed_trip_id"),
        Index("ix_trips_feed_service_id", "feed_id", "service_id"),
        Index("ix_trips_feed_shape_id", "feed_id", "shape_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("transit_feeds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    route_id: Mapped[int] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    trip_id: Mapped[str] = mapped_column(String(255), nullable=False)
    trip_headsign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trip_short_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    direction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shape_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wheelchair_accessible: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    bikes_allowed: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    feed: Mapped["TransitFeed"] = relationship(back_populates="trips")
    route: Mapped["Route"] = relationship(back_populates="trips")
    stop_times: Mapped[list["StopTime"]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="StopTime.stop_sequence",
    )
