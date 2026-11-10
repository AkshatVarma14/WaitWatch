"""Transit feed and city configuration model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.agency import Agency
    from app.models.calendar import Calendar, CalendarDate
    from app.models.route import Route
    from app.models.shape import Shape
    from app.models.stop import Stop
    from app.models.trip import Trip
    from app.models.vehicle_observation import VehicleObservation
    from app.models.vehicle_position import VehiclePosition


class TransitFeed(Base):
    """Configuration for a transit agency feed / city."""

    __tablename__ = "transit_feeds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city_name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    static_gtfs_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    realtime_vehicle_positions_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    realtime_trip_updates_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )
    realtime_alerts_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Reference to the environment variable holding the transit API key
    # (never store the raw key)
    api_key_env_var: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Operational status: active, inactive, error, maintenance
    feed_status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False
    )
    is_live_tracking_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Operational timestamps (timezone-aware)
    last_static_import_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_realtime_poll_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    agencies: Mapped[list["Agency"]] = relationship(
        back_populates="feed", cascade="all, delete-orphan"
    )
    routes: Mapped[list["Route"]] = relationship(
        back_populates="feed", cascade="all, delete-orphan"
    )
    stops: Mapped[list["Stop"]] = relationship(
        back_populates="feed", cascade="all, delete-orphan"
    )
    trips: Mapped[list["Trip"]] = relationship(
        back_populates="feed", cascade="all, delete-orphan"
    )
    calendars: Mapped[list["Calendar"]] = relationship(
        back_populates="feed", cascade="all, delete-orphan"
    )
    calendar_dates: Mapped[list["CalendarDate"]] = relationship(
        back_populates="feed", cascade="all, delete-orphan"
    )
    shapes: Mapped[list["Shape"]] = relationship(
        back_populates="feed", cascade="all, delete-orphan"
    )
    vehicle_positions: Mapped[list["VehiclePosition"]] = relationship(
        back_populates="feed",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    vehicle_observations: Mapped[list["VehicleObservation"]] = relationship(
        back_populates="feed",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
