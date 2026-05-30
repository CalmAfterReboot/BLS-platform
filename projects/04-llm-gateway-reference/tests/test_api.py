"""Integration tests for the FastAPI app via TestClient."""

from __future__ import annotations


def test_health_lists_providers(make_client) -> None:
    client = make_client()

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "mock_fast" in body["providers"]
    assert "mock_premium" in body["providers"]


def test_complete_returns_well_formed_response(make_client) -> None:
    client = make_client()

    response = client.post(
        "/v1/complete",
        json={"prompt": "hello gateway", "tier": "economy", "max_tokens": 32},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider_used"] == "mock_fast"
    assert body["tier"] == "economy"
    assert body["failover_occurred"] is False
    assert body["attempts"] == 1
    assert isinstance(body["completion"], str) and body["completion"]
    assert isinstance(body["latency_ms"], (int, float))
    assert body["latency_ms"] >= 0


def test_complete_rejects_invalid_tier(make_client) -> None:
    client = make_client()

    response = client.post(
        "/v1/complete",
        json={"prompt": "x", "tier": "deluxe"},
    )

    assert response.status_code == 422


def test_all_providers_failing_returns_503_with_envelope(make_client) -> None:
    client = make_client({"mock_fast": "error", "mock_premium": "error"})

    response = client.post(
        "/v1/complete",
        json={"prompt": "x", "tier": "economy"},
    )

    assert response.status_code == 503
    body = response.json()
    assert "error" in body
    error = body["error"]
    assert error["type"] == "AllProvidersFailedError"
    assert error["tier"] == "economy"
    assert error["attempts"] == 2
    assert isinstance(error["message"], str)
