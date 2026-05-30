"""Shared pytest fixtures for the BLS AI Gateway test suite."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Callable

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.providers.base import Provider
from app.providers.mock import MockProvider
from app.routing import Router

RouterFactory = Callable[..., Router]
ClientFactory = Callable[..., TestClient]


def _build_registry(behaviors: dict[str, str]) -> dict[str, Provider]:
    """Materialize a registry of MockProviders keyed by the chain names."""
    return {name: MockProvider(name, behavior) for name, behavior in behaviors.items()}


@pytest.fixture
def make_router() -> RouterFactory:
    """Factory: build a Router from a {provider_name: behavior} mapping."""

    def _make(
        behaviors: dict[str, str],
        *,
        request_timeout_seconds: float = 8.0,
    ) -> Router:
        registry = _build_registry(behaviors)
        settings = Settings(
            openai_api_key=None,
            request_timeout_seconds=request_timeout_seconds,
        )
        return Router(registry, settings)

    return _make


@pytest.fixture
def make_client() -> Iterator[ClientFactory]:
    """Factory: build a TestClient whose registry/router are overridden with mocks.

    The lifespan still runs (so app.state is populated with the default
    registry first), then we overwrite app.state with the test-controlled
    registry and Router before yielding the client.
    """
    created: list[TestClient] = []

    def _make(
        behaviors: dict[str, str] | None = None,
        *,
        request_timeout_seconds: float = 8.0,
    ) -> TestClient:
        effective = behaviors or {"mock_fast": "success", "mock_premium": "success"}
        registry = _build_registry(effective)
        settings = Settings(
            openai_api_key=None,
            request_timeout_seconds=request_timeout_seconds,
        )
        router = Router(registry, settings)

        client = TestClient(app)
        # Enter the TestClient context manually so we can override app.state
        # AFTER the lifespan has populated its defaults but BEFORE any request
        # hits the routes.
        client.__enter__()
        app.state.registry = registry
        app.state.router = router
        app.state.settings = settings
        created.append(client)
        return client

    yield _make

    for client in created:
        client.__exit__(None, None, None)
