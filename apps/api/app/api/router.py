"""WaitWatch API — API router."""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.transit import router as transit_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(transit_router, prefix="/v1", tags=["transit"])
api_router.include_router(transit_router, tags=["transit"])
