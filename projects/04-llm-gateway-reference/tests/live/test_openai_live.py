"""End-to-end live verification of the OpenAI adapter.

These tests confirm two things against a real OpenAI endpoint:

  1. Happy path — a premium-tier request reaches OpenAI and returns a healthy
     CompletionResponse with provider_used == "openai", no failover.
  2. Forced failover — the same premium-tier request, with the OpenAI provider
     pointed at a non-existent model so the upstream returns a 4xx error. The
     router catches the resulting UpstreamError and falls over to mock_premium.

Both tests write a sanitised JSON artefact under docs/verification/ so the
gateway's behaviour is documented as evidence, not just an in-memory assertion.

Run with:    pytest -m live
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.live.conftest import write_artefact


# A deliberately short, deterministic-ish prompt. We never assert on the
# exact text the model returns — only that it's non-empty — because models
# are not byte-stable.
_PROMPT = "Reply with the single word: pong"
_MAX_TOKENS = 8


pytestmark = pytest.mark.live


def test_happy_path_premium_uses_openai(live_client: TestClient, artefact_dir) -> None:
    """Premium tier with a real key should resolve to provider_used=openai."""
    health = live_client.get("/health").json()
    assert "openai" in health["providers"], (
        "OpenAI provider was not registered — check the key in .env "
        f"and pydantic-settings parsing. health={health}"
    )

    request_body = {"prompt": _PROMPT, "tier": "premium", "max_tokens": _MAX_TOKENS}
    response = live_client.post("/v1/complete", json=request_body)

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["provider_used"] == "openai"
    assert body["tier"] == "premium"
    assert body["failover_occurred"] is False
    assert body["attempts"] == 1
    assert isinstance(body["completion"], str) and body["completion"].strip()
    assert isinstance(body["latency_ms"], (int, float)) and body["latency_ms"] > 0

    write_artefact(
        artefact_dir=artefact_dir,
        scenario="happy-path",
        request_payload=request_body,
        response_payload=body,
    )


def test_forced_failover_to_mock_premium(
    live_client: TestClient,
    artefact_dir,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pointing the OpenAI provider at a non-existent model should trip
    UpstreamError on the first hop, and the router should fail over to
    mock_premium for the second."""
    bad_model = "does-not-exist-2026-bls-test"
    openai_provider = live_client.app.state.registry["openai"]
    monkeypatch.setattr(openai_provider, "_model", bad_model)

    request_body = {"prompt": _PROMPT, "tier": "premium", "max_tokens": _MAX_TOKENS}
    response = live_client.post("/v1/complete", json=request_body)

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["provider_used"] == "mock_premium"
    assert body["failover_occurred"] is True
    assert body["attempts"] == 2
    assert body["tier"] == "premium"

    write_artefact(
        artefact_dir=artefact_dir,
        scenario="forced-failover",
        request_payload=request_body,
        response_payload=body,
        extras={
            "forced_condition": {
                "patched_attribute": "OpenAIProvider._model",
                "value": bad_model,
                "expected_upstream_error": "model_not_found",
            },
        },
    )
