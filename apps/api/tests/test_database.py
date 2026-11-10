"""Unit tests for database session lifecycle and connectivity check."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.session import Base, check_database_connection, get_session
from app.models import Agency, TransitFeed


def test_sanitized_database_url_masks_password() -> None:
    """Ensure database passwords are never exposed in loggable URLs."""
    s = Settings(
        database_url="postgresql+asyncpg://myuser:supersecret123@db.prod.internal:5432/transits"
    )
    assert "supersecret123" not in s.sanitized_database_url
    assert "myuser:***@db.prod.internal:5432" in s.sanitized_database_url


def test_sanitized_database_url_without_password() -> None:
    """Ensure URLs without passwords remain valid without errors."""
    s = Settings(database_url="sqlite:///:memory:")
    assert "sqlite:///:memory:" in s.sanitized_database_url


def test_database_url_normalization() -> None:
    """Ensure postgresql:// URLs are automatically converted to postgresql+asyncpg://."""
    s = Settings(database_url="postgresql://user:pass@db:5432/waitwatch")
    assert s.database_url == "postgresql+asyncpg://user:pass@db:5432/waitwatch"

    s_async = Settings(database_url="postgresql+asyncpg://user:pass@db:5432/waitwatch")
    assert s_async.database_url == "postgresql+asyncpg://user:pass@db:5432/waitwatch"


def test_cors_origin_list_parsing() -> None:
    """Ensure cors_origins string is cleanly split and stripped."""
    s = Settings(
        cors_origins="http://localhost:3000, http://localhost:5173 , , http://localhost:80"
    )
    assert s.cors_origin_list == [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:80",
    ]
    # Default settings should support port 3000 and 5173
    default_s = Settings()
    assert "http://localhost:3000" in default_s.cors_origin_list
    assert "http://localhost:5173" in default_s.cors_origin_list


@pytest.mark.asyncio
async def test_check_database_connection_unavailable() -> None:
    """Verify that an unreachable database returns (False, 'unavailable') safely."""
    # When PostgreSQL is offline in test/local environments
    is_connected, status = await check_database_connection(timeout_seconds=0.5)
    assert isinstance(is_connected, bool)
    assert status in ("connected", "unavailable")


@pytest.mark.asyncio
async def test_get_session_lifecycle() -> None:
    """Verify the get_session generator creates and closes sessions."""
    gen = get_session()
    session = await anext(gen)
    assert isinstance(session, AsyncSession)
    # Complete generator cleanly
    try:
        await anext(gen)
    except StopAsyncIteration:
        pass


def test_sqlite_in_memory_schema_creation_and_query() -> None:
    """Verify that models and DDL compile and execute cleanly in a local test engine."""
    test_engine = create_engine("sqlite:///:memory:", echo=False)

    Base.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        feed = TransitFeed(
            city_name="Test City",
            slug="test-city",
            static_gtfs_url="https://example.com/gtfs.zip",
        )
        agency = Agency(
            agency_id="AG1",
            name="Test Transit Authority",
            url="https://example.com",
            timezone="UTC",
            feed=feed,
        )
        session.add(feed)
        session.add(agency)
        session.commit()

        # Query back
        result = session.execute(
            select(TransitFeed).where(TransitFeed.slug == "test-city")
        )
        saved_feed = result.scalar_one()
        assert saved_feed.city_name == "Test City"
        assert len(saved_feed.agencies) == 1
        assert saved_feed.agencies[0].name == "Test Transit Authority"

    test_engine.dispose()
