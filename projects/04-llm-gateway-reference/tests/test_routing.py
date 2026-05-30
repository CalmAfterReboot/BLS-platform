"""Unit tests for app.routing.Router."""

from __future__ import annotations

import pytest

from app.errors import AllProvidersFailedError
from app.models import CompletionRequest, Tier


async def test_economy_succeeds_on_primary(make_router) -> None:
    router = make_router({"mock_fast": "success", "mock_premium": "success"})

    response = await router.route(CompletionRequest(prompt="hello", tier=Tier.ECONOMY))

    assert response.provider_used == "mock_fast"
    assert response.failover_occurred is False
    assert response.attempts == 1
    assert response.tier is Tier.ECONOMY


async def test_premium_resolves_to_expected_primary(make_router) -> None:
    # With no "openai" provider registered, the premium chain shortens to
    # ["mock_premium"], which becomes the effective primary.
    router = make_router({"mock_fast": "success", "mock_premium": "success"})

    assert router.effective_chain(Tier.PREMIUM) == ["mock_premium"]

    response = await router.route(CompletionRequest(prompt="hello", tier=Tier.PREMIUM))

    assert response.provider_used == "mock_premium"
    assert response.failover_occurred is False
    assert response.attempts == 1


async def test_failover_when_primary_errors(make_router) -> None:
    router = make_router({"mock_fast": "error", "mock_premium": "success"})

    response = await router.route(CompletionRequest(prompt="hello", tier=Tier.ECONOMY))

    assert response.provider_used == "mock_premium"
    assert response.failover_occurred is True
    assert response.attempts == 2


async def test_failover_when_primary_times_out(make_router) -> None:
    # Budget must clear the mock-success path's max sleep (~0.15s) so only
    # the "timeout" mock (which sleeps 30s) trips the deadline.
    router = make_router(
        {"mock_fast": "timeout", "mock_premium": "success"},
        request_timeout_seconds=0.5,
    )

    response = await router.route(CompletionRequest(prompt="hello", tier=Tier.ECONOMY))

    assert response.provider_used == "mock_premium"
    assert response.failover_occurred is True
    assert response.attempts == 2


async def test_all_providers_failing_raises(make_router) -> None:
    router = make_router({"mock_fast": "error", "mock_premium": "error"})

    with pytest.raises(AllProvidersFailedError) as exc_info:
        await router.route(CompletionRequest(prompt="hello", tier=Tier.ECONOMY))

    assert exc_info.value.tier is Tier.ECONOMY
    assert exc_info.value.attempts == 2
