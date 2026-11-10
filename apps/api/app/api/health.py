"""WaitWatch API — Health check endpoint."""

from fastapi import APIRouter

from app.core.config import settings
from app.database.session import check_database_connection
from app.schemas.health import HealthResponse

router = APIRouter()

APP_VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check application health including database connectivity.

    Accurately verifies PostgreSQL connectivity without leaking credentials.
    """
    _, db_status = await check_database_connection()

    return HealthResponse(
        status="healthy",
        environment=settings.environment,
        database=db_status,
        version=APP_VERSION,
    )
