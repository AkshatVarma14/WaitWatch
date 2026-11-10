"""Stop transit model with geospatial PostGIS support."""

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
    from app.models.stop_time import StopTime


class Stop(Base):
    """Transit stop, station, or platform with geospatial awareness."""

    __tablename__ = "stops"
    __table_args__ = (
        UniqueConstraint("feed_id", "stop_id", name="uq_stops_feed_stop_id"),
        Index("ix_stops_feed_name", "feed_id", "name"),
        Index("ix_stops_point", "point", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("transit_feeds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stop_id: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Standard WGS84 coordinate columns for fast coordinate access
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # PostGIS geography point column for spatial queries (ST_DWithin, distance)
    # spatial_index=False allows explicit GiST index definition
    # compatible with SQLite testing
    point: Mapped[Any | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )

    # Station hierarchy (parent station / platform relationship)
    parent_station_id: Mapped[int | None] = mapped_column(
        ForeignKey("stops.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    location_type: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wheelchair_boarding: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    platform_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)

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
    feed: Mapped["TransitFeed"] = relationship(back_populates="stops")
    parent_station: Mapped["Stop | None"] = relationship(
        back_populates="child_stops", remote_side=[id]
    )
    child_stops: Mapped[list["Stop"]] = relationship(
        back_populates="parent_station", foreign_keys=[parent_station_id]
    )
    stop_times: Mapped[list["StopTime"]] = relationship(
        back_populates="stop", cascade="all, delete-orphan"
    )
