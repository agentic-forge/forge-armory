"""Application settings using pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="ARMORY_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/forge_armory"

    # Server
    host: str = "0.0.0.0"
    port: int = 8080


# Global settings instance
settings = Settings()
