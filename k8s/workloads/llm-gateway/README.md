# Project 4 — LLM Gateway

**Status:** Done / BUILT (tag `v0.4.0-llm-gateway-live`)

> This is the canonical Helm chart for Project 4. ArgoCD reconciles it
> via the `bls-workloads` ApplicationSet (matrix generator) at the path
> `k8s/workloads/llm-gateway/`. A second working copy under
> `04-llm-gateway/` existed historically and was deleted in WU-3 — see
> the [Project history](#project-history) section if you came looking
> for it.

## Concept demonstrated

**API gateway pattern for backend abstraction.** One stable,
OpenAI-compatible endpoint sits in front of a model-routing layer
(LiteLLM) in front of multiple inference backends. Callers see a single
contract; provider selection, retries, caching, and authentication are
the gateway's concerns, not theirs. The same pattern applies to any
fan-out of provider APIs behind a unified interface — payment
processors, OAuth identity providers, message brokers — and is the
piece of this portfolio most directly transferable to product
engineering.

## Architecture

```
caller (Bearer token) ──▶ FastAPI proxy ──▶ LiteLLM router ──▶ backend
                          (port 8000)        (port 4000)        ├─ Ollama (homelab)
                                                                ├─ Azure OpenAI
                                                                └─ DeepSeek
```

| Layer | Component | Responsibility |
|---|---|---|
| Edge | FastAPI proxy (`app/`) | Bearer-token auth, request validation, forwards to LiteLLM. Has no model knowledge. |
| Routing | LiteLLM (proxy mode) | Provider selection, retries, response caching, normalises every backend to the OpenAI dialect. |
| Cache | Redis | Exact-match response cache for LiteLLM. Sized at 64Mi — present from day one so adding semantic caching later is configuration, not a topology change. |
| Backend (homelab) | Ollama on Proxmox host | Runs open models (llama3.2, mistral, deepseek-r1) natively, outside Kubernetes, to avoid container memory ceilings. Reached at `<homelab-ollama-host>:11434`. |
| Backend (cloud) | Azure OpenAI, DeepSeek API | Reached via LiteLLM provider drivers. |
| Observability | ServiceMonitor → kube-prometheus-stack | Scrapes `/metrics` on the FastAPI service every 30s. See P5 README (WU-6, coming in Week 3). |

Three separate Deployments, not one, because the lifecycles diverge:
the gateway image is rebuilt by CI on every `app/**` change, LiteLLM is
upgraded by changing one image tag, and Redis is a stable dependency
that should not restart when either of the other two does.

## Chart structure

```
k8s/workloads/llm-gateway/
├── Chart.yaml              # Helm metadata (name, version, appVersion)
├── values.yaml             # Default values (k3s homelab)
├── templates/              # Kubernetes manifests templated by Helm
│   ├── configmap-litellm.yaml      # LiteLLM model_list + router_settings
│   ├── deployment-gateway.yaml     # FastAPI proxy Deployment
│   ├── deployment-litellm.yaml     # LiteLLM Deployment (memory limit 2Gi — see "things to know")
│   ├── deployment-redis.yaml       # Redis Deployment
│   ├── service-{gateway,litellm,redis}.yaml  # ClusterIP services
│   ├── ingress.yaml                # Traefik ingress (k3s) — host `llm-gateway.local`
│   ├── secret.yaml                 # Bootstrap secret (placeholder values — WU-4 replaces this)
│   └── servicemonitor-gateway.yaml # Prometheus scrape target
└── app/                    # FastAPI source (built by .github/workflows/build-gateway.yaml)
    ├── Dockerfile
    ├── main.py             # FastAPI entrypoint, middleware wiring
    ├── middleware/auth.py  # API-key Bearer validation
    └── routers/completions.py  # /v1/chat/completions → LiteLLM
```

The `app/` directory living inside the Helm chart is deliberate: the
CI workflow at [`.github/workflows/build-gateway.yaml`](../../../.github/workflows/build-gateway.yaml)
triggers only when files under `k8s/workloads/llm-gateway/app/**`
change, so a `values.yaml` edit redeploys without rebuilding the image
and an `app/main.py` edit rebuilds the image without re-rendering
unchanged Kubernetes manifests.

## Render the chart locally

```bash
# k3s defaults (homelab)
helm template llm-gateway k8s/workloads/llm-gateway/ \
  -f k8s/workloads/llm-gateway/values.yaml --namespace llm-gateway
```

Lint and dry-run install:

```bash
helm lint k8s/workloads/llm-gateway/
helm install --dry-run llm-gateway k8s/workloads/llm-gateway/ \
  -f k8s/workloads/llm-gateway/values.yaml --namespace llm-gateway
```

## Deployment

The chart is GitOps-managed. ArgoCD's `bls-workloads` ApplicationSet
(matrix generator over `[in-cluster, bls-aks-demo] × [...workloads]`)
materialises the `llm-gateway-in-cluster` and `llm-gateway-bls-aks-demo`
Applications and reconciles them to their target clusters. See
[ADR-005 — ApplicationSet matrix pattern](../../../docs/adr/ADR-005-applicationset-matrix-pattern.md).

No `kubectl apply` is needed. The deployment chain is:

1. Push to `main`.
2. If `app/**` changed, GitHub Actions builds and pushes
   `ghcr.io/calmafterreboot/bls-llm-gateway:latest` + `:<sha>`.
3. ArgoCD detects the manifest or image-tag change and reconciles.
4. Kubernetes rolling-updates pods one at a time.

For first-time bring-up on a fresh cluster, the ApplicationSet must be
present first — the bootstrap path is documented in P2's
ArgoCD installation steps (see `02-k3s-platform/`).

## How to test it

After ArgoCD reports `Synced / Healthy`:

```bash
# 1. Pods up
kubectl get pods -n llm-gateway
#   Expect: llm-gateway-*, litellm-*, redis-* all 1/1 Running

# 2. Smoke test against the FastAPI proxy
kubectl port-forward -n llm-gateway svc/llm-gateway-service 8080:8000

# In another shell:
curl -s -X POST http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer <BLS_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local/llama3.2",
    "messages": [{"role": "user", "content": "Say hello in one sentence."}],
    "max_tokens": 64
  }' | jq .

# 3. LiteLLM liveness (unauthenticated — see "things to know" #2)
kubectl port-forward -n llm-gateway svc/litellm-service 4001:4000
curl http://localhost:4001/health/liveliness

# 4. Redis
kubectl exec -n llm-gateway \
  $(kubectl get pod -n llm-gateway -l app=redis -o jsonpath='{.items[0].metadata.name}') \
  -- redis-cli ping
#   Expect: PONG
```

A `401` from step 2 means the Bearer token is missing or wrong. A `504`
means LiteLLM exceeded its 130s client timeout — usually because Ollama
is loading a model from cold; retry.

## Live verification (opt-in)

An opt-in pytest suite under [`tests/live/`](tests/live/) exercises the
real OpenAI path **through the LiteLLM Python SDK** — the same library
the deployed LiteLLM proxy uses for its routing. It is not a smoke test
of the FastAPI proxy in `app/`; it is a verification that LiteLLM's
OpenAI integration and fallback behaviour work as expected against a
real upstream, with sanitised JSON evidence committed under
[`docs/verification/`](docs/verification/).

The suite is **gated behind the `live` pytest marker** and excluded by
default via `addopts = -m 'not live'` in
[`pyproject.toml`](pyproject.toml). It skips cleanly when
`OPENAI_API_KEY` is absent, so it never breaks CI.

```bash
cd k8s/workloads/llm-gateway
cp .env.example .env       # then paste your OpenAI key into .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

pytest -m live -v          # ~2 billable OpenAI calls, < $0.0001 per run
ls docs/verification/      # dated JSON evidence
```

Two scenarios are exercised:

| Scenario | Mechanism | Expected outcome |
|---|---|---|
| Happy path | `litellm.completion(model="openai/gpt-4o-mini", ...)` | Non-empty completion, `failover_occurred=false`, single attempt. |
| Forced failover | `litellm.Router` with bad primary `openai/does-not-exist-…` and `gpt-4o-mini` as the fallback | Router catches the OpenAI 404 (free, no tokens billed), serves the response from gpt-4o-mini, `failover_occurred=true`, two attempts. |

Each run writes a dated JSON artefact:

- `openai-live-happy-path-YYYY-MM-DD.json`
- `openai-live-forced-failover-YYYY-MM-DD.json`

The artefacts contain **no API key, no headers, no auth material** —
only the test inputs and a sanitised view of the gateway's response
envelope (`model_used`, `completion`, `attempts`, `failover_occurred`,
`latency_ms`, `finish_reason`). See [`SECURITY.md`](SECURITY.md) for the
secret-management posture, the `$10` prepay cap, the
`detect-secrets` baseline workflow, and the key-rotation playbook.

The suite is local-only and never run on CI; the deployed
`templates/configmap-litellm.yaml` does not currently include an OpenAI
provider entry, so the verification path does not touch the deployed
cluster. SDK-vs-proxy version drift is called out in `SECURITY.md`.

## Things to know (operational history)

These notes are not tutorial — they exist so the next operator does
not re-discover the same problems.

1. **LiteLLM memory was raised iteratively to 2Gi.** Started at 512Mi,
   OOMKilled three times under load before settling at 2Gi limit /
   512Mi request. The current value is empirically safe but has not
   been profiled under sustained representative traffic; right-size
   with `kubectl top pod -n llm-gateway` once load is real.

2. **LiteLLM probes use `/health/liveliness`, not `/health`.** With a
   master key configured, `/health` requires auth and unauthenticated
   Kubernetes probes get `401`. `/health/liveliness` is explicitly
   unauthenticated and is the right probe target. The master key was
   later removed entirely (see #3) but the probe choice still stands.

3. **`master_key` is removed from LiteLLM `general_settings`.** Setting
   `master_key` in LiteLLM activates database mode (it expects
   `DATABASE_URL` pointing at PostgreSQL for spend logs). That is the
   wrong architecture here — authentication happens at the FastAPI edge,
   LiteLLM is only reachable in-cluster, and there is no PostgreSQL.
   Removing the master key is architecturally correct, not a workaround.

4. **The bootstrap `secret.yaml` is a known gap.** Placeholder API keys
   are committed in plaintext because the Deployments reference Secret
   keys as env vars and need *something* to start. WU-4 replaces this
   with Sealed Secrets in Week 3 — do not propagate this pattern.

5. **Ollama listens on `0.0.0.0` on the Proxmox host.** Default Ollama
   binds to `127.0.0.1`, which makes it unreachable from the k3s
   cluster on the LAN. Override via `systemctl edit ollama` →
   `Environment="OLLAMA_HOST=0.0.0.0"` → `systemctl restart ollama`.

6. **The chart-duplication incident.** A second working copy of this
   chart lived at `04-llm-gateway/` from initial scaffolding through
   2026-05-16. ArgoCD only ever reconciled this path
   (`k8s/workloads/llm-gateway/`), so the duplicate was orphan code,
   not a second deployment. It was deleted under WU-3 after a values-
   aware `helm template` diff (captured in
   `scripts/wu-3/artefacts/chart-diff.txt`) and a four-point
   verification gate (`scripts/wu-3/artefacts/verify-after.txt`). The
   forensic note covering WU-2 (an unattributed Application CR
   deletion that preceded the chart cleanup) is in
   `PHASE-2-HANDOFF.md`.

## Key decisions (and ADR links)

| Decision | Rationale | Reference |
|---|---|---|
| LiteLLM in proxy mode, not SDK mode | Independent lifecycle; swap routing layer without touching FastAPI. | [ADR-008](../../../docs/adr/ADR-008-llm-gateway-design.md) *(stub — architect to complete)* |
| Auth at the FastAPI edge, not in LiteLLM | LiteLLM's auth model is spend-tracking with a DB dependency we don't need. Security boundary lives at the public layer. | ADR-008 |
| Ollama on Proxmox host, not in k3s | Models load multi-GB weights into RAM; container limits cause OOMKill. | ADR-008 |
| `routing_strategy: least-busy` (not round-robin) | Single-host Ollama serving multiple models — round-robin queues behind slow models even if others are idle. | ADR-008 |
| Mirrored chart deleted, canonical path retained | Only `k8s/workloads/llm-gateway/` is reconciled by ArgoCD. The duplicate added drift risk without adding capability. | [ADR-005](../../../docs/adr/ADR-005-applicationset-matrix-pattern.md), WU-3 |

## Observability

A `ServiceMonitor` is shipped with the chart
([`templates/servicemonitor-gateway.yaml`](templates/servicemonitor-gateway.yaml))
and picked up by the kube-prometheus-stack release (label selector
`release: kube-prometheus-stack`). It scrapes `/metrics` on the FastAPI
service every 30s. The dashboards and alert rules live with P5 — see
the P5 README under `05-observability-security/` once WU-6 lands in
Week 3.

## Known gaps (tracked work)

| Gap | Owner | Tracker |
|---|---|---|
| No TLS on ingress | Week 3 | (P5 cert-manager) |
| Image tag `:latest` instead of digest-pinned | Week 3+ | (ArgoCD Image Updater) |
| LiteLLM 2Gi memory limit not profiled under sustained load | When load is real | `kubectl top` after representative traffic |

### Closed gaps

| Gap | Resolution |
|---|---|
| Plaintext bootstrap `secret.yaml` → Sealed Secrets (WU-4) | Replaced with a `SealedSecret` sealed `--scope=strict` to namespace `llm-gateway`, name `llm-gateway-secrets`. Three keys are sealed: `litellm-master-key`, `bls-api-keys`, `ollama-endpoint`. The homelab sealed-secrets controller in the `sealed-secrets` namespace decrypts on apply. See [SECURITY.md](SECURITY.md#sealedsecret-workflow) for the re-sealing and rotation workflow. AKS cluster (when re-enabled) will need its own sealed manifest sealed against its own controller's public key. |
| Homelab Ollama IP literal in `values.yaml` | Removed `proxmox.ollamaEndpoint`. The endpoint now lives in the sealed `ollama-endpoint` key and is injected into the LiteLLM pod as the `OLLAMA_ENDPOINT` env var, referenced from `templates/configmap-litellm.yaml` via LiteLLM's `os.environ/OLLAMA_ENDPOINT` substitution syntax. No homelab-internal address is committed to git. |

## Project history

The full forensic build log — including the seven specific problems
hit during initial bring-up and the iterations that resolved them — is
recoverable from git history at commit `20b24a6` (the last commit that
predates the WU-3 deletion):

```bash
git show 20b24a6:04-llm-gateway/README.md
```

Keep that pointer in mind if you are tracing why a specific decision
was made. The forensic log is not duplicated here because that
documentation pattern (993 lines, ~80% historical narrative) is the
opposite of "useful to the next operator". This README captures the
load-bearing parts and lets git history hold the rest.
