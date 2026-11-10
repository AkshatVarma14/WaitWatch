"""WaitWatch API — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.database.session import engine

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
    yield
    logger.info("WaitWatch API shutting down")
    await engine.dispose()


app = FastAPI(
    title="WaitWatch API",
    description="Real-time public transit tracking API",
    version="0.1.0",
    lifespan=lifespan,
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
