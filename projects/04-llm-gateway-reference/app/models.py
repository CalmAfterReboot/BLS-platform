"""Pydantic v2 request/response models for the gateway."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Tier(str, Enum):
    """Pricing/quality tier requested for a completion."""

    ECONOMY = "economy"
    PREMIUM = "premium"


class CompletionRequest(BaseModel):
    """Inbound completion request from a gateway client."""

    prompt: str = Field(..., min_length=1)
    tier: Tier = Tier.ECONOMY
    max_tokens: int = Field(default=256, ge=1, le=2048)


class CompletionResponse(BaseModel):
    """Outbound completion response, including routing/failover metadata."""

    completion: str
    provider_used: str
    tier: Tier
    failover_occurred: bool
    attempts: int
    latency_ms: float
