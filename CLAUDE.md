# BLS-DevOps — Claude Code Context

> Auto-loaded every session. Full playbook: docs/playbook/platform-engineering-playbook.md

## Who I am
Mihai Gabriel Ferencz — TechOps/MSP Engineer, Global4 Communications, Carlisle UK.
GitHub: CalmAfterReboot. Brand: Blue Layer Systems (bluelayersystems.com).
Target: £45–65k Cloud/DevOps/Platform/SRE UK remote/hybrid.
Homelab: Proxmox 128GB RAM / 6-core Xeon / 4TB. DevVM: Ubuntu 24.04 LTS.
Proxmox Ollama endpoint: http://10.212.46.5:11434

Three tracks:
1. Career exit via BLS 6-project portfolio
2. BLS portfolio — public on GitHub, under £60 total Azure spend
3. MSP SaaS platform — multi-tenant ops intelligence, bootstrap path

## BLS Portfolio State

| Project | What | Status |
|---|---|---|
| P1 | Azure Landing Zone — Terraform, hub-spoke, NSGs, Log Analytics, GitHub Actions | Done |
| P2 | k3s HA Platform — 3-node, Longhorn, ArgoCD GitOps | Done |
| P3 | Multi-cluster GitOps — ArgoCD ApplicationSets, Helm | Done |
| P4 | LLM Gateway — FastAPI + LiteLLM + Redis, Helm, ArgoCD, Ollama on Proxmox | Done |
| P5 | Observability + Security — kube-prometheus-stack, Grafana, Sealed Secrets, NetworkPolicy | In Progress |
| P6 | Platform Engineering — OPA/Gatekeeper, Azure OpenAI, GCP Terraform, BLS site widget live | In Progress |

Repo: ~/Desktop/BLS-DevOps/ on DevVM.

## MSP SaaS Platform
Not a portfolio project — a product. Load docs/playbook/platform-architecture.md for platform sessions.
Stack: FastAPI, Keycloak, Postgres+RLS, TimescaleDB, Redis, LiteLLM, React/Vite/Shadcn, k3s, Cloudflare, Go agent.
Stages: 0 Foundation → 1 Identity/Auth → 2 M365 Connector → 3 AI Triage → 4 Agent → 5 Solutions Advisor → 6 Connectors → 7 Commercial
Pricing: £99 / £299 / £599 / £999/month. 3,500+ UK MSPs in market.
NEVER test on Global4 client tenants. My lab only.

## Engineering Standards
- Everything in Git. Conventional commits. PRs only, no direct main commits.
- Pre-commit hooks: terraform fmt, validate, tflint, Checkov, detect-secrets.
- Pipeline gates: SAST (Semgrep), Trivy, unit + integration + E2E tests.
- Idempotent by default. No destructive ops without explicit confirmation.
- No hardcoded secrets. No credentials in Git. Ever.
- Every architectural decision = ADR in docs/adr/.
- Mandatory tagging on every Azure resource. £60 hard cap.
- Tenant isolation: adversarial RLS tests on every PR touching tenant data.

## Instructions for Claude Code
1. Skip openers. Verdict → rationale → trade-offs → failure modes → implementation.
2. Stress-test designs. Identify blast radius. Surface risks not yet considered.
3. If I am wrong or wasting time — say so immediately and say why.
4. Production context assumed. Peer-level depth. No 101 unless asked.
5. Idempotent scripts only. Risks before commands. No destructive ops without confirmation.
6. Every deliverable is public-repo quality — treat as code review material.
7. For platform work: I am the customer. Challenge architecture and build sequence.
8. Bootstrap-first. Never introduce VC framing unless I raise it.
9. NEVER test platform features on Global4 client tenants.
10. Tenant isolation is highest blast-radius failure. Adversarial tests non-negotiable.
