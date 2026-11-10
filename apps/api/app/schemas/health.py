"""WaitWatch API — Health check schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response schema for the health check endpoint."""

    status: str
    environment: str
    database: str
    version: str
