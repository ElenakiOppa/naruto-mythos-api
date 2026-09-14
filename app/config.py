"""
Application configuration.

All configuration is sourced from environment variables (optionally loaded
from a local .env file in development). Required configuration is validated
eagerly via Pydantic so the application fails fast on startup rather than
failing unpredictably later.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_VERSION = "1.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(alias="DATABASE_URL", repr=False)
    docs_enabled: bool = Field(default=True, alias="DOCS_ENABLED")
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    port: int = Field(default=8000, alias="PORT")

    @field_validator("database_url")
    @classmethod
    def database_url_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("DATABASE_URL must be set")
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS_ORIGINS variable into a list."""
        if not self.cors_origins.strip():
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so environment parsing/validation only happens once per process,
    while still being easy to override in tests via dependency overrides or
    by clearing the cache (get_settings.cache_clear()).
    """
    return Settings()  # type: ignore[call-arg]  # Required values come from environment.
