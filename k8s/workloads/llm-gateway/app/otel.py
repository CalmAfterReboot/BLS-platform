"""OpenTelemetry bootstrap for the BLS LLM Gateway.

`otel_init()` configures traces + metrics + logs and auto-instruments
FastAPI, HTTPX, and Redis at the class level (so any subsequent
`FastAPI()` instance is instrumented without needing the app handle).

Call it BEFORE the FastAPI app is constructed in `app/main.py`.

Env vars (standard OTel SDK names, read at init time):
- `OTEL_EXPORTER_OTLP_ENDPOINT` — default `http://otel-collector.observability:4317` (gRPC).
- `OTEL_SERVICE_NAME` — default `bls-llm-gateway`.
- `OTEL_RESOURCE_ATTRIBUTES` — appended to the SDK Resource; standard OTel format.

The OTLP exporters speak gRPC over plaintext by default to the
in-cluster collector; the collector terminates and forwards to
Tempo (traces), Prometheus (metrics), and Loki (logs). The gateway
pod itself does not need TLS in-cluster — NetworkPolicy scopes the
hop to the observability namespace.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_DEFAULT_ENDPOINT = "http://otel-collector.observability:4317"
_DEFAULT_SERVICE_NAME = "bls-llm-gateway"
_initialised = False


def otel_init() -> None:
    """Configure traces, metrics, logs, and auto-instrumentation.

    Idempotent: calling twice is a no-op (guarded by module-level flag).
    Safe to call before or after FastAPI app instantiation thanks to the
    class-level instrumentor pattern, but call it BEFORE per the
    p6.2 sequence spec.
    """
    global _initialised
    if _initialised:
        return

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_ENDPOINT)
    service_name = os.environ.get("OTEL_SERVICE_NAME", _DEFAULT_SERVICE_NAME)

    resource = Resource.create(
        attributes={
            "service.name": service_name,
            "service.namespace": "llm-gateway",
            "service.version": os.environ.get("OTEL_SERVICE_VERSION", "0.4.0"),
            "deployment.environment": os.environ.get("OTEL_DEPLOYMENT_ENV", "production"),
        }
    )

    # Traces — BatchSpanProcessor (queue + periodic flush) over gRPC.
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # Metrics — PeriodicExportingMetricReader (default 60s interval).
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True)
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Logs — LoggerProvider wired into the stdlib logging via
    # LoggingHandler attached to the root logger.
    #
    # Deprecation note (OTel SDK 1.42): `LoggingHandler` from
    # opentelemetry.sdk._logs emits a DeprecationWarning pointing at a
    # handler in the separate `opentelemetry-instrumentation-logging`
    # package. We deliberately keep the SDK handler for now: the OTel
    # Python logs/log-export surface is still stabilising (the `_logs`
    # module is underscore-private), and the replacement package's API
    # is itself in flux. The current handler functions correctly and
    # the warning is informational, fired once at construction. Migrate
    # when the logs API graduates out of `_logs` — tracked as a Renovate
    # `otel needs-review` follow-up (see .github/renovate.json).
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(logger_provider)
    otel_log_handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    logging.getLogger().addHandler(otel_log_handler)

    # Auto-instrumentation — class-level patches; every FastAPI / HTTPX
    # client / Redis client constructed after this point is traced.
    FastAPIInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()

    _initialised = True
