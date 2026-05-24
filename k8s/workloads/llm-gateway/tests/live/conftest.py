"""Fixtures for live tests that hit real upstream providers via LiteLLM.

These tests are gated behind the ``live`` pytest marker and skipped by default
(see ``pyproject.toml`` addopts). They require ``OPENAI_API_KEY`` to be present
in ``.env`` or the process environment; a missing key short-circuits with a
clear skip message rather than failing inside the LiteLLM SDK.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv


CHART_ROOT = Path(__file__).resolve().parents[2]
ARTEFACT_DIR = CHART_ROOT / "docs" / "verification"


@pytest.fixture(scope="session", autouse=True)
def _require_live_key() -> None:
    """Skip the whole live test module if no real OpenAI key is available.

    Loads ``.env`` from the chart root, then probes ``os.environ`` so the
    test honours a key in ``.env`` even when the user hasn't exported it into
    their shell.
    """
    load_dotenv(CHART_ROOT / ".env")
    key = os.environ.get("OPENAI_API_KEY")
    # Treat both "unset" and "set-but-empty" as missing — an empty string
    # would otherwise sneak past a falsy check and crash inside the LiteLLM
    # SDK with a less helpful message than this skip line.
    if not key:
        pytest.skip(
            "OPENAI_API_KEY not set (or empty) in environment or .env; "
            "live tests require a real key.",
            allow_module_level=True,
        )


@pytest.fixture
def artefact_dir() -> Path:
    """Ensure the artefact directory exists; return it as a Path."""
    ARTEFACT_DIR.mkdir(parents=True, exist_ok=True)
    return ARTEFACT_DIR


def write_artefact(
    *,
    artefact_dir: Path,
    scenario: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    extras: dict[str, Any] | None = None,
) -> Path:
    """Persist a sanitised verification artefact as JSON.

    Committed to the repo as evidence the live path works. The payload is
    built strictly from the test inputs and a sanitised view of the LiteLLM
    response (no headers, no ``Authorization``, no API key, no upstream
    request IDs).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target = artefact_dir / f"openai-live-{scenario}-{today}.json"
    body: dict[str, Any] = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scenario": scenario,
        "openai_model_env": os.environ.get("OPENAI_MODEL", "gpt-4o-mini (default)"),
        "request": request_payload,
        "response": response_payload,
    }
    if extras:
        body["extras"] = extras
    target.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    return target
