"""Mock provider for local development and tests."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Literal

from app.errors import UpstreamError
from app.providers.base import ProviderResponse

logger = logging.getLogger(__name__)

Behavior = Literal["success", "error", "timeout"]

_SUCCESS_MIN_LATENCY_S = 0.05
_SUCCESS_MAX_LATENCY_S = 0.15
_TIMEOUT_SLEEP_S = 30.0


class MockProvider:
    """Configurable mock provider used to exercise routing/failover."""

    def __init__(self, name: str, behavior: str) -> None:
        """Build a mock provider with the given name and behavior flag.

        ``behavior`` must be one of ``"success"``, ``"error"``, or ``"timeout"``.
        """
        if behavior not in ("success", "error", "timeout"):
            raise ValueError(
                f"MockProvider behavior must be 'success' | 'error' | 'timeout', got {behavior!r}"
            )
        self.name = name
        self.behavior: Behavior = behavior  # type: ignore[assignment]

    async def complete(self, prompt: str, max_tokens: int) -> ProviderResponse:
        """Return a canned completion, raise UpstreamError, or stall — per the configured behavior."""
        started = time.perf_counter()

        if self.behavior == "error":
            logger.warning("mock provider %s configured to error", self.name)
            raise UpstreamError(self.name, "mock provider configured to fail")

        if self.behavior == "timeout":
            logger.warning(
                "mock provider %s sleeping %.1fs to force timeout", self.name, _TIMEOUT_SLEEP_S
            )
            await asyncio.sleep(_TIMEOUT_SLEEP_S)
            # Unreachable under normal router timeouts; included for protocol completeness.
            latency_ms = (time.perf_counter() - started) * 1000.0
            return ProviderResponse(
                text=f"[{self.name}] late response",
                provider_name=self.name,
                latency_ms=latency_ms,
            )

        # success path
        await asyncio.sleep(random.uniform(_SUCCESS_MIN_LATENCY_S, _SUCCESS_MAX_LATENCY_S))
        latency_ms = (time.perf_counter() - started) * 1000.0
        text = f"[{self.name}] echo (max_tokens={max_tokens}): {prompt}"
        return ProviderResponse(
            text=text,
            provider_name=self.name,
            latency_ms=latency_ms,
        )
