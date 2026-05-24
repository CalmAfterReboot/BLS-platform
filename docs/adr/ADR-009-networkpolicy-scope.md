# ADR-009 — NetworkPolicy Scope: llm-gateway Namespace Enforced, Monitoring and Sealed-Secrets Deferred

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-24 |
| **Project** | BLS Project 5 — Observability + Security |
| **Deciders** | BLS DevOps |

---

## Context

P5's chart README and the bridge document's scope-boundary diagram both carry the same scope language: NetworkPolicy enforcement exists "only on the load-bearing namespaces today." That language is honest but unspecified — it does not name which namespaces are in scope, which are out, or why.

Three namespaces on this cluster carry workload that could plausibly justify NetworkPolicy enforcement:

| Namespace | What runs there | Inbound user request path | External egress | Holds credentials |
|---|---|---|---|---|
| `llm-gateway` | FastAPI proxy, LiteLLM router, Redis cache | Yes (via Ingress or port-forward) | Yes (Ollama on Proxmox host, OpenAI, Azure OpenAI, DeepSeek) | Yes (master key, Bearer keys, Ollama endpoint — all from a SealedSecret) |
| `monitoring` | Prometheus, Grafana, Alertmanager (disabled), kube-prometheus-stack operator, kube-state-metrics, node-exporter | No (UIs accessed only via kubectl port-forward, which bypasses NetworkPolicy) | No (Prometheus scrapes in-cluster targets and node IPs only) | Grafana admin password (SealedSecret) |
| `sealed-secrets` | Bitnami sealed-secrets controller (single pod) | No (controller is reconciled-by-controller, not called by clients) | No (controller only talks to the kube-apiserver) | The master decryption key (highest-blast-radius secret on the cluster — but at rest in etcd, not in transit) |

The decision is which of these justify the engineering cost of writing, reviewing, and maintaining NetworkPolicy.

ArgoCD's namespace (`argocd`) already ships seven NetworkPolicies provided by the upstream argocd chart; those are inherited, not authored here, and are not part of this scope question.

NetworkPolicy enforcement on this k3s cluster is confirmed active via an empirical deny-all test (recorded in `05-observability-security/README.md`).

---

## Options Considered

### Option A — Full coverage: NetworkPolicy across every namespace

Default-deny ingress and egress on every namespace, with per-namespace allow rules added until the cluster works again.

**Rejected.** The monitoring namespace's egress surface is the problem. Prometheus must scrape:

- Every kubelet on every node (port 10250, node IPs — not pod IPs)
- Every node-exporter pod (port 9100, daemonset on every node)
- The apiserver (port 443 on the kubernetes service in `default`)
- CoreDNS (port 9153 in `kube-system`)
- kube-state-metrics, the operator itself, Grafana (all within `monitoring`)
- The llm-gateway ServiceMonitor target (in `llm-gateway`)
- Any future ServiceMonitor in any future namespace

A tight egress policy on the Prometheus pod must enumerate every target. The discovery model of `serviceMonitorSelector: {}` is fundamentally at odds with an enumerate-allow egress policy — every new ServiceMonitor would silently fail to scrape until the egress policy is widened to cover its target. The failure mode is invisible: the ServiceMonitor would appear configured, the target would appear discovered, but the scrape would time out at the NetworkPolicy layer with no log surfaced to either side.

The cost of getting this wrong is high; the value of getting it right is low (no inbound user request path into the monitoring namespace; the threat model is "compromised scrape target reaches Prometheus" rather than "external attacker reaches Prometheus").

### Option B — Workload-only: enforce on llm-gateway, defer monitoring + sealed-secrets *(selected)*

Enforce NetworkPolicy on the workload namespace that has authenticated request handling, external credential-bearing egress, and a clear graph of allowed traffic flows. Defer the observability and secrets-controller namespaces with explicit reasoning recorded here.

### Option C — None: ship no NetworkPolicy

Leave every namespace wide open. Rely on the cluster's perimeter (UFW on each node, pfSense on the homelab subnet, no public ingress) for isolation.

**Rejected.** The highest-value workload on the cluster handles authenticated API requests, holds master-key-protected upstream credentials, and egresses to multiple external LLM providers. A lateral-movement scenario from any compromised in-cluster pod to the gateway's `/v1/chat/completions` endpoint (with no Bearer token, since auth is at the FastAPI middleware) bypasses the entire authentication contract. Defence-in-depth requires at least one barrier between in-cluster pods and the gateway's network ingress.

---

## Decision

**Enforce NetworkPolicy on the `llm-gateway` namespace via Helm-chart templates with `--strict` per-pod allows over a default-deny baseline. Explicitly defer `monitoring` and `sealed-secrets` with the reasoning recorded in this ADR.**

The policy set is four resources:

1. `default-deny-all` — baseline deny for every pod in the namespace.
2. `gateway-policy` — selects `app: llm-gateway`; ingress from the `monitoring` namespace's Prometheus pod on port 8000; egress to LiteLLM on 4000 and CoreDNS on 53.
3. `litellm-policy` — selects `app: litellm`; ingress from the gateway pod on 4000; egress to Redis on 6379, CoreDNS on 53, and external IPs (non-cluster CIDRs) on 11434 (Ollama) and 443 (cloud LLM providers).
4. `redis-policy` — selects `app: redis`; ingress from LiteLLM on 6379; egress to CoreDNS only.

Templates live in the chart under `k8s/workloads/llm-gateway/templates/networkpolicies.yaml`, gated by `.Values.networkPolicies.enabled` (default `true`). Cluster CIDRs in the LiteLLM external egress rule are parameterized via `.Values.networkPolicies.podCIDR` and `.Values.networkPolicies.serviceCIDR` for cross-cluster portability.

---

## Rationale

**Per-pod policies over per-flow policies.** A pod is "policied" if any NetworkPolicy selects it; NetworkPolicy semantics are additive across policies that select the same pod. Owning each pod's allowed flows in a single policy resource (gateway, litellm, redis) makes the readable unit "what can this pod do?" rather than "what flows are permitted on this edge?" The deny-all baseline is kept for belt-and-braces: any future pod added to the namespace is denied by default until a policy explicitly admits it.

**External egress as an ipBlock with cluster-CIDR exceptions.** LiteLLM's external destinations are not stable, named pods — they are a static homelab address (Ollama) and a set of cloud provider hostnames (OpenAI, Azure OpenAI, DeepSeek) reached over the public internet. NetworkPolicy cannot resolve hostnames, so the only options are an enumerate-allow of specific IPs (brittle, since cloud provider IPs are unstable) or an ipBlock covering `0.0.0.0/0` with the cluster's pod and service CIDRs `except`-ed out. The latter is the standard pattern for "external-only" egress allows; it prevents the rule from accidentally widening in-cluster reach via a transitive match.

**Chart-templated, opt-out via values flag.** The policies describe traffic for the chart's own pods; they live with the chart resources they protect. The opt-out flag (`networkPolicies.enabled: false`) is for environments where NetworkPolicy enforcement is not active (e.g., a cluster running stock Flannel without kube-router or another controller). Without the flag, the chart fails closed in such a cluster — the policies render but enforce nothing, giving a false signal of defence.

**Monitoring deferral.** The cost of getting Prometheus's egress policy right is high (every ServiceMonitor target must be enumerated), the value is low (no inbound user request path), and the failure mode is silent (scrapes time out at the NetworkPolicy layer with no logged rejection). The right time to revisit is when an observability gateway sits in front of Prometheus, or when ServiceMonitor proliferation becomes a discovery boundary worth enforcing.

**Sealed-secrets deferral.** The controller is a single pod with a cluster-scoped reconciliation duty. It talks to the kube-apiserver and nothing else. The high-blast-radius secret it holds (the master decryption key) is at rest in etcd, not in transit — a NetworkPolicy does not protect it. The threat model that does justify policy on this namespace ("compromised pod in the cluster exfiltrates the master key via the controller's network surface") is not blocked by NetworkPolicy on the sealed-secrets namespace; it is blocked by RBAC on the underlying Secret resource and by the egress policy on the compromised pod's namespace. The latter, in the llm-gateway case, is what this ADR ships.

---

## Consequences

### Positive

- The gateway's `/v1/chat/completions` endpoint is unreachable from any in-cluster pod except via the documented Prometheus scrape path. Lateral movement from a compromised in-cluster workload no longer trivially reaches the authenticated request handler.
- LiteLLM's external egress is constrained to two ports (11434 + 443) on non-cluster IPs. Exfiltration over arbitrary high-numbered ports is blocked at the cluster network layer.
- Redis is reachable only from LiteLLM. A compromised gateway pod cannot directly read or write the response cache.
- The chart is portable to a future AKS rebuild — cluster CIDRs are parameterized, not hardcoded.
- The `networkPolicies.enabled` flag means the chart deploys cleanly on a cluster without policy enforcement (the flag would be set false there) instead of silently shipping policies that look enforcing but are not.

### Negative

- The `monitoring` namespace remains wide open. Prometheus can be reached from any pod on its `:9090` ClusterIP; Grafana on its service port. The threat model that survives this gap: a compromised in-cluster pod accesses Grafana's admin UI directly (the admin password is sealed in a Secret, so the attacker would still need that secret — but the network reachability is unconstrained). Tracked for future revisit when an observability gateway is introduced.
- The `sealed-secrets` namespace has no policy. The controller pod is reachable from any in-cluster pod on the apiserver-proxy path. The marginal value of policing it is low (single pod, no inbound request path beyond reconciliation), but the gap is real.
- The external egress rule on LiteLLM is broad: any IP on the internet on port 443 is reachable. A compromised LiteLLM could exfiltrate to an attacker-controlled HTTPS endpoint as long as DNS resolves. Tightening this requires either an egress proxy (Squid, Envoy) intercepting LiteLLM's outbound traffic, or a hostname-aware policy controller (Cilium with FQDN policies, not stock kube-router). Out of scope for this PR.
- The orphaned Ingress resource in the chart (the cluster runs `--disable traefik`) becomes a configuration trip-hazard if a Traefik or other ingress controller is later installed: the NetworkPolicy currently allows ingress only from the Prometheus pod, so a real ingress controller would be blocked. Documented in the policy template comments; the policy will need an additional ingress rule allowing from the controller's namespace when a controller is added.
- No e2e test covers the policy enforcement — verification is point-in-time, recorded in the PR's verification block, not continuously asserted. A drift-detection mechanism (e.g., a periodic deny-test in CI against a sample workload) is out of scope for this PR.

---

## Alternatives Rejected

| Alternative | Reason |
|---|---|
| Full coverage across all namespaces | Monitoring egress surface is unbounded; enforcing tightly would silently break ServiceMonitor discovery; threat model does not justify the cost |
| No NetworkPolicy at all | Leaves the authenticated request path on the gateway reachable by any in-cluster pod; defeats the FastAPI auth contract under lateral movement |
| Standalone Application under `05-observability-security/` instead of in-chart | Policies describe traffic for the chart's own pods; co-locating them with the chart resources keeps label changes synchronised and means the chart is self-contained |
| Single per-flow policy resources (8 policies, one per allowed flow) | Per-pod policies (4 resources) read more naturally as "what can pod X do?"; per-flow policies fragment that view across multiple files and selectors |
| Hardcoded cluster CIDRs in the template | Breaks chart portability to AKS (different default CIDRs on Azure CNI overlay) and to any homelab cluster with non-default CIDRs |
| Cilium FQDN egress policies | Requires Cilium as the CNI; this cluster runs Flannel with kube-router enforcement; CNI swap is a separate, larger decision |
| Egress proxy (Squid/Envoy) for LiteLLM outbound | Adds a stateful component to the request path; introduces TLS interception or upstream cert pinning concerns; deferred until a real audit requirement justifies the operational cost |

---

## Implementation

### Files Changed

| File | Change |
|---|---|
| `k8s/workloads/llm-gateway/templates/networkpolicies.yaml` | New — 4 NetworkPolicy resources, gated by `.Values.networkPolicies.enabled` |
| `k8s/workloads/llm-gateway/values.yaml` | Added `networkPolicies` block: `enabled: true`, `podCIDR`, `serviceCIDR` defaults |
| `docs/adr/ADR-009-networkpolicy-scope.md` | This document |
| `docs/diagrams/README.md` | Diagram 07 caption updated to reflect "llm-gateway namespace policied; monitoring and sealed-secrets deferred per ADR-009" |
| `docs/diagrams/07-scope-boundary.mmd` | Caption comment block updated to match the catalogue row |

### Verification

```bash
# 1 — confirm NetworkPolicy enforcement is active on the cluster.
# Throwaway deny-all test in a test namespace — pass criterion:
# baseline traffic between two pods passes; deny-all on the target
# blocks the same flow.
# (Recorded in 05-observability-security/README.md "Things to know".)

# 2 — confirm chart renders.
cd k8s/workloads/llm-gateway/
helm template . | grep -c '^kind: NetworkPolicy'   # expect 4
helm template . --set networkPolicies.enabled=false \
  | grep -c '^kind: NetworkPolicy'                  # expect 0

# 3 — confirm Prometheus still scrapes the gateway after sync.
kubectl port-forward svc/kube-prometheus-stack-prometheus 9090:9090 -n monitoring &
curl -s http://localhost:9090/api/v1/targets \
  | jq '.data.activeTargets[] | select(.scrapePool|contains("llm-gateway")) | .health'
# expect: "up"

# 4 — confirm the gateway is reachable from inside the namespace
# (e.g., from LiteLLM pod on /v1/chat/completions, end-to-end test).

# 5 — confirm the gateway is NOT reachable from outside the namespace.
# Spawn a busybox in the default namespace; curl the gateway's
# ClusterIP on :8000 — expect timeout.

# 6 — confirm external egress works from LiteLLM (Ollama + cloud).
# Run the live OpenAI verification suite committed under
# k8s/workloads/llm-gateway/tests/live/; expect green.
```
