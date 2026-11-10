"""Stop time transit model."""

from datetime import datetime
from typing import TYPE_CHECKING

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
    from app.models.stop import Stop
    from app.models.trip import Trip


class StopTime(Base):
    """Scheduled arrival and departure time for a trip at a specific stop."""

    __tablename__ = "stop_times"
    __table_args__ = (
        UniqueConstraint(
            "trip_id", "stop_sequence", name="uq_stop_times_trip_sequence"
        ),
        Index("ix_stop_times_stop_arrival", "stop_id", "arrival_time"),
        Index("ix_stop_times_feed_trip", "feed_id", "trip_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("transit_feeds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stop_id: Mapped[int] = mapped_column(
        ForeignKey("stops.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Standard GTFS HH:MM:SS format (can exceed 24:00:00 for overnight journeys)
    arrival_time: Mapped[str] = mapped_column(String(8), nullable=False)
    departure_time: Mapped[str] = mapped_column(String(8), nullable=False)
    stop_sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    stop_headsign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pickup_type: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    drop_off_type: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shape_dist_traveled: Mapped[float | None] = mapped_column(Float, nullable=True)
    timepoint: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    trip: Mapped["Trip"] = relationship(back_populates="stop_times")
    stop: Mapped["Stop"] = relationship(back_populates="stop_times")
    feed: Mapped["TransitFeed"] = relationship()
