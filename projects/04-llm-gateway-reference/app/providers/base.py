"""Provider protocol and shared response type."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ProviderResponse:
    """Internal value returned by a Provider.complete() call."""

    text: str
    provider_name: str
    latency_ms: float


@runtime_checkable
class Provider(Protocol):
    """Async LLM provider contract used by the Router.

    Implementations must expose a stable ``name`` (used for chain lookup and
    response attribution) and an async ``complete`` method that either returns
    a ProviderResponse or raises ``UpstreamError`` on failure.
    """

    name: str

    async def complete(self, prompt: str, max_tokens: int) -> ProviderResponse:
        """Generate a completion. Raise ``UpstreamError`` on any upstream failure."""
        ...
