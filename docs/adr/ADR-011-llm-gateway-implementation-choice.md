# ADR-011 — LLM Gateway Implementation Choice: LiteLLM Adopted; Hand-Rolled Reference Preserved

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-25 |
| **Project** | BLS Project 4 — LLM Gateway |
| **Deciders** | BLS DevOps |

---

## Context

Before the production LLM gateway at [`k8s/workloads/llm-gateway/`](../../k8s/workloads/llm-gateway/) was built around LiteLLM (the choice recorded in [ADR-008](ADR-008-llm-gateway-design.md)), a from-scratch Python implementation was built first as `bls-ai-gateway` — now consolidated into [`projects/04-llm-gateway-reference/`](../../projects/04-llm-gateway-reference/) as a frozen reference.

The reference implementation established the routing primitive end-to-end:

- A **`Provider` protocol** ([`app/providers/base.py`](../../projects/04-llm-gateway-reference/app/providers/base.py)) defining the contract every backend (OpenAI, mock, future Azure/Anthropic) must satisfy.
- A **provider registry** ([`app/providers/registry.py`](../../projects/04-llm-gateway-reference/app/providers/registry.py)) that resolves names to concrete instances at startup based on env config, so the routing layer never imports a provider module directly.
- A **tier policy table** (`TIER_CHAINS` in [`app/routing.py`](../../projects/04-llm-gateway-reference/app/routing.py)) declaring, per pricing/quality tier, the preferred order of providers to try.
- A **sequential failover loop** that walks the chain in order, attempts each provider, and falls through to the next on `UpstreamError`, returning `AllProvidersFailedError` only when every provider in the tier has been exhausted.
- **Error translation** ([`app/errors.py`](../../projects/04-llm-gateway-reference/app/errors.py)) mapping provider-specific exceptions to a uniform `UpstreamError` so the routing layer does not need to know each provider's failure idioms.

The implementation was verified end-to-end against real OpenAI traffic: [`docs/verification/openai-live-happy-path-2026-05-23.json`](../../projects/04-llm-gateway-reference/docs/verification/openai-live-happy-path-2026-05-23.json) (a real `gpt-4o-mini` completion through the gateway) and [`docs/verification/openai-live-forced-failover-2026-05-23.json`](../../projects/04-llm-gateway-reference/docs/verification/openai-live-forced-failover-2026-05-23.json) (a forced failover after killing the primary provider). Both ran against the live OpenAI API, not a mock.

With the routing primitive validated, the question for production became: port this code, or adopt the established community library?

---

## Options Considered

### Option A — Port the hand-rolled routing layer into the production gateway

Take `app/providers/`, `app/routing.py`, and `app/errors.py` from the reference impl and embed them inside the production FastAPI service. LiteLLM is not used; the FastAPI service directly drives provider HTTP clients via the hand-rolled `Provider` protocol.

**Rejected.** The reference impl gets the routing primitive right, but the production gateway needs strictly more than that:

- A **Redis-backed cache** (cost discipline against repeated identical prompts) — would need a custom in-Python cache layer or a separate caching middleware.
- **Prometheus metrics** that match the kube-prometheus-stack conventions already established in P5 — would need hand-rolled histograms for upstream latency per provider, error counters per status class, cache-hit ratios.
- An **OpenAI-compatible API surface** that every existing client SDK already speaks — would need to re-implement the OpenAI chat-completions request/response schema in Pydantic with full fidelity (function-calling, streaming, tool-calls, image input).
- `drop_params`, `disable_spend_logs`, `routing_strategy: least-busy`, and other operational knobs — would need to be re-invented from scratch.

Building each of these would have meant re-implementing a feature LiteLLM already ships and maintains.

### Option B — Adopt LiteLLM in proxy mode; archive the hand-rolled impl as a portfolio artefact *(selected)*

Use LiteLLM as the router (per ADR-008's wider gateway architecture). The hand-rolled implementation is preserved at `projects/04-llm-gateway-reference/` as a frozen reference. No further development of the from-scratch routing layer is planned.

### Option C — Hybrid: hand-rolled routing for known providers, LiteLLM for the rest

Some providers go through the hand-rolled `Router`; others go through LiteLLM. The FastAPI edge layer dispatches based on a config table.

**Rejected as a straw man.** Maintaining two routing layers doubles the operational surface, doubles the test surface, and makes the production gateway's behaviour depend on which provider the caller hit. The split has no architectural justification — it is debt-by-construction.

---

## Decision

**Adopt LiteLLM in proxy mode for the production gateway. Preserve the hand-rolled implementation under `projects/04-llm-gateway-reference/` as a frozen reference; no further development is planned.**

This ADR records the *trade-off between rolling-my-own and adopting LiteLLM* that ADR-008 takes for granted. ADR-008 documents *what* the production gateway is (FastAPI + LiteLLM-in-proxy-mode + Redis); this ADR documents *why* the from-scratch routing layer that the reference impl proved out was not the path forward.

---

## Rationale

- **The routing primitive was understood, not adopted blindly.** Building the from-scratch impl and verifying it end-to-end against real OpenAI established that the architectural reasoning (Provider protocol, tier chains, sequential failover, error translation) was sound. LiteLLM was then adopted from a position of knowing what was being delegated and why.
- **LiteLLM ships the primitive + adjacent concerns.** Routing, failover, model registry, retries, cache, metrics, OpenAI-compatible surface, and cost-discipline knobs all live behind one upstream. Continuing from scratch would have meant tracking each of those as a separate hand-rolled feature.
- **Community-maintained vs solo-maintained.** LiteLLM has an active project + community; the hand-rolled layer would have been a one-person codebase. For a platform meant to outlive any single sprint, the maintenance asymmetry matters.
- **The reference impl is more valuable as evidence than as code.** Preserved, it shows the architectural reasoning behind the production deployment. Ported, it would have become legacy code that drifted out of sync with LiteLLM's feature curve.

---

## Consequences

- **External dependency added** on LiteLLM. Tracked via the pinned `ghcr.io/berriai/litellm:main-latest` image; flagged in the LLM gateway chart README's "Known gaps" section as a floating-tag pin to be hardened to a digest in a follow-up.
- **`projects/04-llm-gateway-reference/` is read-only.** The README banner declares it archived; the upstream `bls-ai-gateway` repository is scheduled for archive.
- **Future provider additions** (Azure OpenAI, Anthropic, DeepSeek) extend LiteLLM's `configmap-litellm.yaml` `model_list`, not the hand-rolled `Provider` protocol. The protocol survives as documentation of how routing decomposes, not as production code.
- **The FastAPI edge layer** (auth, request shaping, `/metrics`, `/healthz`) remains the only first-party Python in the production path. Everything between "request reaches the cluster" and "request reaches a provider" is LiteLLM.

---

## Review trigger

Revisit this decision if any of the following becomes true:

1. **LiteLLM stops being maintained** or releases a breaking change that costs more than the implementation effort to absorb.
2. **A provider requirement emerges that LiteLLM cannot satisfy** — for example, a routing strategy that depends on observability data LiteLLM does not expose, or a contract LiteLLM cannot speak.
3. **Cost or latency from the extra LiteLLM hop** becomes material at production scale (not the case today on a homelab cluster, but worth a re-check at any future cloud-burst point).

If any of these triggers fires, the routing primitive in `projects/04-llm-gateway-reference/` is the documented starting point for a from-scratch replacement — not a green-field rewrite.
