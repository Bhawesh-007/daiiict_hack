"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Settings loaded from .env or environment variables."""

    database_connection_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
    )
    database_echo: bool = False
    app_name: str = "Emission Source Identification API"
    debug: bool = False

    model_config = {
        "env_file": PROJECT_ROOT / ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def async_database_url(self) -> str:
        """Return the URL with asyncpg driver."""
        url = self.database_connection_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def sync_database_url(self) -> str:
        """Return the URL with psycopg2 driver (for Alembic)."""
        url = self.database_connection_url
        if "+asyncpg" in url:
            url = url.replace("+asyncpg", "", 1)
        if url.startswith("postgresql://"):
            return url
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
