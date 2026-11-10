"""Real-time GTFS trip update and stop time prediction snapshot model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.feed import TransitFeed


class TripUpdate(Base):
    """Current GTFS-Realtime trip update and stop time prediction snapshot.

    Represents a trip update and its constituent stop time updates from a
    GTFS-Realtime FeedMessage. Maintains feed-scoped identifiers without
    strict static foreign keys to accommodate added, detoured, or partial trips.
    """

    __tablename__ = "trip_updates"
    __table_args__ = (
        Index("ix_trip_updates_feed_id", "feed_id"),
        Index("ix_trip_updates_feed_trip", "feed_id", "trip_id"),
        Index("ix_trip_updates_feed_stop", "feed_id", "stop_id"),
        Index("ix_trip_updates_feed_entity", "feed_id", "entity_id"),
        Index("ix_trip_updates_trip_stop", "feed_id", "trip_id", "stop_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("transit_feeds.id", ondelete="CASCADE"),
        nullable=False,
    )

    # GTFS-Realtime FeedEntity identifier
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # TripDescriptor source strings (loose coupling, partial descriptors allowed)
    trip_id: Mapped[str] = mapped_column(String(255), nullable=False)
    route_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    direction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(10), nullable=True)
    start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    schedule_relationship: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # 0=SCHEDULED, 1=ADDED, 2=UNSCHEDULED, 3=CANCELED, etc.

    # VehicleDescriptor fields (optional reference to vehicle running this trip)
    vehicle_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vehicle_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vehicle_license_plate: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # StopTimeUpdate fields
    stop_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stop_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Arrival event
    arrival_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    arrival_delay: Mapped[int | None] = mapped_column(Integer, nullable=True)
    arrival_uncertainty: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Departure event
    departure_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    departure_delay: Mapped[int | None] = mapped_column(Integer, nullable=True)
    departure_uncertainty: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Stop-level schedule relationship: 0=SCHEDULED, 1=SKIPPED, 2=NO_DATA
    stop_schedule_relationship: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # Trip-level delay from TripUpdate (seconds)
    trip_delay: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    update_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    feed_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
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
    feed: Mapped["TransitFeed"] = relationship(
        "TransitFeed", back_populates="trip_updates"
    )
