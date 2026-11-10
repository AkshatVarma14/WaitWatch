"""Tests for WaitWatch API root and health endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient) -> None:
    """Test that the root endpoint returns expected data."""
    async with client:
        response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "WaitWatch API"
    assert "version" in data
    assert data["docs"] == "/docs"


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    """Test that the health endpoint returns expected structure."""
    async with client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" in data
    assert "database" in data
    assert "version" in data
    # Database should be 'unavailable' in test environment (no real DB)
    assert data["database"] in ("connected", "unavailable")
