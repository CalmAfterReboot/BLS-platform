# ADR-008: LLM Gateway design — API gateway pattern over a routed-provider fleet
**Date:** 2026-05-16 (drafted) · 2026-05-24 (accepted)
**Status:** Accepted

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

The API gateway pattern was chosen over its two leading alternatives
— LiteLLM serving directly at the edge, and a service-mesh-based
abstraction layered over LiteLLM — because each alternative made a
different security or operational boundary worse without earning a
meaningful gain at this scale.

LiteLLM-as-edge would have shaved one network hop off every request
but at the cost of coupling caller authentication to LiteLLM's
spend-tracking model, which assumes a PostgreSQL database for budgets
and audit. Bringing PostgreSQL onto this platform purely to satisfy
an authentication boundary would have introduced a stateful failure
domain to a stack designed to be stateless at the edge. The FastAPI
layer makes the authentication surface a fifteen-line middleware in
a file that can be diffed in a code review, with no database
dependency, no spend-tracking lifecycle to manage, and no upgrade
path that risks the auth contract.

A service-mesh option (Istio sidecar, Linkerd) would have moved
mTLS, retries, and routing-policy enforcement to the mesh and
reduced the gateway's responsibilities to request shaping. Rejected
on two grounds: the mesh's authentication primitives do not match
the simple Bearer-token model this gateway uses without bolting an
external auth provider in front (mesh auth assumes mTLS on top of
mTLS, which means another set of certificates to rotate); and a
mesh's operational footprint is non-trivial — the second-order
debugging surface (envoy access logs, sidecar configmaps, per-pod
injector annotations) would have outweighed any benefit at this
single-cluster, single-workload scale.

The accepted trade-off is two in-cluster hops per request (caller →
FastAPI → LiteLLM → backend) in exchange for: a single file that
owns authentication; a routing layer (LiteLLM) that can be swapped
for a different multi-provider router without touching auth; and the
ability to add semantic caching, request-shape rate limiting, or
response post-processing as future FastAPI middleware without
changing the routing contract callers depend on. The latency cost is
~5–10 ms of in-cluster networking overhead per request — well under
the inherent backend latency on any real model call.

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

5. **Native cloud-provider AI gateway (Azure API Management with
   policy expressions).** Rejected — the portfolio runs primarily on
   the homelab k3s cluster, and an Azure-bound managed gateway would
   have made the AKS path the privileged path while leaving the
   homelab path on a custom stack. Symmetry across deployment targets
   is itself a portfolio claim worth preserving; tying half the
   routing logic to a managed Azure service breaks it.

6. **Single-process Python service combining auth + routing.**
   Rejected — this would have inlined LiteLLM as a library inside
   the FastAPI process, removing the proxy hop and the second
   container. But LiteLLM's release cadence is faster than this
   gateway's, and treating LiteLLM as a separately-versioned service
   (proxy mode) lets it be upgraded by bumping one image tag in
   `values.yaml` without rebuilding the gateway image or restarting
   the auth layer. The lifecycle independence is worth the second
   container.

7. **Plaintext Secret manifest indefinitely.** Considered as a
   permanent state; rejected. The bootstrap `secret.yaml` shipped
   placeholder plaintext keys at v0.4.0 as an explicit time-limited
   gap. WU-4 closed that gap on 2026-05-24 by replacing the manifest
   with a `--scope=strict` Bitnami `SealedSecret` that also seals the
   Ollama endpoint address (previously a plaintext value in
   `values.yaml`). No homelab-internal address or credential is
   committed in plaintext now.

## Consequences

**Accepted costs:**
- Two hops for every request (FastAPI → LiteLLM → backend). Latency
  budget includes ~5–10 ms of in-cluster networking overhead.
- LiteLLM memory footprint required iterative right-sizing (now 2 Gi
  limit / 512 Mi request) — captured in the README's "things to know"
  section. Not yet profiled under sustained representative traffic.
- Three Deployments to manage instead of one (gateway, LiteLLM,
  Redis); lifecycle independence paid for in operational footprint
  (three sets of probes, three rolling-update windows).

**Capabilities gained:**
- Single OpenAI-compatible endpoint covering local + cloud backends.
- LiteLLM can be replaced (or upgraded across breaking versions) by
  changing one image tag in `values.yaml` — no FastAPI code change.
- Auth boundary at the public edge makes the security model
  inspectable in one file (`app/middleware/auth.py`); 401/403 are
  returned as typed JSON envelopes (post the auth-middleware fix on
  2026-05-24 that converted the misplaced `HTTPException` raises
  from `BaseHTTPMiddleware` to direct `JSONResponse` returns).
- Redis cache is wired in from day one; semantic caching is now a
  configuration change, not a topology change.
- Runtime credentials (Bearer API keys, LiteLLM master key, Ollama
  endpoint) are committed encrypted as a `SealedSecret` and unsealed
  in-cluster — no plaintext credential or homelab-internal address
  is committed to git as of WU-4 closure (2026-05-24).
- An opt-in pytest live verification suite exercises the real OpenAI
  path through the LiteLLM SDK — the same library the deployed proxy
  runs — and commits sanitised JSON evidence to
  `docs/verification/`. The gateway's behaviour against a real
  upstream is documented as fact, not assertion.

**Second-order consequences:**

- **Lock-in to LiteLLM's provider abstraction.** Any provider
  LiteLLM does not support cannot be routed through this gateway
  without a custom adapter. Mitigated by LiteLLM's breadth (100+
  providers as of writing) and by the gateway's clean separation:
  a custom adapter would live as a separately-versioned router
  pod, not as code inside the FastAPI process.

- **This design rules out a true edge service mesh.** If a future
  iteration of this platform needs mesh-level capabilities (mTLS
  between every workload, automatic retry budgets, traffic-shifted
  canaries), the FastAPI layer is in the way of mesh injection.
  The most likely re-architecture would push FastAPI's auth into a
  Gateway API resource handled by the mesh ingress and reduce
  LiteLLM to a pure routing pod behind it. Non-trivial migration;
  flagging here is sufficient until the mesh need is real.

- **Scale ceiling: this design assumes single-host Ollama remains
  the homelab primary.** If model count grew 10× and required a
  fleet of Ollama hosts, the `routing_strategy: least-busy` setting
  would not by itself produce sensible behaviour across
  heterogeneous hosts — a slow host's least-busy slot is still
  slower than a fast host's busy slot. The re-architecture path
  is documented in the Review trigger section: introduce per-host
  LiteLLM config blocks with capacity weights, or move to a
  queue-based dispatcher.

- **SDK-vs-proxy version drift is a known live-verification risk.**
  The proxy image is pinned to `main-latest`; the SDK is pinned to
  `>=1.40,<2.0` in `requirements-dev.txt`. The verification suite
  tests the library path; behaviour drift between SDK and proxy
  would not be caught by the suite. Mitigated by pinning the proxy
  to a specific tag the day any production traffic depends on
  specific Router semantics.

## Review trigger

Revisit this ADR when any of the following becomes true:

- Sustained model count exceeds the single-host Ollama capacity
  (would invalidate `least-busy` routing and the
  Proxmox-host-not-k3s decision).
- A managed identity provider is introduced in front of the gateway
  (would move auth off FastAPI middleware).
- LiteLLM gains a no-database auth mode that meets the same
  guarantees (would let the gateway layer collapse into LiteLLM).
- Sealed Secrets is superseded by a managed-secrets integration
  (Azure Key Vault + CSI driver, External Secrets Operator) — would
  change the credential-injection path for the gateway and require
  per-cluster secret-source decisions ahead of any AKS rebuild.
- The live verification suite begins reporting persistent drift
  between the LiteLLM SDK path and the deployed proxy — would
  indicate the `main-latest` pin has diverged enough that the
  SDK-tested behaviour no longer represents deployed behaviour, and
  the proxy should be pinned to a specific tag.
- A second Ollama host (or any heterogeneous backend topology) is
  added on the homelab side — would invalidate the single-host
  `least-busy` reasoning and force a routing-strategy revisit.
