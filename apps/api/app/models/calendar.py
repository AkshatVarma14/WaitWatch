"""Calendar and CalendarDate service schedule models."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
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


class Calendar(Base):
    """Weekly service calendar defining regular operating days and validity dates."""

    __tablename__ = "calendars"
    __table_args__ = (
        UniqueConstraint(
            "feed_id", "service_id", name="uq_calendars_feed_service_id"
        ),
        Index(
            "ix_calendars_feed_service_dates", "feed_id", "start_date", "end_date"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("transit_feeds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_id: Mapped[str] = mapped_column(String(255), nullable=False)

    monday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tuesday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wednesday: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    thursday: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    friday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    saturday: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    sunday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

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
    feed: Mapped["TransitFeed"] = relationship(back_populates="calendars")


class CalendarDate(Base):
    """Specific calendar exception (service added or removed on an explicit date)."""

    __tablename__ = "calendar_dates"
    __table_args__ = (
        UniqueConstraint(
            "feed_id",
            "service_id",
            "date",
            name="uq_calendar_dates_feed_service_date",
        ),
        Index("ix_calendar_dates_feed_date", "feed_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("transit_feeds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_id: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    # 1 = service has been added for the specified date
    # 2 = service has been removed for the specified date
    exception_type: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    feed: Mapped["TransitFeed"] = relationship(back_populates="calendar_dates")
