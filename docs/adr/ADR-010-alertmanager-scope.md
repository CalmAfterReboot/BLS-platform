# ADR-010 — Alertmanager Scope: Rules Ship, Routing Stays Off

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-24 |
| **Project** | BLS Project 5 — Observability + Security |
| **Deciders** | BLS DevOps |

---

## Context

Two things land in the same close-out pass for P5:

1. Workload-specific `PrometheusRule` resources ship with the LLM gateway chart (`k8s/workloads/llm-gateway/templates/prometheusrules.yaml`). Three rules: `LLMGatewayDown` (target absent for 5m, critical), `LLMGatewayHighErrorRate` (5xx ratio > 5% for 10m, warning), `LLMGatewayHighLatency` (p99 on non-LLM endpoints > 1s for 10m, warning).
2. The `kube-prometheus-stack` values overlay at `05-observability-security/values/kube-prometheus-stack.yaml` carries `alertmanager.enabled: false` — Alertmanager is not installed in this deployment.

The question this ADR settles: now that workload rules exist, do we re-enable Alertmanager and route alerts somewhere, or do we keep Alertmanager off and let the rules fire to the Prometheus UI only?

This is a portfolio-quality decision, not a production-incident decision. There is no on-call rotation on this homelab; there is no audience expecting to be paged when the LLM gateway returns a 5xx burst at 3 a.m.

---

## Options Considered

### Option A — Re-enable Alertmanager, route to a self-hosted destination (ntfy.sh, Telegram bot, Discord webhook)

Install Alertmanager via the chart values, configure a single receiver pointing at a self-hosted notification service the architect actually checks.

**Rejected.** The destination is still a place no one is on-call for. A Telegram channel that pings the architect's personal phone at 3 a.m. for a single homelab gateway pod is operational performance theatre — it imitates the surface of an incident-response posture without the underlying rotation, runbook hand-off, or escalation policy that would make a page actually actionable. A page that the recipient mutes within 48 hours is worse than no page at all: it teaches the receiver to ignore the channel.

### Option B — Re-enable Alertmanager, route to email

Same critique as Option A. Email-routed alerts that no one acts on become inbox noise; over weeks the rule is effectively silenced by the receiver's filter, and the system carries the shape of paging without any of the function.

### Option C — Keep Alertmanager disabled; rules fire to the Prometheus UI only *(selected)*

The three workload rules are evaluated by Prometheus on its standard `interval: 30s` schedule. When a rule's expression is true for the `for:` duration, the alert transitions to `firing` state and becomes visible at `/alerts` and `/rules` in the Prometheus UI (reached via `kubectl port-forward svc/kube-prometheus-stack-prometheus 9090:9090 -n monitoring`).

No external destination is configured. No paging.

### Option D — Don't ship workload rules at all

Skip Option C. Don't add the `PrometheusRule` resources. The chart's ~30 default rules (apiserver SLOs, kubelet, node-exporter, etc.) provide cluster-level alerting; skip workload-level entirely.

**Rejected.** Workload rules carry diagnostic signal even without external routing. The act of writing the PromQL expressions (with the right metric names, the right label filters, the right `for:` durations) is portfolio evidence that the architect understands the metric model the workload exposes. A reviewer reading `prometheusrules.yaml` can see what the architect believes the load-bearing failure modes are. Removing the file removes that evidence.

---

## Decision

**Workload PrometheusRules ship and fire. Alertmanager stays disabled. Rules are visible at the Prometheus UI `/alerts` endpoint; nothing routes externally.**

This is the explicit, recorded scope statement. It is intentional, not an oversight, and not a "to be enabled later" placeholder.

---

## Rationale

**Rules carry diagnostic value without external routing.** A `firing` state in the Prometheus UI is sufficient signal for a homelab operator who already runs an explicit `kubectl get application -n argocd` check when they sit down to work. The alert UI surfaces "what's wrong right now" without requiring the operator to remember which workload to check.

**Paging into a void is operational performance theatre.** Re-enabling Alertmanager with no on-call rotation creates the shape of an incident-response posture without the function. A page that no one acts on is worse than no page: it trains the recipient to ignore the channel, devalues the alert in the operator's mind, and presents a false picture of operational maturity to anyone reading the platform configuration. The portfolio's job is to demonstrate honest engineering judgement, not to ship pageable infrastructure that nobody pages.

**Re-enable is one values change away.** If a real on-call audience appears (a team takes over, a customer needs SLOs, a downstream consumer needs to be paged on gateway failures), the path is:

1. Change `alertmanager.enabled: false` → `true` in `05-observability-security/values/kube-prometheus-stack.yaml`.
2. Configure a receiver under `alertmanager.config.receivers` and a route under `alertmanager.config.route`.
3. Sync via ArgoCD.

That is a one-line values change plus a receiver/route configuration. The rules themselves do not change. The cost of starting from the rules-only state and adding routing later is approximately zero; the cost of starting from a fully-routed state and discovering the route is dead is significantly higher.

**This is the portfolio's honesty discipline applied.** Bridge document §6 lists deliberate non-claims explicitly ("no formal 24/7 SRE on-call — that's MSP context, not this repo"). Routing rules to a destination the architect cannot operationally honour would contradict that scope statement. Keeping the rules visible-but-unrouted preserves both the technical evidence (the rules exist and work) and the scope honesty (no claim of paging maturity).

---

## Consequences

### Positive

- No false signal of operational maturity. A reviewer reading this ADR sees the deliberate scope rather than inferring it from the absence of an Alertmanager spec.
- The three rule files exist as portfolio evidence that the architect understands the gateway's failure modes (down vs error-rate vs latency on the fast path), the metric model the FastAPI instrumentator exposes, and the PromQL needed to assert thresholds correctly.
- The re-enable path is documented and cheap to execute.
- The Prometheus UI's `/alerts` endpoint remains the authoritative "what's wrong right now" view for the operator on the workstation, without competing channels.

### Negative

- A real degradation that happens overnight is invisible until the next manual `port-forward` check the operator runs. The portfolio does not claim 24/7 alerting; this is consistent with that claim but is still a real operational gap.
- A hiring manager scanning the platform for "paging maturity" sees no paging. This ADR is the explicit answer to that question — the choice is deliberate, not a missing feature.
- If the operator adds workloads with stricter availability expectations (e.g., a customer-facing API), the rules-only posture becomes inappropriate and needs to be revisited. That revisit lives in a future ADR superseding this one, not in silent re-enable.

---

## Alternatives Rejected

| Alternative | Reason |
|---|---|
| Re-enable + route to ntfy.sh / Telegram / Discord | Homelab has no on-call rotation; the page would be received by the architect's personal phone alone, with no escalation. A page no one acts on is operational theatre. |
| Re-enable + route to email | Same critique as above. Email rules without an audience become inbox noise; the receiver's filter silences them within weeks. |
| Don't ship workload rules at all | Loses portfolio evidence that the architect understands the metric model and failure modes. The chart's ~30 default rules cover cluster infrastructure; workload-level signal is the part this portfolio adds. |
| Ship rules + ship Alertmanager with NO receivers configured | Worst of both worlds: the operational surface looks like "paging exists" but no routing happens; future operators reading the configuration believe paging is wired and may not test it before relying on it. |

---

## Implementation

### Files Changed

| File | Change |
|---|---|
| `k8s/workloads/llm-gateway/templates/prometheusrules.yaml` | New — 3 workload rules, gated by `.Values.prometheusRules.enabled` |
| `k8s/workloads/llm-gateway/values.yaml` | Added `prometheusRules.enabled: true` block with comment referencing this ADR |
| `docs/adr/ADR-010-alertmanager-scope.md` | This document |
| `05-observability-security/README.md` | Updated Known Gaps + Key Decisions to reference this ADR; moved the Alertmanager line from "tracked as PR-E" to "scope recorded in ADR-010" |
| `05-observability-security/values/kube-prometheus-stack.yaml` | `alertmanager.enabled: false` unchanged; comment block added explaining this is the ADR-010 recorded decision (not an oversight) |

### Verification

```bash
# 1 — Confirm the PrometheusRule resource is created and operator picks it up.
kubectl -n llm-gateway get prometheusrule llm-gateway
# Expected: NAME llm-gateway, AGE > 0

# 2 — Confirm Prometheus loaded the rules.
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s http://localhost:9090/api/v1/rules | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
    [print(g['name'], '->', [r['name'] for r in g['rules']]) \
     for g in d['data']['groups'] if g['name']=='llm-gateway.rules']"
# Expected: llm-gateway.rules -> ['LLMGatewayDown', 'LLMGatewayHighErrorRate', 'LLMGatewayHighLatency']

# 3 — Confirm Alertmanager pod does NOT exist (per the scope decision).
kubectl -n monitoring get pods -l app.kubernetes.io/name=alertmanager
# Expected: No resources found.

# 4 — Optional smoke test: trigger LLMGatewayDown.
kubectl -n llm-gateway scale deployment llm-gateway --replicas=0
# Wait for `for: 5m` to elapse, then:
curl -s http://localhost:9090/api/v1/alerts | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
    [print(a['labels']['alertname'], '->', a['state']) for a in d['data']['alerts']]"
# Expected: LLMGatewayDown -> firing
# Restore:
kubectl -n llm-gateway scale deployment llm-gateway --replicas=1
```

---

## Revisit triggers

This ADR should be revisited when any of the following becomes true:

- A non-architect operator takes responsibility for the platform (paging suddenly has a real receiver).
- A customer or downstream system depends on the gateway's availability with a stated SLO (paging gains a contractual basis).
- The homelab grows past a single operator (paging requires a real rotation and escalation policy, not just a destination).

Until one of those triggers fires, the decision stands.
