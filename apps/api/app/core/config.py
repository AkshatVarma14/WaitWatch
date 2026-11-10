"""WaitWatch API — Core configuration."""

from urllib.parse import urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Environment
    environment: str = "development"

    # Database
    database_url: str = (
        "postgresql+asyncpg://waitwatch:waitwatch@localhost:5432/waitwatch"
    )
    database_connect_timeout: float = 3.0

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = (
        "http://localhost:5173,http://localhost:3000,http://localhost:80,"
        "http://127.0.0.1:5173,http://127.0.0.1:3000"
    )

    # Transit API keys
    delhi_transit_api_key: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_database_url(cls, v: str | None) -> str:
        """Ensure standard postgresql:// URLs are normalized to postgresql+asyncpg://."""
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v or ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def sanitized_database_url(self) -> str:
        """Return the database URL with credentials safely masked for logging."""
        try:
            parsed = urlsplit(self.database_url)
            if parsed.password:
                user_part = parsed.username or ""
                host_part = parsed.hostname or ""
                netloc = f"{user_part}:***@{host_part}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                return urlunsplit(
                    (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
                )
            return self.database_url
        except Exception:
            return "postgresql+asyncpg://***"


settings = Settings()
