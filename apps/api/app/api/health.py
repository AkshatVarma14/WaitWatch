"""WaitWatch API — Health check endpoint."""

import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.database.session import engine
from app.schemas.health import HealthResponse

router = APIRouter()
logger = logging.getLogger(__name__)

APP_VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check application health including database connectivity."""
    db_status = "unchecked"

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        db_status = "unavailable"

    return HealthResponse(
        status="healthy",
        environment=settings.environment,
        database=db_status,
        version=APP_VERSION,
    )
