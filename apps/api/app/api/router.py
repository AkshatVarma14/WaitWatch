"""WaitWatch API — API router."""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.transit import router as transit_router
from app.api.websocket import router as ws_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(transit_router, prefix="/v1", tags=["transit"])
api_router.include_router(transit_router, tags=["transit"])
api_router.include_router(ws_router, prefix="/v1", tags=["websocket"])
api_router.include_router(ws_router, tags=["websocket"])
