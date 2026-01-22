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

    # Tool RAG settings
    toolrag_enabled: bool = True
    toolrag_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    toolrag_default_threshold: float = 0.5


# Global settings instance
settings = Settings()
