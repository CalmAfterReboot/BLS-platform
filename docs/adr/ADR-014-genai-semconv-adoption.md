# ADR-014 — OpenTelemetry GenAI Semantic Conventions: Adoption + Custom `bls.cost_gbp_*` Attributes

| Field | Value |
|---|---|
| **Status** | Accepted (partial — Sequence 4 adds the cost attributes) |
| **Date** | 2026-05-28 |
| **Project** | BLS Project 6 — Platform Engineering (Stream B) |
| **Deciders** | BLS DevOps |

---

## Context

[ADR-013](ADR-013-otel-lgtm-adoption.md) adopted the OpenTelemetry wire format across the LLM gateway. That ADR settled the *transport*; this one settles the *attribute model* — specifically, which OpenTelemetry semantic conventions apply to LLM workloads, what gets emitted by libraries automatically, and which platform-specific attributes the BLS gateway adds on top.

OpenTelemetry's [GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) (work-group draft, marked "experimental" but in production use at multiple LLM vendors) define the canonical attribute names for spans + metrics that wrap LLM calls. Examples:

| Attribute | Meaning |
|---|---|
| `gen_ai.system` | Provider name — `openai`, `azure_openai`, `anthropic`, `ollama`. |
| `gen_ai.request.model` | The model name the caller requested (`gpt-4o-mini`, `llama3.2`). |
| `gen_ai.response.model` | The model name the provider actually used (often the same; sometimes the served-from substitute). |
| `gen_ai.usage.input_tokens` | Tokens billed for the request. |
| `gen_ai.usage.output_tokens` | Tokens billed for the response. |
| `gen_ai.request.temperature` | Sampling temperature, if provided. |
| `gen_ai.response.finish_reasons` | Array — `["stop"]`, `["length"]`, `["content_filter"]`. |

LiteLLM's `otel` callback (enabled in this PR's `configmap-litellm.yaml`) emits the above attributes automatically for every routed request, on every provider it knows about. That is the upstream half.

The platform half — cost-per-request in the operator's chosen currency, lineage-of-decision recording which tier of the model fleet was selected and why — does not exist in the GenAI semconv. We add it as `bls.*` custom attributes, namespaced to make the platform-specific extension obvious.

---

## Decision

**Adopt the OpenTelemetry GenAI semantic conventions verbatim for every attribute LiteLLM's `otel` callback emits.** No renaming, no shadow-mapping; what comes out of LiteLLM is what lands in Tempo, what Grafana queries, what dashboards refer to.

**Add a small, scoped set of `bls.*` custom attributes** for things GenAI semconv does not cover. The current scope:

- `bls.cost_gbp_per_1k_input_tokens` — float; pence-precision (e.g., 0.00015 = £0.000 15 per 1k input tokens, current OpenAI `gpt-4o-mini` rate).
- `bls.cost_gbp_per_1k_output_tokens` — float; same units.
- `bls.cost_gbp_estimated` — float; pre-computed per-request cost: `(input_tokens / 1000) * cost_per_1k_input + (output_tokens / 1000) * cost_per_1k_output`. Stored on the span at emit time, denormalised so Grafana queries don't need a join.
- `bls.tier` — enum string: `economy` / `premium`. Mirrors the `Tier` enum from the hand-rolled reference impl ([`projects/04-llm-gateway-reference/app/models.py`](../../projects/04-llm-gateway-reference/app/models.py)) for narrative continuity, even though production LiteLLM routing does not use the same primitive.
- `bls.fallback_index` — int; 0 = primary provider succeeded, 1 = first fallback succeeded, etc. LiteLLM's `num_retries` chain populates this.

These attributes are **set by the gateway**, not by LiteLLM. The LiteLLM otel callback emits the GenAI attributes; the gateway's request handler reads the response, looks up the cost rate from a static table (or future Azure Cost Management lookup), computes the `bls.cost_gbp_*` values, and adds them to the same span via a [span event](https://opentelemetry.io/docs/specs/otel/trace/api/#add-events) or by setting attributes on the active span before it closes.

The actual emit code does not exist in this PR — it lands in Sequence 4. **This ADR declares the contract so the dashboard, queries, and downstream tooling can be built against the attribute names ahead of the code that produces them.**

---

## Rationale

### Why GenAI semconv verbatim

- **Cross-vendor portability.** Other LLM observability tooling — Langfuse, LangSmith, OpenLLMetry, Phoenix from Arize — consume the same GenAI attribute names. A Grafana dashboard built on `gen_ai.request.model` works against traces that came from a completely different gateway.
- **Upstream library does it for free.** LiteLLM v1.40+ emits GenAI attributes when the `otel` callback is active. We get correct provider name, model name, token counts, finish reasons, and temperature without writing a line of code.
- **Specification stability.** The GenAI work-group draft has been in active use since mid-2024 and is unlikely to break naming. If it does, that's an upstream LiteLLM problem, not ours.

### Why the `bls.*` prefix

- **Namespacing — these attributes don't belong in the GenAI semconv.** Cost is operator-specific (currency, billing model, FX conversion); tier is platform-specific (we made up the enum); fallback index is router-specific (different routers have different concepts of "fallback"). Trying to push them upstream would be wrong.
- **Discoverable in TraceQL.** A Tempo TraceQL query `{span.bls.cost_gbp_estimated > 0.05}` is obviously a platform-specific filter, not a typo of a standard attribute. The prefix signals "this is BLS-emitted; don't expect it on traces from other systems."

### Why precompute `bls.cost_gbp_estimated`

The denormalised cost lets a Grafana panel render "total spend by provider over the last hour" with a single Prometheus query (the otel-collector's `prometheusremotewrite` exporter pushes span attributes as Prometheus labels when configured; alternatively a Tempo metrics-generator computes the rollup). Without denormalisation, the panel needs a join between span attributes (which Prometheus doesn't speak) and a static cost-rate table (which lives nowhere queryable).

The trade-off: when OpenAI changes a model's price, our cost-per-1k constants drift until we update them. The cost table is in `bls-platform-private` (operator-private), so the public repo never carries pricing data; updates are a private-repo PR.

### Why partial Accepted

Setting the contract here, ahead of the emitter code, makes the dashboard panel placeholder (the "Cost per 1k tokens by provider" panel in [`k8s/workloads/monitoring/dashboards-gateway-tracing.yaml`](../../k8s/workloads/monitoring/dashboards-gateway-tracing.yaml)) meaningful — the dashboard layout is final; Sequence 4 swaps in the query string when the attributes are real. ADRs that wait for the implementation tend not to get written.

---

## Lineage — connection to the reference implementation

The hand-rolled reference at [`projects/04-llm-gateway-reference/`](../../projects/04-llm-gateway-reference/) ([ADR-011](ADR-011-llm-gateway-implementation-choice.md)) defined a `Tier` enum (`ECONOMY` / `PREMIUM`) and a `TIER_CHAINS` policy table in [`app/routing.py`](../../projects/04-llm-gateway-reference/app/routing.py). The verification artefacts under [`docs/verification/`](../../projects/04-llm-gateway-reference/docs/verification/) — the `openai-live-happy-path-2026-05-23.json` and `openai-live-forced-failover-2026-05-23.json` traces captured during ADR-011's "verified end-to-end" claim — are the spiritual ancestor of the `bls.tier` and `bls.fallback_index` attributes:

- The reference impl's `Router.route()` walked a tier chain and counted attempts; the production LiteLLM router does the same thing inside its `num_retries` chain. The semantic is identical; the implementation is now LiteLLM's.
- The reference's verification JSON files captured the request, the response, the latency, and which provider answered. Once `bls.cost_gbp_*` lands in production traces, the equivalent information will be queryable from Grafana directly — no per-experiment JSON capture, no ad-hoc `tests/live/` runs.

This continuity is intentional. The reference impl is preserved as a portfolio artefact precisely because the architectural reasoning (routing primitive + verification → production via a community library + observability) remains the design — only the surface that emits it changed.

---

## Consequences

- **The cost-per-1k-tokens dashboard panel** is a placeholder in this PR; it renders a "DEFERRED to Sequence 4" markdown block. The dashboard layout is final.
- **Sequence 4 owes the emitter.** Either a small Python module in the gateway that wraps the LiteLLM response handler and sets attributes on the active span, or a custom LiteLLM callback that does the same. Either way, ~30 lines and a unit test.
- **No code in this PR depends on `bls.*` attributes.** This ADR documents intent; nothing breaks if Sequence 4 redefines the attribute names. Doing so would be reluctant — every place that reads them (the dashboard, future Loki queries, future Cost Management integration) would have to follow.
- **Future Azure OpenAI / DeepSeek additions inherit the contract.** When LiteLLM adds those providers to `configmap-litellm.yaml`, the GenAI attributes flow automatically; the cost table grows by two entries; the dashboard adapts via the existing `{{model}}` legend template variable.

---

## Review trigger

Revisit if any of the following becomes true:

1. **OpenTelemetry GenAI semconv reaches stable** and renames a load-bearing attribute. Pin the relevant upstream version in `requirements.txt` and update the dashboard queries in lockstep.
2. **An operator-facing cost story emerges** (Azure Cost Management lookup, OpenAI Usage API polling, on-demand FX conversion). At that point `bls.cost_gbp_*` is no longer the right surface — the underlying source of truth becomes a separate exporter, and the span attribute becomes a denormalised cache of it.
3. **Multi-currency support is required.** Today the `_gbp_` suffix in the attribute name hardcodes one currency. If GBP stops being the only output, either rename the attribute family or add `bls.cost.currency` as a separate dimension.
4. **A different observability vendor is adopted** (per [ADR-013](ADR-013-otel-lgtm-adoption.md) review trigger #2). The `bls.*` prefix survives the move; only the dashboard renderer changes.
