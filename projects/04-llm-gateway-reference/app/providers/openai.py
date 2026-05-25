"""OpenAI-backed provider."""

from __future__ import annotations

import logging
import time

from openai import AsyncOpenAI
from openai import OpenAIError

from app.errors import UpstreamError
from app.providers.base import ProviderResponse

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """Provider backed by the official openai AsyncOpenAI client."""

    name: str = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        """Construct the provider. The AsyncOpenAI client is built eagerly but performs no I/O."""
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key)

    async def complete(self, prompt: str, max_tokens: int) -> ProviderResponse:
        """Call OpenAI chat.completions and translate any SDK failure into UpstreamError."""
        started = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except OpenAIError as exc:
            logger.warning("openai provider call failed: %s", exc)
            raise UpstreamError(self.name, str(exc)) from exc
        except Exception as exc:  # network/SDK-adjacent failures
            logger.warning("openai provider call failed with unexpected error: %s", exc)
            raise UpstreamError(self.name, str(exc)) from exc

        latency_ms = (time.perf_counter() - started) * 1000.0
        choice = response.choices[0] if response.choices else None
        text = (choice.message.content or "") if choice is not None else ""
        return ProviderResponse(
            text=text,
            provider_name=self.name,
            latency_ms=latency_ms,
        )
