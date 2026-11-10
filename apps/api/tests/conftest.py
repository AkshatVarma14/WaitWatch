"""Global pytest configuration and fixtures for WaitWatch API tests."""

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure test environment is active for all test runs."""
    monkeypatch.setattr(settings, "environment", "test")
