"""Real-time GTFS vehicle position snapshot model."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

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


class VehiclePosition(Base):
    """Current vehicle position snapshot for a transit feed.

    Represents a single vehicle entity from a GTFS-Realtime FeedMessage.
    Maintains source GTFS string identifiers without strict foreign keys to
    static tables, supporting partial, unscheduled, or ahead/behind descriptors.
    """

    __tablename__ = "vehicle_positions"
    __table_args__ = (
        UniqueConstraint(
            "feed_id", "entity_id", name="uq_vehicle_positions_feed_entity_id"
        ),
        Index("ix_vehicle_positions_feed_id", "feed_id"),
        Index("ix_vehicle_positions_feed_route", "feed_id", "route_id"),
        Index("ix_vehicle_positions_feed_vehicle", "feed_id", "vehicle_id"),
        Index("ix_vehicle_positions_point", "point", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("transit_feeds.id", ondelete="CASCADE"),
        nullable=False,
    )

    # GTFS-Realtime FeedEntity identifier
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # VehicleDescriptor fields
    vehicle_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vehicle_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    license_plate: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # TripDescriptor source strings (loose coupling, partial descriptors allowed)
    trip_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    route_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    direction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(10), nullable=True)
    start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    schedule_relationship: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Current stop information
    stop_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_stop_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_status: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # 0=INCOMING_AT, 1=STOPPED_AT, 2=IN_TRANSIT_TO

    # Coordinates
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # PostGIS geography point column for spatial queries (GiST indexed)
    point: Mapped[Any | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )

    # Kinematics and telemetry
    bearing: Mapped[float | None] = mapped_column(Float, nullable=True)
    odometer: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Congestion and occupancy
    congestion_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occupancy_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occupancy_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Feed header and vehicle timestamps (timezone-aware)
    feed_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    vehicle_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Local receipt timestamp
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    feed: Mapped["TransitFeed"] = relationship(
        "TransitFeed", back_populates="vehicle_positions"
    )
