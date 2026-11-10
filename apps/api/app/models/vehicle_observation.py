"""Historical vehicle observation model."""

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


class VehicleObservation(Base):
    """Historical vehicle position sample for a transit feed.

    Maintains append-only observation history for historical delay analysis,
    speed profiling, and arrival estimation (ETA). Scoped to a TransitFeed with
    idempotent deduplication based on (feed_id, entity_id, observed_at).
    """

    __tablename__ = "vehicle_observations"
    __table_args__ = (
        UniqueConstraint(
            "feed_id",
            "entity_id",
            "observed_at",
            name="uq_vehicle_observations_feed_entity_observed_at",
        ),
        Index("ix_vehicle_obs_feed_id", "feed_id"),
        Index(
            "ix_vehicle_obs_feed_vehicle_time",
            "feed_id",
            "vehicle_id",
            "observed_at",
        ),
        Index(
            "ix_vehicle_obs_feed_route_time",
            "feed_id",
            "route_id",
            "observed_at",
        ),
        Index("ix_vehicle_obs_feed_observed_at", "feed_id", "observed_at"),
        Index("ix_vehicle_obs_point", "point", postgresql_using="gist"),
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

    # TripDescriptor source strings
    trip_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    route_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    direction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(10), nullable=True)
    start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    schedule_relationship: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Current stop information
    stop_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_stop_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_status: Mapped[int | None] = mapped_column(Integer, nullable=True)

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

    # Canonical observation timestamp for deduplication:
    # Uses vehicle_timestamp when available, falls back to feed_timestamp,
    # or ingestion receipt time when source timestamps are absent.
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Raw distinct source timestamps
    vehicle_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    feed_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Server receipt timestamp
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    feed: Mapped["TransitFeed"] = relationship(
        "TransitFeed", back_populates="vehicle_observations"
    )
