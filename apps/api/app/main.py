"""WaitWatch API — FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError

from app.api.router import api_router
from app.core.config import settings
from app.database.session import engine
from app.services.realtime.db_listener import run_db_listener
from app.services.realtime.websocket_manager import ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Handle application startup and shutdown."""
    logger.info(
        "WaitWatch API starting up (env=%s, db=%s)",
        settings.environment,
        settings.sanitized_database_url,
    )
    stop_event = asyncio.Event()
    listener_task = asyncio.create_task(run_db_listener(ws_manager, stop_event))
    yield
    logger.info("WaitWatch API shutting down")
    stop_event.set()
    listener_task.cancel()
    try:
        await asyncio.wait_for(listener_task, timeout=2.0)
    except (TimeoutError, asyncio.CancelledError):
        pass
    await ws_manager.close_all()
    await engine.dispose()


app = FastAPI(
    title="WaitWatch API",
    description="Real-time public transit tracking API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(OperationalError)
async def operational_error_handler(
    request: Request, exc: OperationalError
) -> JSONResponse:
    """Sanitize database operational/connection errors into 503 responses."""
    logger.warning("Database unavailable: %s", type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database service is temporarily unavailable"},
    )


@app.exception_handler(DBAPIError)
async def dbapi_error_handler(request: Request, exc: DBAPIError) -> JSONResponse:
    """Sanitize database DBAPI errors into 503 responses."""
    logger.warning("Database error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database service is temporarily unavailable"},
    )


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "name": "WaitWatch API",
        "version": "0.1.0",
        "docs": "/docs",
    }
