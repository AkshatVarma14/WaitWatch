"""Route transit model."""

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
    from app.models.agency import Agency
    from app.models.feed import TransitFeed
    from app.models.trip import Trip


class Route(Base):
    """Transit route representing a sequence of trips."""

    __tablename__ = "routes"
    __table_args__ = (
        UniqueConstraint("feed_id", "route_id", name="uq_routes_feed_route_id"),
        Index("ix_routes_feed_route_type", "feed_id", "route_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("transit_feeds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agency_id: Mapped[int] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    route_id: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    long_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    route_type: Mapped[int] = mapped_column(Integer, nullable=False)
    route_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    route_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    text_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
    feed: Mapped["TransitFeed"] = relationship(back_populates="routes")
    agency: Mapped["Agency"] = relationship(back_populates="routes")
    trips: Mapped[list["Trip"]] = relationship(
        back_populates="route", cascade="all, delete-orphan"
    )
