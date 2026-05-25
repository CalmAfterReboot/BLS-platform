# Project 5 — Observability + Security

**Blue Layer Systems DevOps Portfolio · Project 5 of 6**

P5 is the observability and security layer of the platform. It ships
pull-based metrics across the cluster (kube-prometheus-stack), encrypted
secrets at rest in Git (Bitnami Sealed Secrets), and namespace-scoped
network isolation (NetworkPolicy on `llm-gateway`). All three landed via
GitOps — every manifest is reconciled from `main` by ArgoCD; nothing is
applied by hand.

This document is the landing page for the P5 surface. The technical depth
lives in the linked ADRs, the runbook, and the per-namespace manifests
that are kept with the resources they configure.

---

## Table of contents

1. [Concept demonstrated](#concept-demonstrated)
2. [Architecture](#architecture)
3. [Directory map](#directory-map)
4. [Prerequisites](#prerequisites)
5. [Phase 1 — Sealed Secrets controller](#phase-1--sealed-secrets-controller)
6. [Phase 2 — kube-prometheus-stack via multi-source ArgoCD Application](#phase-2--kube-prometheus-stack-via-multi-source-argocd-application)
7. [Phase 3 — Cross-namespace ServiceMonitor for the LLM gateway](#phase-3--cross-namespace-servicemonitor-for-the-llm-gateway)
8. [Phase 4 — NetworkPolicy baseline on `llm-gateway`](#phase-4--networkpolicy-baseline-on-llm-gateway)
9. [Phase 5 — Workload `PrometheusRule` for the LLM gateway](#phase-5--workload-prometheusrule-for-the-llm-gateway)
10. [Things to know (operational history)](#things-to-know-operational-history)
11. [Key decisions (and ADR links)](#key-decisions-and-adr-links)
12. [Observability of the observability](#observability-of-the-observability)
13. [Known gaps (tracked work)](#known-gaps-tracked-work)
14. [Verification](#verification)
15. [Project history](#project-history)

---

## Concept demonstrated

Pull-based metrics with label-based aggregation, plus encrypted secrets
in Git decrypted only inside the cluster, plus a namespace-scoped
network isolation baseline on the workload that handles authenticated
requests. Three concepts; three tools; one set of architectural
decisions recorded under [`docs/adr/`](../docs/adr/).

| Concept | Tool | Decision record |
|---|---|---|
| Pull-based metrics + label aggregation | Prometheus (via kube-prometheus-stack) | [ADR-006](../docs/adr/ADR-006-observability-gitops.md) |
| Encrypted secrets at rest in Git | Bitnami Sealed Secrets | [runbook](../docs/runbooks/sealed-secrets-controller.md) |
| Workload network isolation | Kubernetes NetworkPolicy + k3s kube-router enforcement | [ADR-009](../docs/adr/ADR-009-networkpolicy-scope.md) |
| Independent chart-version + values lifecycle | ArgoCD multi-source `Application` | [ADR-006](../docs/adr/ADR-006-observability-gitops.md) |

Concept-to-tool details (the platform-wide table) live at
[`docs/plan-v4/concept-tool-mapping.md`](../docs/plan-v4/concept-tool-mapping.md).

---

## Architecture

**Diagram:**
[`docs/diagrams/06-observability-data-flow.png`](../docs/diagrams/06-observability-data-flow.png)
([source](../docs/diagrams/06-observability-data-flow.py)).

A three-column data-flow view: nine ServiceMonitor scrape sources on the
left feed Prometheus in the centre; Grafana, the (currently-disabled)
AlertManager, and the human operator via `kubectl port-forward` read on
the right; the prometheus-operator manages the ServiceMonitor and
PrometheusRule CRDs that configure the centre column.

```
                           ┌─────────────────────────────────┐
 8× ServiceMonitors        │     monitoring namespace        │      Consumers
 in monitoring ns ───────► │                                 │      ─────────
                           │   Prometheus (StatefulSet)      │ ───► Grafana
                           │   prometheus-operator           │       (PromQL queries
 1× ServiceMonitor         │   ServiceMonitor / Prom Rule    │        + self-scrape)
 in llm-gateway ns ──────► │     CRDs (declarative config)   │
 (crosses NetworkPolicy    │                                 │ ╌╌►  AlertManager
  boundary; admitted by    │                                 │       (DISABLED today —
  gateway-policy ADR-009)  │                                 │        PR-E re-enable)
                           └─────────────────────────────────┘
                                          ▲
                                          │ kubectl port-forward
                                          │ (apiserver-mediated;
                                          │  bypasses NetworkPolicy)
                                       Operator
```

**Where each artefact lives in the repo** (P5 is intentionally spread —
manifests stay with the resource they configure, decisions live under
`docs/adr/`):

| Artefact | Path |
|---|---|
| kube-prometheus-stack values | [`05-observability-security/values/kube-prometheus-stack.yaml`](values/kube-prometheus-stack.yaml) |
| kube-prometheus-stack `Application` | [`k8s/apps/monitoring.yaml`](../k8s/apps/monitoring.yaml) |
| Sealed Secrets controller `Application` | [`k8s/apps/sealed-secrets.yaml`](../k8s/apps/sealed-secrets.yaml) |
| Grafana admin sealed credentials | [`k8s/workloads/monitoring/grafana-admin-secret.yaml`](../k8s/workloads/monitoring/grafana-admin-secret.yaml) |
| LLM gateway `ServiceMonitor` | [`k8s/workloads/llm-gateway/templates/servicemonitor-gateway.yaml`](../k8s/workloads/llm-gateway/templates/servicemonitor-gateway.yaml) |
| LLM gateway NetworkPolicy template | [`k8s/workloads/llm-gateway/templates/networkpolicies.yaml`](../k8s/workloads/llm-gateway/templates/networkpolicies.yaml) |
| ADR — observability GitOps deployment | [`docs/adr/ADR-006-observability-gitops.md`](../docs/adr/ADR-006-observability-gitops.md) |
| ADR — NetworkPolicy scope | [`docs/adr/ADR-009-networkpolicy-scope.md`](../docs/adr/ADR-009-networkpolicy-scope.md) |
| Sealed Secrets runbook | [`docs/runbooks/sealed-secrets-controller.md`](../docs/runbooks/sealed-secrets-controller.md) |
| Observability data-flow diagram | [`docs/diagrams/06-observability-data-flow.py`](../docs/diagrams/06-observability-data-flow.py) |

---

## Directory map

```
05-observability-security/
├── README.md                      # This document
└── values/
    └── kube-prometheus-stack.yaml # Helm values, referenced by k8s/apps/monitoring.yaml
                                   # via ArgoCD multi-source $values overlay
```

The directory deliberately holds only the values overlay. Everything
else lives where it is used (Applications under `k8s/apps/`, workload
manifests under `k8s/workloads/<chart>/templates/`, decisions under
`docs/adr/`). See the [Architecture](#architecture) section for the full
map.

---

## Prerequisites

### Tooling

```bash
kubectl version --client       # >= 1.30
helm version --short           # >= 3.12 (chart values rendering only — ArgoCD does the apply)
kubeseal --version             # 0.36.x; the controller image in k8s/apps/sealed-secrets.yaml pins to 2.18.5
argocd version --client        # >= 2.6 (multi-source Application support is hard-required by ADR-006)
```

### Access to a running cluster with ArgoCD

P5 assumes the platform from P2 (`02-k3s-platform`) and P3
(`03-aks-multicluster`) is already running: a k3s HA cluster on Proxmox
with ArgoCD installed in-cluster and the matrix ApplicationSet at
[`k8s/apps/app-of-apps.yaml`](../k8s/apps/app-of-apps.yaml) discovering
workloads under `k8s/workloads/`.

P5 itself ships nothing as a workload under the ApplicationSet — both
the kube-prometheus-stack and the Sealed Secrets controller are
**standalone `Application` resources** rather than ApplicationSet
children, for the architectural reasons recorded in ADR-006. See
[Phase 2](#phase-2--kube-prometheus-stack-via-multi-source-argocd-application).

### Verify NetworkPolicy enforcement before relying on it

NetworkPolicy CRDs are accepted by any Kubernetes API; whether they are
**enforced** depends on the cluster's network controller. k3s ships
kube-router by default for this; other clusters may need a deliberate
choice (Calico, Cilium, Antrea, etc.). The cluster's enforcement state
is verifiable empirically in under a minute — see [Verification](#verification).

---

## Phase 1 — Sealed Secrets controller

The controller lives in its own namespace (`sealed-secrets`, **not**
`kube-system`) so that the master key's reconciliation lifecycle is
visible and ArgoCD-managed. The deployment is one standalone
`Application` pointing at the upstream Bitnami Helm chart.

### Apply the Application

```bash
kubectl apply -f k8s/apps/sealed-secrets.yaml
```

ArgoCD reconciles the controller from
[`k8s/apps/sealed-secrets.yaml`](../k8s/apps/sealed-secrets.yaml):

| Field | Value |
|---|---|
| Source repo | `https://bitnami-labs.github.io/sealed-secrets` (upstream chart) |
| Chart version | `2.18.5` (pinned in the `Application` spec) |
| Namespace | `sealed-secrets` |
| Sync policy | `automated.prune=true, selfHeal=true, CreateNamespace=true` |
| Release name | `sealed-secrets` (overridden via `fullnameOverride`) |

### Seal a Secret against this controller

`kubeseal` defaults assume the controller is at
`kube-system/sealed-secrets-controller`. **This deployment is
different.** Always pass:

```bash
kubeseal \
  --controller-namespace sealed-secrets \
  --controller-name sealed-secrets \
  --scope strict \
  -o yaml < plaintext-secret.yaml > sealed-secret.yaml
```

`--scope strict` binds the SealedSecret to its exact namespace and
exact `metadata.name`. Renaming or moving the SealedSecret invalidates
it.

### Back up the master key — and verify the off-workstation copy

The master key is the highest-blast-radius secret on the cluster. The
full backup procedure (including the wider label selector that catches
both the active key and rotated-out keys, the off-workstation transfer,
the `shred -u` caveats, and the controller-restart test) is in the
runbook:

→ [`docs/runbooks/sealed-secrets-controller.md`](../docs/runbooks/sealed-secrets-controller.md)

The runbook also names the known test-coverage gap: the
**controller-restart test** has been run and passes; the **full
restore-from-backup test** against a fresh `sealed-secrets` namespace
has not been routinely executed and is scheduled for the next planned
cluster rebuild.

---

## Phase 2 — kube-prometheus-stack via multi-source ArgoCD Application

### Why standalone, not the ApplicationSet

The matrix ApplicationSet at
[`k8s/apps/app-of-apps.yaml`](../k8s/apps/app-of-apps.yaml) was designed
for workloads with a uniform deployment model — local Helm charts under
`k8s/workloads/`, same sync policy, one-Application-per-(cluster,
workload). kube-prometheus-stack is an **upstream** chart published at
`prometheus-community.github.io/helm-charts`. Restructuring the
ApplicationSet template to handle upstream charts would change the
contract for every workload it deploys. Standalone Application is the
correct abstraction boundary.

The full rationale, including the rejected umbrella-chart and
inline-`valuesObject` alternatives, is in
[ADR-006](../docs/adr/ADR-006-observability-gitops.md).

### How multi-source separates chart from values

```yaml
# k8s/apps/monitoring.yaml — abridged
sources:
  - repoURL: https://prometheus-community.github.io/helm-charts
    chart: kube-prometheus-stack
    targetRevision: "84.5.0"          # pinned chart version
    helm:
      valueFiles:
        - $values/05-observability-security/values/kube-prometheus-stack.yaml
  - repoURL: https://github.com/CalmAfterReboot/BLS-platform
    targetRevision: HEAD
    ref: values                       # this Git repo provides the values file
```

- Bumping the chart is a one-line diff in `monitoring.yaml`
- Changing values is a one-file diff at
  `05-observability-security/values/kube-prometheus-stack.yaml`
- Both changes are independently reviewable
- No binary `charts/` tarball ever lands in Git

### Apply the Application

```bash
kubectl apply -f k8s/apps/monitoring.yaml
```

ArgoCD reconciles the upstream chart against the values file. Sync
policy uses `ServerSideApply=true` because kube-prometheus-stack CRD
annotations exceed the 262144-byte client-side-apply limit — without
it, the first install fails with an annotation size error.

### Notable values choices (full file at `values/kube-prometheus-stack.yaml`)

- `serviceMonitorSelector: {}` + `serviceMonitorNamespaceSelector: {}`
  → Prometheus watches ServiceMonitors **across all namespaces**.
  Without this, the LLM gateway's ServiceMonitor in `llm-gateway`
  would be invisible to Prometheus in `monitoring`.
- `kubeScheduler.enabled: false`, `kubeControllerManager.enabled:
  false`, `kubeEtcd.enabled: false`, `kubeProxy.enabled: false` — k3s
  embeds these into the server binary and does not expose them on the
  standard endpoints the chart attempts to scrape. Leaving them
  enabled would produce persistent `ScrapeError` targets in the
  Prometheus UI.
- `alertmanager.enabled: false` — the chart's Alertmanager is
  **disabled in this deployment by deliberate decision** recorded in
  [ADR-010](../docs/adr/ADR-010-alertmanager-scope.md). Workload
  `PrometheusRule` resources ship (see Phase 5) and fire to the
  Prometheus UI's `/alerts` endpoint only; no external paging. Re-enable
  is one values change away if a real on-call audience appears.
- `grafana.admin.existingSecret: grafana-admin-credentials` — the
  Grafana admin password lives in
  [`k8s/workloads/monitoring/grafana-admin-secret.yaml`](../k8s/workloads/monitoring/grafana-admin-secret.yaml)
  as a SealedSecret, not in the chart's default
  `kube-prometheus-stack-grafana` secret.
- `retention: 7d`, `retentionSize: "5GB"` — homelab profile. Increase
  if portfolio workloads grow.

---

## Phase 3 — Cross-namespace ServiceMonitor for the LLM gateway

The LLM gateway exposes `/metrics` on port `8000` (named `http` on the
Service). Its ServiceMonitor lives **with the chart** in
[`k8s/workloads/llm-gateway/templates/servicemonitor-gateway.yaml`](../k8s/workloads/llm-gateway/templates/servicemonitor-gateway.yaml)
rather than under `05-observability-security/` — the resource and the
workload it scrapes share a lifecycle.

For Prometheus in `monitoring` to discover a ServiceMonitor in
`llm-gateway`, two conditions must hold:

1. The empty selectors in `monitoring`'s Prometheus spec
   (`serviceMonitorSelector: {}` + `serviceMonitorNamespaceSelector: {}`,
   set in Phase 2's values file).
2. The ServiceMonitor must carry the label
   `release: kube-prometheus-stack` so the prometheus-operator picks it
   up — this label is set in
   [`servicemonitor-gateway.yaml:8`](../k8s/workloads/llm-gateway/templates/servicemonitor-gateway.yaml).

When PR #18 (NetworkPolicy baseline — see Phase 4) lands, this
cross-namespace scrape edge crosses the `llm-gateway`
namespace's `default-deny` baseline; it is admitted by the
`gateway-policy` ingress rule that allows from the `monitoring`
namespace's Prometheus pod on port `8000`.

---

## Phase 4 — NetworkPolicy baseline on `llm-gateway`

### Why `llm-gateway` is in scope and other namespaces are not

The decision and its rationale are recorded in full in
[ADR-009](../docs/adr/ADR-009-networkpolicy-scope.md). Summarised:

- **`llm-gateway` is in scope.** Authenticated inbound request path;
  master-key-protected upstream credentials; external egress to
  multiple LLM providers. Defence-in-depth requires at least one
  barrier between in-cluster pods and the gateway's network ingress.
- **`monitoring` is deferred.** Prometheus's egress surface is
  unbounded under `serviceMonitorSelector: {}`. A tight egress policy
  is fundamentally at odds with the discovery model — every new
  ServiceMonitor would silently fail to scrape until the policy is
  widened. Cost of getting it right is high; threat model does not
  justify it (no inbound user request path into `monitoring`).
- **`sealed-secrets` is deferred.** Single-pod cluster-scoped
  controller. The high-blast-radius secret it holds is at rest in
  etcd, not in transit — NetworkPolicy does not protect it. The threat
  model that does matter is RBAC-bounded, not network-bounded.

### The policy set (4 resources)

Templated under
[`k8s/workloads/llm-gateway/templates/networkpolicies.yaml`](../k8s/workloads/llm-gateway/templates/networkpolicies.yaml),
gated by `.Values.networkPolicies.enabled` (default `true`):

| Policy | Selects | Allows |
|---|---|---|
| `default-deny-all` | every pod in `llm-gateway` | nothing (baseline deny — belt-and-braces) |
| `gateway-policy` | `app: llm-gateway` | ingress: Prometheus :8000; egress: LiteLLM :4000, CoreDNS :53 |
| `litellm-policy` | `app: litellm` | ingress: gateway :4000; egress: Redis :6379, CoreDNS :53, external (non-cluster IPs) on :11434 (Ollama) + :443 (cloud LLM APIs) |
| `redis-policy` | `app: redis` | ingress: LiteLLM :6379; egress: CoreDNS :53 |

External egress is an `ipBlock 0.0.0.0/0` with the k3s pod and service
CIDRs in `except` — the only sound way to allow external-only egress
when destinations are cloud-hostname-based and unstable as IPs.
Cluster CIDRs are parameterised via
`.Values.networkPolicies.podCIDR` / `.serviceCIDR` for AKS portability.

### Opt-out for clusters without enforcement

```yaml
# Override in an ApplicationSet values overlay for clusters where
# NetworkPolicy enforcement is not active.
networkPolicies:
  enabled: false
```

When disabled the chart renders zero NetworkPolicy resources. The chart
**does not** ship policies that look enforcing but aren't.

---

## Phase 5 — Workload `PrometheusRule` for the LLM gateway

Three workload-specific rules ship with the chart at
[`k8s/workloads/llm-gateway/templates/prometheusrules.yaml`](../k8s/workloads/llm-gateway/templates/prometheusrules.yaml),
gated by `.Values.prometheusRules.enabled` (default `true`):

| Rule | Expression (summary) | For | Severity |
|---|---|---|---|
| `LLMGatewayDown` | `up{namespace="llm-gateway", service="llm-gateway-service"} == 0` | 5m | critical |
| `LLMGatewayHighErrorRate` | 5xx-ratio over total > 5% | 10m | warning |
| `LLMGatewayHighLatency` | p99 latency on non-LLM endpoints > 1s | 10m | warning |

Notes:

- **Status labels are bucketed** (`"2xx"`, `"5xx"`) by the
  `prometheus-fastapi-instrumentator` 7.1.0 default mapping — the
  error-rate rule filters on `status="5xx"` not on raw HTTP codes like
  `status="500"`.
- **The latency rule excludes `/v1/chat/completions`** via
  `handler!="/v1/chat/completions"`. LLM inference is legitimately slow
  (multi-second generations are normal); a slow fast-path
  (`/healthz`, `/metrics`) signals event-loop contention, GC pressure,
  or container resource starvation — the real diagnostic signal.
- **Rules fire to the Prometheus UI only.** Alertmanager stays
  disabled per [ADR-010](../docs/adr/ADR-010-alertmanager-scope.md).
  This is the deliberate scope statement, not an oversight.

### Why the rules ship anyway if no one pages on them

Workload rules carry diagnostic value even without external routing.
The PromQL expressions themselves are portfolio evidence that the
architect understands the metric model (which metrics
`prometheus-fastapi-instrumentator` exposes, which labels are stable,
which handler to exclude and why). A reviewer reading
`prometheusrules.yaml` sees what the architect believes the
load-bearing failure modes are. The Prometheus UI's `/alerts` view
becomes the authoritative "what's wrong right now" surface for the
operator on the workstation. See
[ADR-010 Rationale](../docs/adr/ADR-010-alertmanager-scope.md#rationale)
for the full reasoning.

### Re-enable path (if an audience appears)

1. `alertmanager.enabled: false → true` in
   [`values/kube-prometheus-stack.yaml`](values/kube-prometheus-stack.yaml).
2. Add a `receivers:` block under `alertmanager.config` and a
   `route:` block matching the desired severity labels.
3. ArgoCD sync.

The rules themselves do not change. ADR-010 documents the trigger
conditions under which a future ADR should supersede this one.

---

## Things to know (operational history)

These notes exist so the next operator does not re-discover the same
problems. Each entry is a real gotcha encountered during P5 bring-up.

1. **The Sealed-Secrets controller is NOT in `kube-system`.** The
   default `kubeseal` invocation
   (`--controller-namespace kube-system --controller-name
   sealed-secrets-controller`) **silently fails** against this
   deployment — it cannot find the controller, falls back to fetching
   the public cert from a separate path, and you only notice when the
   sealed manifest fails to decrypt on apply. Always pass
   `--controller-namespace sealed-secrets --controller-name
   sealed-secrets` explicitly. The same applies to operator commands
   like `kubectl logs deployment/sealed-secrets`.

2. **`serviceMonitorSelector: {}` is non-obvious and load-bearing.**
   The chart's default Prometheus spec scopes its ServiceMonitor watch
   to `release: kube-prometheus-stack` via Helm-generated defaults.
   Without `serviceMonitorSelectorNilUsesHelmValues: false` AND empty
   `{}` selectors, ServiceMonitors in other namespaces (like the LLM
   gateway's) are invisible — they exist as resources but are never
   scraped. Failure mode is silent: target list looks complete,
   missing targets simply don't appear. See
   [`values/kube-prometheus-stack.yaml`](values/kube-prometheus-stack.yaml).

3. **`ServerSideApply=true` is mandatory.** kube-prometheus-stack CRDs
   (Prometheus, Alertmanager, PrometheusRule, ServiceMonitor, etc.)
   carry annotations larger than the 262144-byte limit
   `kubectl apply` enforces in client-side mode. Without
   `ServerSideApply=true` in the Application's `syncOptions`, the
   first sync fails with `metadata.annotations: Too long: must have at
   most 262144 bytes`. This is true on every chart upgrade, not just
   the first install — keep the flag.

4. **k3s disables several control-plane scrapes by intent.** k3s
   embeds `kube-scheduler`, `kube-controller-manager`, `etcd`, and
   `kube-proxy` into the server binary; they don't expose the standard
   endpoints the chart tries to scrape. Leaving the chart's defaults
   produces persistent `ScrapeError` targets in the Prometheus UI and
   fires `KubeControllerManagerDown`-style alerts the moment
   AlertManager is enabled. The values file explicitly disables them
   under `kubeScheduler.enabled: false`, `kubeControllerManager.
   enabled: false`, `kubeEtcd.enabled: false`, `kubeProxy.enabled:
   false`. Also `defaultRules.rules.etcd: false`,
   `kubeSchedulerAlerting: false`, `kubeSchedulerRecording: false`
   to suppress the associated rule files.

5. **Grafana admin password lives in a separate sealed Secret, not
   the chart default.** The chart's default secret name is
   `kube-prometheus-stack-grafana`. This deployment overrides
   `grafana.admin.existingSecret: grafana-admin-credentials` and seals
   a separate secret at
   [`k8s/workloads/monitoring/grafana-admin-secret.yaml`](../k8s/workloads/monitoring/grafana-admin-secret.yaml).
   The retrieval command for the unsealed plaintext lives in the
   operator-private handbook (gitignored — never committed). When the
   chart bumps and `helm template` diffs reveal a change to the secret
   name, this override needs to be re-verified.

6. **NetworkPolicy enforcement is silent when absent.** Applying a
   NetworkPolicy resource on a cluster without a policy controller
   (stock Flannel without kube-router, for example) succeeds at the
   API layer — the resource exists, `kubectl get netpol` lists it — but
   no traffic is rejected. The failure mode is therefore "policy looks
   enforced, isn't". The empirical deny-all test in
   [Verification](#verification) catches this in under a minute and
   should be run **before** relying on any NetworkPolicy for security
   on a cluster whose CNI you did not configure yourself. On this
   cluster: kube-router is bundled by default with k3s and enforcement
   is confirmed active.

---

## Key decisions (and ADR links)

| Decision | Rationale | Reference |
|---|---|---|
| Standalone `Application` for kube-prometheus-stack (not the matrix ApplicationSet) | ApplicationSet template targets local Helm charts under `k8s/workloads/`; upstream charts incompatible without restructuring the template for every workload. Observability is infrastructure, not a workload. | [ADR-006](../docs/adr/ADR-006-observability-gitops.md) |
| Multi-source `Application` (chart + values from separate repos) | Independent reviewability of chart version vs values; no binary `charts/` tarball in Git; chart bump is a one-line diff. | [ADR-006](../docs/adr/ADR-006-observability-gitops.md) |
| `ServerSideApply=true` in sync options | kube-prometheus-stack CRD annotations exceed the 262144-byte client-side-apply limit; without this, every CRD update fails. | [ADR-006](../docs/adr/ADR-006-observability-gitops.md) |
| Sealed Secrets controller in its own namespace, not `kube-system` | The master-key lifecycle is visible and ArgoCD-reconciled rather than buried in the system namespace; tooling (`kubeseal` flags) must adapt. | [runbook](../docs/runbooks/sealed-secrets-controller.md) |
| Sealed Secrets over SOPS / External Secrets Operator | SOPS needs out-of-band key distribution; ESO needs an external secret store (Vault, Azure Key Vault, etc.) which a self-funded homelab does not justify. Sealed Secrets self-contained in-cluster with one secret to back up. | [runbook](../docs/runbooks/sealed-secrets-controller.md) |
| NetworkPolicy on `llm-gateway` only; `monitoring` and `sealed-secrets` deferred | Cost of getting Prometheus's egress right under `serviceMonitorSelector: {}` is high and failure mode is silent. Sealed-secrets controller's high-value secret is at-rest in etcd, not in transit. | [ADR-009](../docs/adr/ADR-009-networkpolicy-scope.md) |
| Per-pod NetworkPolicies over per-flow | Readable unit is "what can this pod do?" rather than "what flows are permitted on this edge?" — easier to review, easier to extend when a pod is added. | [ADR-009](../docs/adr/ADR-009-networkpolicy-scope.md) |
| Workload `PrometheusRule` ships; Alertmanager stays disabled (rules fire to Prometheus UI only) | Rules carry diagnostic value without external routing. Paging into a void with no on-call rotation is operational theatre — a page no one acts on devalues the alert in the operator's mind and presents a false picture of maturity. Re-enable is one values change away if a real audience appears. | [ADR-010](../docs/adr/ADR-010-alertmanager-scope.md) |
| Latency rule excludes `/v1/chat/completions` handler | LLM inference is legitimately slow (multi-second generations are normal). A slow fast-path (`/healthz`, `/metrics`) signals event-loop contention or resource starvation — the real diagnostic signal. | [ADR-010](../docs/adr/ADR-010-alertmanager-scope.md) |

---

## Observability of the observability

Prometheus self-scrapes via the
`kube-prometheus-stack-prometheus` ServiceMonitor; the operator
self-scrapes via `kube-prometheus-stack-operator`. The 30+
`PrometheusRule` resources delivered by the chart cover apiserver
SLOs, kubelet liveness, node-exporter resource saturation, kube-state-
metrics object-count anomalies, and the Prometheus and operator
internals themselves.

Workload rules now ship alongside (see [Phase 5](#phase-5--workload-prometheusrule-for-the-llm-gateway)
above): `LLMGatewayDown`, `LLMGatewayHighErrorRate`, and
`LLMGatewayHighLatency`. They are evaluated by Prometheus on the
standard 30-second interval and fire to the Prometheus UI's `/alerts`
endpoint. Alertmanager is intentionally **not** installed — see
[ADR-010](../docs/adr/ADR-010-alertmanager-scope.md) for the recorded
scope decision.

Grafana ships pre-loaded with the standard kube-prometheus-stack
dashboards. No custom dashboard JSON is committed to this project
today — they exist on the Grafana instance only. Sealing them into Git
(via ConfigMap + `sidecar.dashboards.enabled: true`) is on the
roadmap; not blocking.

---

## Known gaps (tracked work)

| Gap | Status | Tracker |
|---|---|---|
| No TLS on observability UIs — all access via `kubectl port-forward` | Deliberate — cluster runs `--disable traefik`, no Ingress controller installed | Week 4 — paired cert-manager + Traefik IngressRoute work |
| NetworkPolicy scope limited to `llm-gateway` | Deliberate, reasoning recorded | [ADR-009](../docs/adr/ADR-009-networkpolicy-scope.md) — revisit if observability gateway introduced |
| Alertmanager disabled; rules fire to Prometheus UI only | Deliberate, reasoning recorded | [ADR-010](../docs/adr/ADR-010-alertmanager-scope.md) — revisit if a real on-call audience appears |
| No log aggregation (Loki) | Deliberate — homelab has no high-availability persistent storage; workloads here don't have enough pods to tail | Bridge §4.5 — "what I deliberately didn't build" |
| No distributed tracing (Tempo) | Deliberate — no workload emits OpenTelemetry spans cleanly today (LiteLLM does not) | Bridge §4.5 |
| Full restore-from-backup test for sealed-secrets master key | Not routinely executed (controller-restart test passes — see runbook) | Next cluster rebuild (runbook §Known gaps) |
| Grafana dashboard JSON not committed to Git | Roadmap (not blocking) | Future PR |
| Image-digest pinning for upstream charts | Deferred (chart-version pin is auditable; digest is belt-and-braces) | Roadmap |

### Closed in the P5 closing pass

| Gap | Resolution |
|---|---|
| No workload-specific `PrometheusRule` resources | [`prometheusrules.yaml`](../k8s/workloads/llm-gateway/templates/prometheusrules.yaml) ships 3 rules (`LLMGatewayDown`, `LLMGatewayHighErrorRate`, `LLMGatewayHighLatency`). Status labels filtered as `"2xx"`/`"5xx"` per the FastAPI instrumentator's bucketing; latency rule excludes `/v1/chat/completions` because LLM inference is legitimately slow. See [Phase 5](#phase-5--workload-prometheusrule-for-the-llm-gateway). |
| Alertmanager re-enable / paging decision | Explicit scope recorded in [ADR-010](../docs/adr/ADR-010-alertmanager-scope.md): keep disabled, rules-only fire to Prometheus UI. Re-enable is one values change away if an on-call audience appears; the ADR documents the trigger conditions for a future ADR to supersede this one. |
| `[Architect fills in]` markers in bridge document §4.5 (P5 depth view) | Filled in PR #22: multi-source-over-umbrella as the load-bearing decision, Loki as the deliberate didn't-build. |
| P5 README does not exist | Created in this closing pass (#23 + iterations). |

---

## Verification

End-to-end check that the P5 surface is operational. Every command is
read-only against the running cluster; none modify state.

```bash
# 1 — Confirm all P5 Applications reconcile cleanly.
kubectl get application -n argocd \
  kube-prometheus-stack sealed-secrets \
  -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status
# Expected:
#   NAME                   SYNC     HEALTH
#   kube-prometheus-stack  Synced   Healthy
#   sealed-secrets         Synced   Healthy

# 2 — ServiceMonitors discovered across all namespaces.
kubectl get servicemonitor -A
# Expected: 8 in monitoring + 1 (llm-gateway) in llm-gateway = 9 total.

# 3 — Prometheus targets all UP.
kubectl -n monitoring exec prometheus-kube-prometheus-stack-prometheus-0 \
  -c prometheus -- wget -qO- 'http://localhost:9090/api/v1/targets' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
      [print(t['scrapePool'], '→', t['health']) for t in d['data']['activeTargets']]"
# Expected: every scrapePool reports 'up' with no lastError.

# 4 — Sealed-Secrets controller responsive (versions match locally and in-cluster).
kubeseal --version
kubectl -n sealed-secrets get deployment sealed-secrets \
  -o jsonpath='{.spec.template.spec.containers[0].image}'
# Expected: client and controller within a minor version of each other.

# 5 — NetworkPolicy enforcement empirically active (throwaway test).
NS=netpol-verify-$$
kubectl create ns "$NS"
kubectl -n "$NS" run target --image=nginx:alpine --restart=Never --port=80 -l app=target
kubectl -n "$NS" run client --image=busybox:1.36 --restart=Never --command -- sleep 600
kubectl -n "$NS" wait --for=condition=Ready pod/target --timeout=60s
kubectl -n "$NS" wait --for=condition=Ready pod/client --timeout=60s
TARGET_IP=$(kubectl -n "$NS" get pod target -o jsonpath='{.status.podIP}')
kubectl -n "$NS" exec client -- wget -qO- --timeout=3 "http://${TARGET_IP}" >/dev/null \
  && echo "baseline OK" || echo "baseline UNEXPECTED FAIL"
cat <<EOF | kubectl -n "$NS" apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all-ingress
spec:
  podSelector: { matchLabels: { app: target } }
  policyTypes: [Ingress]
EOF
sleep 4
kubectl -n "$NS" exec client -- wget -qO- --timeout=3 "http://${TARGET_IP}" >/dev/null 2>&1 \
  && echo "POLICY NOT ENFORCED — fix CNI / install kube-router before relying on NetworkPolicy" \
  || echo "POLICY ENFORCED — kube-router is doing its job"
kubectl delete ns "$NS" --wait=false

# 6 — LLM gateway scrape works through the NetworkPolicy boundary.
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
PF=$!
sleep 2
curl -s http://localhost:9090/api/v1/query \
  --data-urlencode 'query=up{job=~".*llm-gateway.*"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
      print(d['data']['result'][0]['value'][1] if d['data']['result'] else 'NO_DATA')"
kill $PF
# Expected: '1' (target is up).

# 7 — Sealed Secrets controller restart preserves decryption capability.
#     Full procedure (with pre-flight sync-policy suspension) is in:
#     docs/runbooks/sealed-secrets-controller.md

# 8 — Workload PrometheusRules loaded and visible in Prometheus.
kubectl -n llm-gateway get prometheusrule llm-gateway
# Expected: NAME llm-gateway, AGE > 0.
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090 &
PF=$!; sleep 2
curl -s http://localhost:9090/api/v1/rules \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
      [print(g['name'], '->', [r['name'] for r in g['rules']]) \
       for g in d['data']['groups'] if g['name']=='llm-gateway.rules']"
kill $PF
# Expected:
#   llm-gateway.rules -> ['LLMGatewayDown', 'LLMGatewayHighErrorRate', 'LLMGatewayHighLatency']

# 9 — Alertmanager is intentionally NOT installed (per ADR-010 scope).
kubectl -n monitoring get pods -l app.kubernetes.io/name=alertmanager 2>&1
# Expected: No resources found in monitoring namespace.
```

---

## Project history

P5 came together in three stages:

1. **Sealed-Secrets controller deployed** (commit history under
   `k8s/apps/sealed-secrets.yaml` and the runbook draft). The decision
   to pin the controller into a non-`kube-system` namespace was made
   here and locked in the runbook's `kubeseal` flag convention.

2. **kube-prometheus-stack via multi-source Application** (PR landed
   the standalone Application + values file + ADR-006). The
   `serviceMonitorSelector: {}` gotcha and the `ServerSideApply=true`
   requirement were discovered during this phase and recorded in
   ADR-006's Rationale section, not as warts.

3. **P5 hardening + closing pass** (a series of PRs that produced and
   then refined the current shape):
   - PR #18 — NetworkPolicy baseline on `llm-gateway` + ADR-009
   - PR #23 — observability data-flow diagram (06) + this README
     (recovered from the #19/#20 stack after a squash-merge SHA
     mismatch caused GitHub to auto-close them)
   - PR #21 — bridge document bullet-label cleanup across §4.1–§4.5
     (uniform "Load-bearing decision:" label)
   - PR #22 — bridge document §4.5 architect-voice fills (multi-source
     decision; Loki deferred); diagram-06 + ADR-009 reading-path
     links activated
   - PR #24 — diagram 06 + 07 readability redesign (06: TB layout
     with single shared scrape edge label, soft cluster fills;
     07: 6 IN / 5 OUT items, uniform 3-5 word labels, invisible
     edges forcing the two-column stack)
   - PR-E — workload `PrometheusRule` resources + ADR-010 Alertmanager
     scope (this stage). Closes the last open P5 gap.

cert-manager + TLS for the observability UIs is paired with the
Traefik IngressRoute work in Week 4 — not P5 scope.

The forensic detail of any specific bring-up issue (e.g., the etcd
member-config corruption from a mistyped k3s join command — see
[`02-k3s-platform/README.md`](../02-k3s-platform/README.md#issue-6--accidental-self-join-on-control-01))
lives where the workload it pertains to lives. This README is the
landing page; the depth lives in the linked artefacts.
