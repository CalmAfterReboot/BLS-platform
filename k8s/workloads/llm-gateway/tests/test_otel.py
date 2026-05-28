"""Smoke-test: otel_init() degrades gracefully when the OTLP endpoint is unreachable.

This is a behaviour guard, not a functional test. The OTel SDK is
designed so that an unreachable collector causes BatchSpanProcessor
to log warnings and drop telemetry — never to raise. We test that the
gateway's `otel_init()` upholds that contract, so a misconfigured
endpoint can't crash the FastAPI bootstrap.

If this test ever fails, do not "fix" the test — fix the regression
in `otel.py` that introduced the new raise path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The gateway app uses a flat-namespace layout (no `app.` package
# prefix) because the production Dockerfile runs uvicorn from inside
# the app/ directory. Mirror that here.
APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def test_otel_init_does_not_raise_when_endpoint_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import otel  # local import is intentional — must follow the sys.path setup above

    # Reset the idempotency guard so this test exercises a full init,
    # regardless of any prior test having already initialised OTel.
    monkeypatch.setattr(otel, "_initialised", False)

    # Point the exporters at a TLD that cannot resolve. BatchSpanProcessor +
    # BatchLogRecordProcessor + PeriodicExportingMetricReader all swallow
    # connection failures and surface them as logged warnings — the SDK's
    # explicit graceful-degradation contract.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://nonexistent.invalid:4317")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "bls-llm-gateway-test")

    # Should return cleanly — no exception, no traceback, no exit.
    otel.otel_init()

    # Idempotency contract: a second call is a no-op.
    otel.otel_init()
