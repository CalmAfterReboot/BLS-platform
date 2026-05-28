# ADR-013 — OpenTelemetry + LGTM Stack Adoption

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-28 |
| **Project** | BLS Project 6 — Platform Engineering (Stream B) |
| **Deciders** | BLS DevOps |

---

## Context

[ADR-006](ADR-006-observability-gitops.md) put `kube-prometheus-stack` on the cluster: Prometheus + Grafana + Alertmanager (the last disabled per [ADR-010](ADR-010-alertmanager-scope.md)). That landed metrics — and only metrics. The other two pillars of the three-signal model — distributed traces and structured logs — have been kubectl-port-forward-and-read-from-stderr until now.

For the LLM gateway specifically, "what is happening when a request is slow" is currently unanswerable without either a Wireshark-on-the-cluster session or a deliberate `kubectl logs --since=5m` correlation race between three pods (gateway → LiteLLM → Redis/Ollama). That's not viable as the platform grows toward Azure OpenAI, eval harnesses, and recurring cost analysis (Sequence 4).

Constraints:

- **No vendor lock-in.** The portfolio repo is public and the platform is bootstrap-budget; tying observability to Datadog / New Relic / Honeycomb pricing is out. Whatever fronts the gateway has to be runnable on the homelab and forkable by any reader.
- **Three signals must correlate.** A trace ID in a log line should be a one-click pivot to the trace; a span should pivot to the logs that ran during its window. Stitching this together by hand defeats the entire premise.
- **Storage budget is homelab-scale.** No S3, no Snowflake, no managed Elasticsearch. Filesystem-on-PVC has to be enough at portfolio scale, with a documented limit and a path off it.
- **The existing Prometheus stays the metrics sink.** Two metrics stores is two query languages, two dashboards, two retentions — none of that complexity earns its keep here.

This ADR records the decision to adopt **OpenTelemetry as the wire protocol** + **Loki / Tempo / (existing) Prometheus** as the three storage backends, with a single **otel-collector** fanning out.

---

## Options Considered

### Option A — ELK (Elasticsearch + Kibana + Filebeat) + Jaeger for traces

Two parallel stacks: ELK for logs, Jaeger for traces. Prometheus stays where it is. Custom integration between them.

**Rejected.** Two reasons:

1. **Operational complexity.** Elasticsearch needs a 3-node minimum for any HA story; on this cluster (5 nodes total, two of them workers) that single Application would dominate the worker resource budget. Filebeat → Logstash → ES → Kibana is four moving parts; each one has its own version compatibility matrix, JVM tuning, and shard math.
2. **Vendor-neutral wire format.** Filebeat speaks Beats protocol; Jaeger speaks Jaeger Thrift / Jaeger gRPC. The application has to know which pipe it's writing to — there is no single instrumentation library that produces *both* in their native formats. Swapping ELK for any other log store in the future would be a code-side change in every service.

### Option B — OpenTelemetry + LGTM stack (Loki / Grafana / Tempo / Mimir) — partial *(rejected variant)*

The full LGTM stack uses Mimir instead of Prometheus for the metrics tier. Mimir is a horizontally-scalable Prometheus-compatible store designed for multi-tenant deployments.

**Rejected.** [ADR-006](ADR-006-observability-gitops.md) already settled on Prometheus + kube-prometheus-stack; Mimir would mean migrating that, and the win is zero at this scale (single tenant, sub-GB of metrics per day). Mimir earns its keep at the 100 GiB-of-metrics-per-day inflection point — far above where we sit.

### Option C — OpenTelemetry + Loki + Tempo + existing Prometheus *(selected)*

The OpenTelemetry SDK is the only thing the application code knows. Traces, logs, and metrics all leave the process as OTLP. An in-cluster `otel-collector` (contrib distribution, DaemonSet, one per node) is the single egress point: receives OTLP on `:4317` / `:4318`, runs tail-based sampling on the traces, and fans out to:

- **Tempo** for traces (via OTLP/gRPC).
- **Loki** for logs (via OTLP/HTTP — Loki 3.x speaks native OTLP at `/otlp`).
- **kube-prometheus-stack Prometheus** for metrics (via `prometheusremotewrite` exporter; Prometheus must enable the `enableRemoteWriteReceiver` flag, which this PR does).

Grafana — already deployed by kube-prometheus-stack — is the single UI. Datasource provisioning for Loki and Tempo is auto-discovered via the Grafana sidecar's `grafana_datasource: "1"` label convention. The trace → log and trace → metrics pivots are wired via `tracesToLogsV2` / `tracesToMetrics` jsonData on the Tempo datasource.

### Option D — Cloud-hosted observability (Datadog / Grafana Cloud / Honeycomb)

Stop running observability infrastructure entirely. The application emits OTLP to a hosted endpoint.

**Rejected at this stage** for the bootstrap-budget reason. Free tiers exist but they all eventually meter retention or cardinality. Honourable mention: Grafana Cloud's free tier (50 GB logs, 50 GB traces, 14d retention) is genuinely useful if the homelab is ever decommissioned; the OTel wire format chosen here means *switching to it is a one-line endpoint change in `values.yaml`* and no code touches. That's the point — Option D is reachable from Option C without rewrites; the reverse is not true.

---

## Decision

**Adopt OpenTelemetry as the single instrumentation interface; deploy Loki + Tempo as new ArgoCD Applications; route everything through an `otel-collector-contrib` DaemonSet with tail-based sampling. Existing Prometheus stays the metrics sink via remote-write.**

Application code calls `otel_init()` (one function, in `app/otel.py`) once at startup; the SDK does the rest. No vendor-specific logging library, no Jaeger client, no `prom_client` parallel to the FastAPI instrumentator. The OTel `Resource` carries service identity (`service.name`, `service.namespace`, `service.version`); the OTel `BatchSpanProcessor` queues; the OTel exporters speak OTLP/gRPC to a localhost-resolved collector pod on the same node.

---

## Rationale

### Why OpenTelemetry as the wire

- **Single SDK, three signals.** `opentelemetry-sdk` covers traces + metrics + logs with a unified `Resource` model. Instrumentation libraries (`opentelemetry-instrumentation-fastapi`, `-httpx`, `-redis`) auto-emit consistent attributes; we don't write per-library shims.
- **Vendor-neutral.** The collector is the boundary — swapping Tempo for Jaeger, Loki for Elastic, Prometheus for Mimir is a config change in `k8s/workloads/otel-collector/values.yaml`. The gateway code never knows.
- **Pre-existing FastAPI Prometheus middleware survives.** The existing `prometheus_fastapi_instrumentator` keeps emitting `/metrics` for kube-prometheus-stack to scrape directly; OTel adds a second metrics path (via OTLP → remote-write) for things like LiteLLM's GenAI-aligned histograms that we don't want to plumb through `/metrics`. Two backends, one Prometheus, no daylight.

### Why tail-based sampling, not head-based

The collector receives every span but only forwards a subset. The `tail_sampling` processor evaluates each *complete trace* against a policy chain — full traces, not individual spans — and decides at the end whether to keep or drop. Configured policies (in priority order):

1. **`status_code: ERROR`** — keep 100% of traces that contain at least one ERROR-status span.
2. **`latency > 2000 ms`** — keep 100% of traces whose root span exceeds 2 seconds.
3. **`probabilistic 10%`** — keep 10% of the remainder, drop the other 90%.

This is the inverse of head-based sampling (where the decision is made before the trace is complete): head-based has to choose blind and almost always over-samples healthy traffic while under-sampling the rare slow / failing traces that matter. Tail-based gets the sampling rate down to ~10% storage cost while preserving 100% of investigative-value traces.

Trade-off documented: tail-sampling needs `decision_wait: 10s` of buffer per trace, costing memory on the collector. The contrib chart's default ceiling is generous; we cap at 1 GiB.

### Why LGTM over ELK

- **Single Grafana UI.** Three datasources, one query interface, one auth boundary. Kibana would be a second UI with its own auth, its own dashboards-as-JSON dialect, its own user management.
- **No JVM in the data plane.** Loki, Tempo, and Prometheus are all Go binaries; their memory is bounded and predictable. Elasticsearch + Logstash bring a JVM heap-tuning lifecycle that has no place on a 16 GiB worker node.
- **Trace ⇄ log pivot is free.** Grafana renders both natively; the Tempo datasource's `tracesToLogsV2` block (and the Loki datasource's `derivedFields` regex for `trace_id=…`) makes the pivot a single click in either direction.

### Storage trade-offs

| Backend | Storage | Retention | Failure mode |
|---|---|---|---|
| Tempo | `local` filesystem, 10 GiB PVC | 72 h | Single-node, PVC-bound; lose the PV → lose all traces. Acceptable: traces are short-half-life investigative artefacts, not compliance evidence. |
| Loki | `filesystem` chunks, 10 GiB PVC | 14 d (336 h) | Same. Logs are queryable evidence for the operational window; old enough logs are by design unavailable. |
| Prometheus (existing) | KPS chart-managed, 5 GiB retention | 7 d | Already covered by ADR-006. |

All three are PVC-backed on the k3s cluster's default storage class (Longhorn per CLAUDE.md). The portfolio-scope deferral is the **scale-out path**: when ingest exceeds single-node capacity, both Loki and Tempo have multi-component "distributed" Helm charts that swap filesystem for S3-compatible object storage. The OTel wire stays the same; only the Application manifest swaps in.

---

## Consequences

- **`otel-collector` is now a critical-path dependency.** If the DaemonSet is down on a node, OTLP exports from pods on that node retry locally (the BatchSpanProcessor queues for up to 5,000 spans before dropping); the gateway itself does not block on OTel writes. Documented in [docs/runbooks/otel-collector-down.md] (planned follow-up).
- **The gateway image grows by ~30–40 MiB.** OpenTelemetry's gRPC + protobuf transitive deps account for most of this. Acceptable.
- **`redis-py` is now a gateway dep** even though the FastAPI edge layer does not use a Redis client (the instrumentor's `import redis` at module-load forces this). Documented in `app/requirements.txt`. Future direct-Redis-client work would activate the instrumentation; today it sits dormant.
- **LiteLLM gains the `otel` callback.** Per-request spans + GenAI-semconv-aligned attributes (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, etc.) flow through the same collector. See [ADR-014](ADR-014-genai-semconv-adoption.md).
- **Kube-prometheus-stack opens the remote-write receiver.** `enableRemoteWriteReceiver: true` on `prometheus.prometheusSpec`. Scoped by NetworkPolicy ([ADR-009](ADR-009-networkpolicy-scope.md)) — only the otel-collector namespace can hit it.
- **Two ArgoCD Applications added** (`loki`, `tempo`) + one (`otel-collector`) under standalone management. The matrix ApplicationSet at `k8s/apps/app-of-apps.yaml` is updated to exclude `k8s/workloads/otel-collector/` (the standalone Application owns it) and `k8s/workloads/argocd-config/` (the strategic-merge patches are not standalone resources).

---

## Review trigger

Revisit if any of the following becomes true:

1. **Single-node storage ceilings are reached.** Loki's `filesystem` mode crashes on disk pressure; Tempo silently drops traces. The recovery path is the distributed Helm charts + an S3-compatible backend (minio in-cluster, R2 via Cloudflare R2 free tier, or Azure Blob).
2. **A managed observability tier is funded.** Grafana Cloud free tier alone is enough to take Loki + Tempo off-cluster; the OTel collector's exporters re-target with no application-code change.
3. **Compliance retention requirements exceed 14 d on logs.** The current ceiling is operational, not regulatory. A regulator's "logs for N months" would force either off-cluster archive (S3 + lifecycle) or a parallel ELK-style stack purely for that purpose.
4. **The metrics-via-remote-write path proves duplicative with the existing `/metrics` scrape.** If LiteLLM's GenAI histograms end up on both sides of Prometheus (scraped + remote-written), drop the scrape side and let OTel carry the load.
