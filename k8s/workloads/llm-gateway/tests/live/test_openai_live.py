"""End-to-end live verification of the LiteLLM → OpenAI path.

These tests confirm two things against a real OpenAI endpoint, using the
LiteLLM Python SDK — the same library the deployed ``litellm`` container in
``templates/deployment-litellm.yaml`` runs:

  1. Happy path — ``litellm.completion(model="openai/gpt-4o-mini", ...)``
     returns a healthy completion with no fallback.
  2. Forced failover — ``litellm.Router`` configured with a non-existent
     primary model and ``gpt-4o-mini`` as fallback. The router catches the
     OpenAI 404 and falls over to the working model.

Both tests write a sanitised JSON artefact under ``docs/verification/`` so the
verification path is documented as evidence, not just an in-memory assertion.

Run with:    pytest -m live
"""

from __future__ import annotations

import time
from typing import Any

import litellm
import pytest

from tests.live.conftest import write_artefact


# A deliberately short, deterministic-ish prompt. We never assert on the
# exact text the model returns — only that it's non-empty — because models
# are not byte-stable.
_PROMPT = "Reply with the single word: pong"
_MAX_TOKENS = 8
_HAPPY_MODEL = "openai/gpt-4o-mini"
_BAD_MODEL = "openai/does-not-exist-2026-bls-test"


pytestmark = pytest.mark.live


def _sanitised_response(
    response: Any,
    *,
    attempts: int,
    latency_ms: float,
    failover_occurred: bool,
    model_used: str,
) -> dict[str, Any]:
    """Build a sanitised envelope from a LiteLLM ``ModelResponse``.

    Mirrors the shape of bls-ai-gateway's ``CompletionResponse`` — public
    fields only, no upstream IDs, no headers, no auth material.
    """
    choice = response.choices[0]
    content = getattr(choice.message, "content", None) or ""
    return {
        "model_used": model_used,
        "completion": content,
        "attempts": attempts,
        "failover_occurred": failover_occurred,
        "latency_ms": latency_ms,
        "finish_reason": getattr(choice, "finish_reason", None),
    }


def test_happy_path_openai_via_litellm(artefact_dir) -> None:
    """A direct ``litellm.completion`` call to gpt-4o-mini should succeed cleanly."""
    request_body = {
        "model": _HAPPY_MODEL,
        "messages": [{"role": "user", "content": _PROMPT}],
        "max_tokens": _MAX_TOKENS,
    }

    start = time.perf_counter()
    response = litellm.completion(**request_body)
    latency_ms = (time.perf_counter() - start) * 1000.0

    assert response.choices, "no choices in LiteLLM response"
    content = response.choices[0].message.content
    assert (
        isinstance(content, str) and content.strip()
    ), f"empty completion from {_HAPPY_MODEL}; response={response}"

    sanitised = _sanitised_response(
        response,
        attempts=1,
        latency_ms=latency_ms,
        failover_occurred=False,
        model_used=_HAPPY_MODEL,
    )

    write_artefact(
        artefact_dir=artefact_dir,
        scenario="happy-path",
        request_payload=request_body,
        response_payload=sanitised,
    )


def test_forced_failover_openai_via_litellm_router(artefact_dir) -> None:
    """LiteLLM Router with a bad primary and gpt-4o-mini as fallback should
    fall over on the OpenAI 404 and serve the response from the fallback."""
    primary_alias = "bad-primary"
    fallback_alias = "gpt-4o-mini-fallback"

    router = litellm.Router(
        model_list=[
            {
                "model_name": primary_alias,
                "litellm_params": {"model": _BAD_MODEL, "max_retries": 0},
            },
            {
                "model_name": fallback_alias,
                "litellm_params": {"model": _HAPPY_MODEL},
            },
        ],
        fallbacks=[{primary_alias: [fallback_alias]}],
        num_retries=0,
    )

    request_body = {
        "model": primary_alias,
        "messages": [{"role": "user", "content": _PROMPT}],
        "max_tokens": _MAX_TOKENS,
    }

    start = time.perf_counter()
    response = router.completion(**request_body)
    latency_ms = (time.perf_counter() - start) * 1000.0

    assert response.choices, "no choices in fallback response"
    content = response.choices[0].message.content
    assert (
        isinstance(content, str) and content.strip()
    ), f"empty completion after failover; response={response}"

    # Verify the actual model that served the response was the fallback, not
    # the broken primary. LiteLLM surfaces the resolved model in response.model.
    resolved_model = response.model or ""
    assert (
        "gpt-4o-mini" in resolved_model.lower()
    ), f"forced failover did not land on gpt-4o-mini; got model={resolved_model!r}"

    sanitised = _sanitised_response(
        response,
        attempts=2,
        latency_ms=latency_ms,
        failover_occurred=True,
        model_used=resolved_model,
    )

    write_artefact(
        artefact_dir=artefact_dir,
        scenario="forced-failover",
        request_payload=request_body,
        response_payload=sanitised,
        extras={
            "forced_condition": {
                "primary_alias": primary_alias,
                "primary_model": _BAD_MODEL,
                "fallback_alias": fallback_alias,
                "fallback_model": _HAPPY_MODEL,
                "expected_upstream_error": "model_not_found (404)",
            },
        },
    )
