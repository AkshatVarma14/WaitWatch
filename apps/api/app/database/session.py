"""WaitWatch API — Database engine, session management, and connectivity."""

import asyncio
import logging
from collections.abc import AsyncGenerator

from geoalchemy2 import Geography
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

# Register SQLite fallback compilation for GeoAlchemy2 Geography
# to enable in-memory SQLite unit testing without requiring SpatiaLite.
@compiles(Geography, "sqlite")
def _compile_geography_sqlite(type_: Geography, compiler: object, **kw: object) -> str:
    return "BLOB"


class Base(DeclarativeBase):
    """Declarative base class for all WaitWatch database models."""

    pass


engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency providing an async database session with automatic cleanup."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_connection(
    timeout_seconds: float | None = None,
) -> tuple[bool, str]:
    """Perform a real database connectivity check without leaking credentials.

    Returns:
        tuple[bool, str]: (is_connected, status_description)
    """
    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else settings.database_connect_timeout
    )
    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                return True, "connected"
    except TimeoutError:
        logger.warning(
            "Database connectivity check timed out after %.1fs on %s",
            timeout,
            settings.sanitized_database_url,
        )
        return False, "unavailable"
    except Exception as exc:
        # Log the error category without printing sensitive connection strings
        logger.warning(
            "Database connectivity check failed on %s: %s",
            settings.sanitized_database_url,
            type(exc).__name__,
        )
        return False, "unavailable"
