# ADR-001 — LiteLLM vs Roll-Your-Own

| Field | Value |
|---|---|
| **Status** | Accepted — supersedes this codebase |
| **Date** | 2026-05-25 |
| **Project** | bls-ai-gateway (this repository — reference implementation) |

---

This ADR is the in-project mirror of the platform-level decision.

**Decision:** the production LLM gateway adopts LiteLLM in proxy mode rather than porting the from-scratch routing primitive (Provider protocol, tier-chain policy, sequential failover, error translation) built in this codebase. This codebase is preserved as a frozen reference implementation; no further development is planned.

The full rationale, alternatives considered, consequences, and review trigger live in the canonical ADR in the platform monorepo:

- **[`docs/adr/ADR-011-llm-gateway-implementation-choice.md`](../../../../docs/adr/ADR-011-llm-gateway-implementation-choice.md)** *(when read from inside BLS-DevOps; from a clone of just `bls-ai-gateway`, see [github.com/CalmAfterReboot/BLS-platform → docs/adr/ADR-011-…](https://github.com/CalmAfterReboot/BLS-platform/blob/main/docs/adr/ADR-011-llm-gateway-implementation-choice.md))*

This mirror exists so that anyone landing on the reference repo by itself (without the platform monorepo context) can find the decision that froze it. Edits to the canonical ADR-011 do **not** propagate here automatically — if the decision is ever revisited, both files must be updated together.
