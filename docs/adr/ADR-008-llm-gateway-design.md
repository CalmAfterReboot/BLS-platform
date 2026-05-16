# ADR-008: LLM Gateway design — API gateway pattern over a routed-provider fleet
**Date:** 2026-05-16
**Status:** Stub — Architect to complete

> Stub ADR. The README under `k8s/workloads/llm-gateway/README.md`
> already records the four load-bearing decisions in tabular form;
> this ADR exists so each decision has a permanent home written in
> the architect's voice. Sections marked `[Architect fills in]` need
> the architect's narrative — 2-4 paragraphs each — before this ADR
> moves from **Stub** to **Accepted**.

## Context

Project 4 needs a single, stable HTTP endpoint that callers can point
at and get LLM completions from — without the callers having to know
which provider answered, in which network, with which dialect. The
homelab has an Ollama instance on a Proxmox host running open models;
the AKS environment has Azure OpenAI; an external DeepSeek API is also
in scope. All three speak slightly different APIs and have different
failure modes, latencies, and cost profiles.

The platform constraints are:

- One contract for callers: OpenAI-compatible (so any client SDK works).
- Auth must work even when no managed identity provider is in front.
- The homelab Ollama is the cheapest backend and should be preferred
  when available; the cloud backends are fallback / overflow.
- Observability has to fit the kube-prometheus-stack pattern already
  established in P5 (ServiceMonitor + `/metrics`).
- This sits inside the existing GitOps and matrix-ApplicationSet
  architecture (ADR-005); no new control plane.

## Decision

Adopt the **API gateway pattern with a routed provider fleet**:

1. **FastAPI proxy at the edge.** Bearer-token auth and request
   shaping live here; no model logic.
2. **LiteLLM in proxy mode (not SDK mode) as the router.** Normalises
   every provider to the OpenAI dialect; owns retries, caching, and
   routing strategy.
3. **Ollama runs natively on the Proxmox host, outside k3s.** Reached
   over the homelab LAN by LiteLLM.
4. **Three separate Deployments**, not a single pod, so gateway,
   LiteLLM, and Redis can be lifecycle-managed independently.
5. **`routing_strategy: least-busy`** for the multi-model
   single-host Ollama topology.

## Rationale

[Architect fills in — 2-4 paragraphs covering why the API gateway
pattern was chosen over alternatives like direct LiteLLM-as-edge or a
service-mesh-based abstraction. Make explicit the trade-off accepted:
two hops instead of one for any homelab call, in exchange for a clean
auth boundary at the public layer and the ability to swap LiteLLM out
without rewriting auth.]

## Alternatives considered

1. **LiteLLM as edge (no FastAPI).** Rejected — LiteLLM's auth model
   is built around spend-tracking with a PostgreSQL dependency this
   stack does not have, and putting LiteLLM at the public boundary
   couples auth to the routing layer.
2. **Ollama inside k3s.** Rejected — language-model weight loads
   conflict with container memory ceilings; native Proxmox execution
   gives unbounded RAM access on dedicated hardware.
3. **Round-robin routing.** Rejected for the single-host multi-model
   case — a slow model would block the round-robin slot even when
   another model is idle. Least-busy is the correct fit.
4. **Single-pod (gateway + LiteLLM + Redis sidecar).** Rejected on
   lifecycle grounds — these three components are upgraded by
   different mechanisms (CI image build, upstream tag bump, dependency
   pin) and should not restart together.

[Architect fills in — any alternatives the architect considered and
discarded that aren't in this list; record them so the ADR captures
the full decision space.]

## Consequences

**Accepted costs:**
- Two hops for every request (FastAPI → LiteLLM → backend). Latency
  budget includes ~5-10ms of in-cluster networking overhead.
- LiteLLM memory footprint required iterative right-sizing (now 2Gi
  limit / 512Mi request) — captured in the README's "things to know"
  section.
- The bootstrap `secret.yaml` ships plaintext placeholder keys
  pending Sealed Secrets (WU-4). Explicitly time-limited.

**Capabilities gained:**
- Single OpenAI-compatible endpoint covering local + cloud backends.
- LiteLLM can be replaced (or upgraded across breaking versions) by
  changing one image tag in `values.yaml` — no FastAPI code change.
- Auth boundary at the public edge makes the security model
  inspectable in one file (`app/middleware/auth.py`).
- Redis cache is wired in from day one; semantic caching is now a
  configuration change, not a topology change.

[Architect fills in — the second-order consequences the architect
sees that aren't yet observable: lock-in risks, what this rules out
later, how this would have to be re-thought if the model count grew
10x.]

## Review trigger

Revisit this ADR when any of the following becomes true:

- Sustained model count exceeds the single-host Ollama capacity
  (would invalidate `least-busy` routing and the
  Proxmox-host-not-k3s decision).
- A managed identity provider is introduced in front of the gateway
  (would move auth off FastAPI middleware).
- LiteLLM gains a no-database auth mode that meets the same
  guarantees (would let the gateway layer collapse into LiteLLM).
- Sealed Secrets is bypassed by a managed-secrets integration
  (would change the WU-4 follow-up path).
