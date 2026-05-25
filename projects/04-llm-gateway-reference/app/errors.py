"""Gateway exception hierarchy."""

from __future__ import annotations

from app.models import Tier


class GatewayError(Exception):
    """Base class for all gateway errors."""


class UpstreamError(GatewayError):
    """A provider call failed."""

    def __init__(self, provider_name: str, message: str) -> None:
        self.provider_name = provider_name
        super().__init__(f"{provider_name}: {message}")


class AllProvidersFailedError(GatewayError):
    """Every provider in the chain failed."""

    def __init__(self, tier: Tier, attempts: int) -> None:
        self.tier = tier
        self.attempts = attempts
        super().__init__(f"All providers failed for tier={tier.value} after {attempts} attempt(s)")
