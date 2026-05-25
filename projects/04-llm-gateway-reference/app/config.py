"""Application configuration via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # SecretStr keeps the key out of repr()/str()/log dumps; call
    # .get_secret_value() at the single point of use (the OpenAI client).
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    request_timeout_seconds: float = 8.0
    mock_fast_behavior: str = "success"
    mock_premium_behavior: str = "success"
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
