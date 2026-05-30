# BLS-DevOps — Claude Code Context

> Auto-loaded every session. Operator profile: docs/playbook/about-me.md

## Portfolio State

| Project | What | Status |
|---|---|---|
| P1 | Azure Landing Zone — Terraform, hub-spoke, NSGs, Log Analytics, GitHub Actions | Done |
| P2 | k3s HA Platform — 3-node, Longhorn, ArgoCD GitOps | Done |
| P3 | Multi-cluster GitOps — ArgoCD ApplicationSets, Helm | Done |
| P4 | LLM Gateway — FastAPI + LiteLLM + Redis, Helm, ArgoCD, Ollama on Proxmox | Done |
| P5 | Observability + Security — kube-prometheus-stack, Grafana, Sealed Secrets, NetworkPolicy, workload PrometheusRules | Done |
| P6 | Platform Engineering — OPA/Gatekeeper, Azure OpenAI, GCP Terraform, BLS site widget | Not started — consolidation landing now |

## Engineering Standards
- Everything in Git. Conventional commits. PRs only, no direct main commits.
- Pre-commit hooks: terraform fmt, validate, tflint, Checkov, detect-secrets.
- Pipeline gates: Semgrep SAST, Trivy, unit + integration + E2E tests.
- Idempotent by default. No destructive ops without explicit confirmation.
- No hardcoded secrets. No credentials in Git. Ever.
- Every architectural decision = ADR in docs/adr/.
- Mandatory tagging on every Azure resource.
- Tenant isolation: adversarial RLS tests on every PR touching tenant data.

## Instructions for Claude Code
1. Skip openers. Verdict first, then rationale, trade-offs, failure modes, implementation.
2. Stress-test designs. Identify blast radius. Surface risks not yet considered.
3. If something is wrong or inefficient — say so immediately and say why.
4. Production context assumed. Peer-level depth. No 101 unless asked.
5. Idempotent scripts only. Risks before commands. No destructive ops without confirmation.
6. Every deliverable is public-repo quality — treat as code review material.
7. Bootstrap-first on platform work. Challenge architecture and build sequence.
8. Tenant isolation is highest blast-radius failure. Adversarial tests non-negotiable.
