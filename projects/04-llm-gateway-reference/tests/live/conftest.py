"""Fixtures for live tests that hit real upstream providers.

These tests are gated behind the `live` pytest marker and skipped by default
(see pyproject.toml addopts). They require `OPENAI_API_KEY` to be present in
`.env` or the process environment; a missing key short-circuits with a clear
skip message rather than failing.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]
ARTEFACT_DIR = REPO_ROOT / "docs" / "verification"


@pytest.fixture(scope="session", autouse=True)
def _require_live_key() -> None:
    """Skip the whole live test module if no real OpenAI key is available.

    We probe via a fresh ``Settings()`` so we honour whatever's in `.env` even
    when the user hasn't exported the variable into their shell.
    """
    probe = Settings()
    # Treat both "unset" and "set-but-empty" as missing — pydantic-settings
    # turns `OPENAI_API_KEY=""` into SecretStr(""), which would otherwise sneak
    # past a `None` check and crash inside the OpenAI SDK with a less helpful
    # message than this skip line.
    if probe.openai_api_key is None or not probe.openai_api_key.get_secret_value():
        pytest.skip(
            "OPENAI_API_KEY not set (or empty) in environment or .env; "
            "live tests require a real key.",
            allow_module_level=True,
        )


@pytest.fixture
def live_client() -> Iterator[TestClient]:
    """A TestClient backed by the real app, with caches cleared so the lifespan
    rebuilds the registry against the current environment (including .env)."""
    get_settings.cache_clear()
    client = TestClient(app)
    client.__enter__()
    try:
        yield client
    finally:
        client.__exit__(None, None, None)
        get_settings.cache_clear()


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

    We commit these to the repo as evidence the live path works. The payload
    is built strictly from the gateway's public response (no headers, no
    Authorization, no API key) plus the request body the test sent.
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
