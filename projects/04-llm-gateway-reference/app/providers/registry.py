"""Provider registry construction."""

from __future__ import annotations

import logging

from app.config import Settings
from app.providers.base import Provider
from app.providers.mock import MockProvider
from app.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)


def build_registry(settings: Settings) -> dict[str, Provider]:
    """Construct the provider registry from settings."""
    registry: dict[str, Provider] = {
        "mock_fast": MockProvider("mock_fast", settings.mock_fast_behavior),
        "mock_premium": MockProvider("mock_premium", settings.mock_premium_behavior),
    }

    if settings.openai_api_key is not None:
        registry["openai"] = OpenAIProvider(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.openai_model,
        )
    else:
        logger.warning(
            "OpenAI provider unavailable: OPENAI_API_KEY is not set; "
            "only mock providers will be registered"
        )

    return registry
