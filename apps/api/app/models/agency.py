"""Agency transit model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.feed import TransitFeed
    from app.models.route import Route


class Agency(Base):
    """Transit agency providing services within a feed/city."""

    __tablename__ = "agencies"
    __table_args__ = (
        UniqueConstraint(
            "feed_id", "agency_id", name="uq_agencies_feed_agency_id"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("transit_feeds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agency_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lang: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fare_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

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
    feed: Mapped["TransitFeed"] = relationship(back_populates="agencies")
    routes: Mapped[list["Route"]] = relationship(
        back_populates="agency", cascade="all, delete-orphan"
    )
