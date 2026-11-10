"""Unit tests for Alembic migration configuration and scripts."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_config_resolves() -> None:
    """Verify alembic.ini is discoverable and configured properly."""
    api_dir = Path(__file__).resolve().parent.parent
    ini_path = api_dir / "alembic.ini"
    assert ini_path.is_file(), f"Missing alembic.ini at {ini_path}"

    alembic_cfg = Config(str(ini_path))
    script = ScriptDirectory.from_config(alembic_cfg)

    # Verify initial migration is present
    heads = script.get_heads()
    assert len(heads) == 1
    assert heads[0] == "0001_initial_transit_models"

    rev = script.get_revision("0001_initial_transit_models")
    assert rev is not None
    assert rev.down_revision is None
    assert "transit models" in (rev.doc or "").lower()


def test_migration_environment_settings_integration() -> None:
    """Verify that the Alembic environment uses app settings for database URL."""
    api_dir = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(api_dir / "alembic.ini"))
    configured_url = alembic_cfg.get_main_option("sqlalchemy.url")
    assert configured_url is not None
    assert "postgresql+asyncpg://" in configured_url
