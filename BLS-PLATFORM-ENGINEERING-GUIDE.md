# Blue Layer Systems — Platform Engineering Guide

> Bridge document. Translates the engineering work in this monorepo into a reading path that goes from architectural intent to verifiable evidence in under ten minutes.
>
> Concept-first, tool-second throughout. Every tool named here is justified by the concept it implements; the depth of that justification lives in the ADRs and runbooks linked from each section.

---

## 1. The signal

The question this document answers: whether the work in this repository can stand up a production platform without supervision. The artefacts answer it directly — not through a CV's worth of verbs ("designed, implemented, architected"), but through code that runs, decisions that are recorded, and incidents that were documented as they happened.

The portfolio is six projects deep. Five are built and live; one is intentionally empty until the work behind it ships. The infrastructure spans a hub-spoke Azure landing zone backed by remote Terraform state with locking, a three-node highly-available Kubernetes cluster on bare-metal Proxmox with an Ansible-driven hardening baseline, a matrix-generator ApplicationSet driving GitOps reconciliation to multiple clusters from a single manifest, a FastAPI/LiteLLM gateway running live behind that GitOps layer with Prometheus metrics exposed, and a Sealed-Secrets controller plus kube-prometheus-stack observability with a tested restart path and a written backup runbook.

Six Architecture Decision Records cover the load-bearing choices: why a homelab cluster alongside the cloud, why Ansible rather than cloud-init, why Terraform plus Ansible rather than manual provisioning, why a matrix ApplicationSet, why a standalone Application for the observability stack. Two runbooks cover the operations that matter: sealed-secrets key backup with a controller-restart test, and a forensic handoff documenting a three-minute window when an ArgoCD Application CR disappeared from the cluster with no attributable mechanism (PHASE-2-HANDOFF.md, gitignored).

Five release tags mark milestones — `v0.2.0-k3s-cluster-live` through `v0.5.0-observability-live` — each pointing at a commit where the named capability genuinely worked. Around seventy commits of substantive work, all on conventional-commit headlines, all pre-commit-gated through Terraform formatting and validation, tflint, Checkov, detect-secrets, hadolint, and ruff (scoped to the Python under the LLM gateway test suite).

This document exists because the work is dense enough to be unreadable without a map. The map is concept-first: the property being implemented comes before the tool that implements it, so a reader following an unfamiliar tool can stay oriented on the architectural intent. The single global concept→tool reference table is at [`docs/plan-v4/concept-tool-mapping.md`](docs/plan-v4/concept-tool-mapping.md).

## 2. The working context

The work in this repository was built on personal time, on personal hardware, against personal cloud spend within a hard £60 cap on the Azure side. Everything in `git log` is the architect's own engineering decision, against a constraint set the architect set, using a tool stack the architect picked from alternatives.

The day-job working surface is a UK Managed Services Provider. An MSP operator works across multiple clients' infrastructure, in environments not of their own choosing, against constraints that vary by week. That surface produces a different engineering reflex than a single-product platform team. The reflex visible in this repository — defensive backups for the master key before any operation that could destroy the controller's namespace, preflight scripts that snapshot state before destructive actions, "surface, never automate" as the rule for destructive operations — is that reflex applied to a portfolio rather than a single client.

What this repository is not: a sequence of tutorial completions, a Cloud Resume Challenge variant, a Terraform learn-by-doing repository, a kubernetes-the-hard-way replay. The tutorials those names describe were not unhelpful inputs to the path that produced this work, but the work itself stands on its own — every project solves a problem the architect chose, against constraints the architect set.

## 3. The portfolio at a glance

Five built projects and one intentionally empty placeholder. Each project's README has the technical depth; this section reads top-down so the structure is visible in one sitting.

### P1 — Cloud foundation (Azure landing zone)

**Concept:** declarative state with reconciliation, tagging discipline at the policy layer, remote Terraform state with locking, hub-spoke network topology with security boundaries that deny by default.

**Implementation:** Terraform-defined Azure resource group, hub and spoke virtual networks with peering, two network security groups governing east-west and north-south traffic, Log Analytics workspace for centralised diagnostics, Azure Policy assignments enforcing tag presence and geographic restriction. State held in an Azure Storage account (name redacted) with blob-locking. Live in a UK South Azure subscription (subscription ID intentionally not printed here; available on request).

**What this demonstrates:** the candidate can stand up a compliant cloud foundation from first principles, including the parts that are easy to skip (remote state, locking, deny-by-default NSG posture, tag-presence policies). The total Azure spend is sub-£0.01/month at rest — discipline visible on the cost line.

**Evidence:** [`projects/01-landing-zone/`](projects/01-landing-zone/) for the Terraform, [`docs/adr/`](docs/adr/) for the related decisions, the `v0.4.0-multicluster-gitops` and later tags for the integration points.

### P2 — Private compute platform (k3s on Proxmox, hardened via Ansible)

**Concept:** container orchestration with high availability on commodity hardware, configuration management as code, defence-in-depth at the bootstrap layer.

**Implementation:** Three control-plane nodes and two workers, all provisioned via Terraform against the Proxmox API and converged via an Ansible `node-hardening` role. The role applies auditd, fail2ban, hardened SSH, sysctl tuning, ufw, and ntp synchronisation idempotently — a re-run on a converged node makes no changes; a re-run on a drifted node corrects the drift. Control-plane HA via kube-vip with an automatic VIP failover. ADR-002 records the homelab-alongside-cloud decision; ADR-003 records the Ansible-over-cloud-init decision; ADR-004 records the provisioning approach.

**What this demonstrates:** the candidate can operate Kubernetes from etcd outward — not just consume a managed control plane. Real failure modes have been encountered and recovered (DNS resolution traced to a misconfigured firewall NAT rule with tcpdump, etcd corruption after a mistyped join command resolved via full node reinstall and kube-vip recreation). The hardening role is shippable to a real environment because it has already converged five times on real hardware.

**Evidence:** [`02-k3s-platform/`](02-k3s-platform/), [`ansible/roles/node-hardening/`](ansible/roles/node-hardening/), [`02-k3s-platform/docs/adr/ADR-004-proxmox-provisioning-approach.md`](02-k3s-platform/docs/adr/ADR-004-proxmox-provisioning-approach.md), [`docs/what-broke.md`](docs/what-broke.md) for the early incident log.

### P3 — Multi-cluster delivery (matrix ApplicationSet)

**Concept:** GitOps as the deployment boundary, declarative fleet management with automatic discovery of both workloads and clusters.

**Implementation:** A single ApplicationSet using a matrix generator combining a git-directory generator (discovers workload folders under `k8s/workloads/`) and a clusters generator (discovers all clusters registered with ArgoCD). Result: one Application per `(workload, cluster)` combination, scaling N×M from one manifest. Three workloads currently in the matrix: `podinfo`, `llm-gateway`, `monitoring`. Cluster registrations were in-cluster (k3s) plus a now-torn-down AKS demo cluster — ADR-005 records the pattern; the AKS teardown is a deliberate cost-discipline choice with a pending decision (WU-5) on rebuild vs cleanup.

**What this demonstrates:** the candidate understands GitOps as a discipline rather than a tool — single source of truth, declarative reconciliation, drift detection, automated self-heal. The matrix ApplicationSet is the architectural choice that lets a real fleet scale from one manifest; the candidate evaluated three options (individual Application manifests, ApplicationSet-per-workload, matrix generator) and recorded the rejection reasons for each.

**Evidence:** [`03-aks-multicluster/`](03-aks-multicluster/), [`k8s/apps/app-of-apps.yaml`](k8s/apps/), [`docs/adr/ADR-005-applicationset-matrix-pattern.md`](docs/adr/ADR-005-applicationset-matrix-pattern.md), screenshots at [`docs/screenshots/`](docs/screenshots/).

### P4 — Workload (LLM gateway, FastAPI + LiteLLM + Redis)

**Concept:** API gateway pattern for backend abstraction — a single endpoint normalises calls across heterogeneous LLM providers, with a typed request layer, dependency injection, and a `/metrics` endpoint observable by the platform's pull-based scraper.

**Implementation:** Python FastAPI service wrapping LiteLLM (the OpenAI-compatible adapter to 100+ LLM providers), Redis for caching, packaged as a Helm chart deployed via the matrix ApplicationSet. Image build wired through a GitHub Actions workflow (`build-gateway.yaml`) producing a versioned container image consumed by the chart. The service has been live on the k3s cluster for several days at the time of this writing.

**Hardening pass (2026-05-24):** runtime credentials — Bearer API keys, LiteLLM master key, Ollama endpoint address — live in a Bitnami `SealedSecret` scoped `--strict` to namespace and name. No plaintext credential or homelab-internal address is committed in git (WU-4 closed). An opt-in pytest live suite under `k8s/workloads/llm-gateway/tests/live/` exercises the real OpenAI path through the LiteLLM SDK — the same library the deployed proxy runs — and commits sanitised JSON evidence under `docs/verification/` as proof the path works. The auth contract was tightened in the same pass: 401 missing-token and 403 invalid-key now return typed JSON envelopes through a `JSONResponse`-from-middleware fix that replaced a `HTTPException`-raise-from-`BaseHTTPMiddleware` pattern Starlette silently coerces to 500. Three of the five "Known gaps" listed in the chart README are now closed; the remaining two are explicitly P5-scope (TLS via cert-manager) or properly deferred (image digest pin, sustained-load memory profile).

**What this demonstrates:** the candidate can ship a real application onto the platform they built, with the observability hooks wired through (metrics exposed, ServiceMonitor scraping, `/metrics` reachable from the Prometheus instance in the `monitoring` namespace) and the operational discipline applied beyond the happy path — secrets encrypted in git, the gateway's behaviour verified against a real upstream and committed as evidence, the security contract surveyed and tightened in a follow-up pass.

**Evidence:** [`k8s/workloads/llm-gateway/`](k8s/workloads/llm-gateway/) (canonical chart), [`.github/workflows/build-gateway.yaml`](.github/workflows/build-gateway.yaml), [`k8s/workloads/llm-gateway/docs/verification/`](k8s/workloads/llm-gateway/docs/verification/) (live OpenAI evidence), [`k8s/workloads/llm-gateway/SECURITY.md`](k8s/workloads/llm-gateway/SECURITY.md) (SealedSecret workflow, cost cap, key rotation).

### P5 — Observability + security

**Concept:** pull-based metrics with label-based aggregation, encrypted secrets in Git decrypted only inside the cluster, defensive operations posture for the highest-blast-radius secret on the platform.

**Implementation:** kube-prometheus-stack deployed as a standalone ArgoCD Application using ArgoCD multi-source — upstream chart pinned to a version, custom values held in Git as a separately reviewable file (ADR-006). Prometheus configured with `serviceMonitorSelector: {}` so it watches ServiceMonitors across all namespaces; k3s control-plane components disabled in values to avoid ScrapeError noise. Bitnami Sealed-Secrets controller pinned into its own namespace (`sealed-secrets`, not `kube-system`) with a wider-selector backup procedure capturing all retained keys (active and rotated-out) and a controller-restart test proving in-cluster key reload works without losing decryption capability.

The Sealed-Secrets runbook ([`docs/runbooks/sealed-secrets-controller.md`](docs/runbooks/sealed-secrets-controller.md)) is itself a load-bearing artefact — it documents not only the happy path but the known gap (full restore-from-backup against a fresh cluster has not been routinely executed; the runbook says so explicitly).

**What this demonstrates:** the candidate treats secrets and observability as load-bearing infrastructure with operational discipline, not as features to be ticked off. The runbook is honest about what is tested and what is not. Defensive backups precede destructive operations.

**Evidence:** [`05-observability-security/`](05-observability-security/), [`k8s/apps/monitoring.yaml`](k8s/apps/), [`k8s/apps/sealed-secrets.yaml`](k8s/apps/), [`docs/adr/ADR-006-observability-gitops.md`](docs/adr/ADR-006-observability-gitops.md), [`docs/runbooks/sealed-secrets-controller.md`](docs/runbooks/sealed-secrets-controller.md).

### P6 — Platform engineering (intentionally empty)

**Concept:** policy as code, secondary cloud presence, public-facing surface — three workstreams that belong on the roadmap but have not shipped enough to claim.

**Status:** empty. P6's scope (OPA/Gatekeeper policy as code, Azure OpenAI integration, GCP Terraform parity, BLS site widget) is named in the project register but no code lives under it yet. Listed here for transparency only: an honest portfolio reports the empty rows alongside the built ones.

---

## 4. Technical depth — per-project deep dives

> **Architect-fill section.** Each P1-P5 subsection below has its concept-and-tool framing and its reading-path links already populated (Plan-v4 Week 2). The two rows marked `[Architect fills in — see ADR-NNN, diagram NN]` are deliberately left for the architect's voice. Fill in 2-3 sentences in your own words: the load-bearing decision, and the trade-off you accepted. Do not let those rows be ghost-written; the rest of the document carries no first-person claim that those two rows do not earn.

### 4.1 Azure landing zone — depth view (P1)

- **Architectural concept demonstrated:** Declarative state with reconciliation. Describe the desired Azure landing zone in code, let Terraform converge cloud reality to match.
- **Tool implementing the concept:** Terraform (Azure provider) with remote state in an Azure Storage account.
- **Where to read deeper:**
  - Topology diagram: [`docs/diagrams/02-landing-zone-topology.py`](docs/diagrams/02-landing-zone-topology.py) (rendered to `.png` by CI)
  - System-wide container view: [`docs/diagrams/01-container-view.py`](docs/diagrams/01-container-view.py)
  - Concept-to-tool row: [`docs/plan-v4/concept-tool-mapping.md`](docs/plan-v4/concept-tool-mapping.md) (rows for *Declarative state with reconciliation*, *Tagging discipline + spend control*, *Remote Terraform state with locking*)
  - Project README: [`projects/01-landing-zone/README.md`](projects/01-landing-zone/README.md)
- **Load-bearing decision:** *[Architect fills in — name the load-bearing call. Candidates: hub-spoke over flat VNet at this scale, NSG strategy, the remote-state hardening posture, the tag-policy enforcement model. Pick one, 2-3 sentences.]*
- **What I deliberately didn't build:** *[Architect fills in — name what was in scope and consciously cut. Candidates: Azure Firewall in front of the hub, Bastion, private endpoints across the data plane, Front Door. Pick one, 2-3 sentences with the trade-off accepted.]*

### 4.2 k3s cluster — depth view (P2)

- **Architectural concept demonstrated:** Container orchestration with high availability on commodity hardware, combined with configuration management as code for every node.
- **Tool implementing the concept:** k3s with kube-vip for control-plane HA; Ansible `node-hardening` role applied to every node.
- **Where to read deeper:**
  - Cluster topology diagram: [`docs/diagrams/03-k3s-ha-cluster.py`](docs/diagrams/03-k3s-ha-cluster.py)
  - ADRs: [`ADR-002 — homelab over cloud-only`](docs/adr/ADR-002-homelab-over-cloud-only.md), [`ADR-003 — Ansible over cloud-init`](docs/adr/ADR-003-ansible-over-cloud-init.md)
  - Concept-to-tool rows: [`docs/plan-v4/concept-tool-mapping.md`](docs/plan-v4/concept-tool-mapping.md) (*Container orchestration with HA on commodity hardware*, *Configuration management as code*, *Defence-in-depth on bootstrap nodes*)
  - Ansible role: [`ansible/roles/node-hardening/`](ansible/roles/node-hardening/)
- **Load-bearing decision:** *[Architect fills in — see ADR-002 and ADR-003. Candidates: HA via three CP nodes rather than single-CP "simpler" homelab, etcd-embedded over external, hardening as a re-runnable Ansible role rather than a one-shot bootstrap script. 2-3 sentences.]*
- **What I deliberately didn't build:** *[Architect fills in — Candidates: managed AKS (would have shipped faster but lost the etcd-outward learning surface), Talos / k0s instead of k3s, GitOps-managed Ansible runs. 2-3 sentences with the trade-off accepted.]*

### 4.3 Multi-cluster GitOps — depth view (P3)

- **Architectural concept demonstrated:** Declarative fleet management — one ApplicationSet manifest generates `N × M` Applications across clusters and workloads from a single spec.
- **Tool implementing the concept:** ArgoCD ApplicationSet with the matrix generator (Git-directory × cluster-list).
- **Where to read deeper:**
  - Reconciliation flow diagram: [`docs/diagrams/04-multi-cluster-gitops.mmd`](docs/diagrams/04-multi-cluster-gitops.mmd)
  - ADR: [`ADR-005 — ApplicationSet matrix pattern`](docs/adr/ADR-005-applicationset-matrix-pattern.md)
  - Concept-to-tool rows: [`docs/plan-v4/concept-tool-mapping.md`](docs/plan-v4/concept-tool-mapping.md) (*GitOps as the deployment boundary*, *Declarative fleet management*)
  - Project README: [`03-aks-multicluster/README.md`](03-aks-multicluster/README.md)
  - Forensic case study: PHASE-2-HANDOFF.md WU-2 (local-only) — worked example of GitOps incident response.
- **Load-bearing decision:** *[Architect fills in — see ADR-005, diagram 04. Candidates: matrix generator over list/Git alone (the N×M scaling argument), uniform sync policy across child apps, `selfHeal=true` despite the operational implications. 2-3 sentences.]*
- **What I deliberately didn't build:** *[Architect fills in — Candidates: Flux (different CRD layout for the same model), ArgoCD ApplicationSet plugin generators, app-of-apps over ApplicationSet. 2-3 sentences with the trade-off.]*

### 4.4 LLM gateway — depth view (P4)

- **Architectural concept demonstrated:** API gateway pattern for backend abstraction — a single OpenAI-compatible endpoint normalises calls across heterogeneous LLM providers (Ollama on Proxmox, Azure OpenAI, DeepSeek).
- **Tool implementing the concept:** FastAPI at the edge (auth, request validation) in front of LiteLLM in proxy mode (provider routing, retries, cache) in front of the backends. Redis for exact-match response caching.
- **Where to read deeper:**
  - Request-path diagram: [`docs/diagrams/05-llm-gateway-request-path.mmd`](docs/diagrams/05-llm-gateway-request-path.mmd)
  - ADR: [`ADR-008 — LLM gateway design`](docs/adr/ADR-008-llm-gateway-design.md)
  - Concept-to-tool row: [`docs/plan-v4/concept-tool-mapping.md`](docs/plan-v4/concept-tool-mapping.md) (*API gateway pattern for backend abstraction*)
  - Project README: [`k8s/workloads/llm-gateway/README.md`](k8s/workloads/llm-gateway/README.md) — operator-facing runbook including the six-item "things to know" operational history.
- **Load-bearing decision:** Auth at the FastAPI edge rather than in LiteLLM. LiteLLM's authentication model is built around spend-tracking with a PostgreSQL dependency this stack does not have; placing auth at the FastAPI edge means the security boundary is a fifteen-line middleware in a single file (`app/middleware/auth.py`) that can be diff-reviewed and carries no database lifecycle to manage. The trade-off accepted is two in-cluster hops per request — caller → FastAPI → LiteLLM → backend, ~5–10 ms of in-cluster networking — in exchange for the ability to swap LiteLLM for any other multi-provider router without rewriting authentication, and the ability to add semantic caching, rate limiting, or response post-processing as future FastAPI middleware without changing the routing contract.
- **What I deliberately didn't build:** Semantic caching. Redis is wired in from day one and Helm-managed alongside the gateway, but only as an exact-match cache; semantic similarity requires an embeddings model and a vector index that the homelab does not currently host. The topology supports both — adding semantic caching is a configuration change in `configmap-litellm.yaml`, not an architectural one. Streaming responses and request-shape rate limiting are deferred for the same reason: the design accommodates them but no caller's needs justify the operational cost today.

### 4.5 Observability + security — depth view (P5)

- **Architectural concept demonstrated:** Pull-based metrics with label-based aggregation, plus encrypted secrets in Git decrypted only in-cluster.
- **Tool implementing the concept:** Prometheus (via kube-prometheus-stack) for metrics; Sealed Secrets (Bitnami) for secret material at rest in Git. Multi-source ArgoCD Applications pin chart versions independently from values.
- **Where to read deeper:**
  - Observability data-flow diagram: [`docs/diagrams/06-observability-data-flow.py`](docs/diagrams/06-observability-data-flow.py) (renders to [`06-observability-data-flow.png`](docs/diagrams/06-observability-data-flow.png))
  - ADRs: [`ADR-006 — observability GitOps`](docs/adr/ADR-006-observability-gitops.md), [`ADR-009 — NetworkPolicy scope`](docs/adr/ADR-009-networkpolicy-scope.md)
  - Concept-to-tool rows: [`docs/plan-v4/concept-tool-mapping.md`](docs/plan-v4/concept-tool-mapping.md) (*Pull-based metrics*, *Encrypted secrets in Git*, *Multi-source ArgoCD Application*)
  - Runbook: [`docs/runbooks/sealed-secrets-controller.md`](docs/runbooks/sealed-secrets-controller.md)
  - Project README: [`05-observability-security/README.md`](05-observability-security/README.md)
- **Load-bearing decision:** Multi-source ArgoCD Application over an umbrella Helm chart wrapping `kube-prometheus-stack`. Pinning chart version and values in separate sources means a chart upgrade is a one-line diff in `monitoring.yaml` and a values change is a separately-reviewable file edit — neither requires touching the other, neither commits a binary tarball to Git. The trade-off accepted is a hard floor of ArgoCD 2.6 for multi-source support and an explicit `ServerSideApply=true` to clear the 262144-byte CRD annotation limit kube-prometheus-stack triggers on every install.
- **What I deliberately didn't build:** Centralised log aggregation (Loki). The homelab cluster has no high-availability persistent storage beyond what kube-prometheus-stack itself consumes; a real Loki deployment with retention policy and ingester replication would double the cluster's stateful-storage footprint for a use case the portfolio does not exercise. The metrics side ships with kube-prometheus-stack because every workload already emits Prometheus metrics; the logs side does not, because no workload here has more than a handful of pods to tail.

---

## 5. Engineering discipline

The decisions are recorded. The commits are conventional. The hooks gate the commits. The runbooks are honest. These are not slogans — every claim drills into a specific artefact in this repository.

**Architecture Decision Records.** Six ADRs in [`docs/adr/`](docs/adr/) plus one nested under P2. Each ADR follows the same template: Context, Options Considered (with reasons for rejection), Decision, Rationale, Consequences (both positive and negative — the negative section is non-optional), Alternatives Rejected (with reasons), Implementation. ADR-006 spends an entire paragraph explaining why `ServerSideApply=true` is non-negotiable for kube-prometheus-stack — that level of specificity is the standard.

**Conventional commits.** Every commit subject is typed (`feat`, `fix`, `docs`, `refactor`, `chore`, `test`, `ci`), imperative-mood, and scoped where helpful. Commit bodies do the explanation work the subject cannot. Examples in `git log`: `fix(wu-2): correct preflight sync-state logic` carries a body that names the exact logic bug, the symptom that surfaced it, and the side effect of the fix on step 3's gate.

**Pre-commit hooks.** [`.pre-commit-config.yaml`](.pre-commit-config.yaml) runs trailing-whitespace, end-of-file fixer, YAML syntax check, large-file guard, merge-conflict guard, private-key detector, `detect-secrets` against the committed baseline, Terraform formatting and validation, tflint, Checkov, and hadolint. The hooks pass before the commit lands. The detect-secrets baseline self-cleans on each commit and is staged into the same commit that touches it — workflow friction documented in BLS-STATUS.md so future operators do not rediscover it.

**Runbooks.** Two runbooks at the time of writing: [`docs/runbooks/sealed-secrets-controller.md`](docs/runbooks/sealed-secrets-controller.md) (master-key backup, controller-restart test, known gaps in test coverage stated explicitly) and the operational handoff in PHASE-2-HANDOFF.md (gitignored, session-continuity-only). The sealed-secrets runbook spends multiple paragraphs on what `shred -u` does and does not protect against — that paragraph is the discipline being demonstrated.

**Incident response.** [`docs/what-broke.md`](docs/what-broke.md) records real incidents with root cause and lesson. The WU-2 forensic note in PHASE-2-HANDOFF.md (gitignored — local-only) is the larger example: a three-minute window where an ArgoCD Application CR disappeared, eight ruled-out mechanisms with evidence, three remaining candidates ranked by probability, an explicit statement of why the investigation stopped converging (no K8s API audit log enabled — WU-8). This is what platform engineers do when something breaks.

## 6. What this portfolio deliberately doesn't claim

A portfolio is as much about what is not in it as what is. The following are choices, not gaps:

**No multi-tenant production workload.** The cluster runs the architect's own workloads. There is no claim of multi-tenant operations, RBAC partitioning across customers, or quota-and-noisy-neighbour mitigation at scale. Multi-tenant operations are not in scope; that surface would be the next expansion.

**No claim of AWS or GCP production experience inside this repository.** The Terraform stack here is Azure-first; GCP parity is named on the P6 roadmap and has not shipped. AWS exposure exists outside this repository in the architect's MSP work but is not demonstrated here. AWS production depth is not a property this repository proves.

**No claim of platform-team-of-N operations.** This is a one-architect portfolio. What this repository demonstrates is the architect operating across multiple environments and projects against a constraint set they set — not coordinating across a team of platform engineers. Cross-team coordination is not a signal this portfolio surfaces.

**No claim that AKS is currently running.** AKS was provisioned for the P3 multi-cluster demonstration and torn down to preserve the £60 Azure spend cap. The dangling registrations in ArgoCD are tracked transparently (PHASE-2-HANDOFF.md WU-5 — local-only). A rebuild decision is on the Plan-v4 calendar for Week 4; until then, the portfolio's AKS claim is "built once, evidence captured, torn down for cost discipline."

**No claim that every WU is closed.** The Phase 2 hardening sprint has open work units (P5 README, audit logging on the cluster API server, AKS rebuild). Chart deduplication (WU-3) closed in Week 2; SealedSecret conversion for the LLM gateway plus removal of the homelab Ollama address from values.yaml (WU-4) closed on 2026-05-24. The remaining work is in flight; the handoff doc is honest about it. A closing portfolio that pretends every loose end is tied is a portfolio that cannot be trusted on the tied ones.

**No claim of formal SRE on-call.** The recovery work in this repository is real but not 24/7-on-call work. Proven on-call rotation depth is MSP context outside this repository, not a property of the platform here.

## 7. How to verify

This portfolio is verifiable end-to-end. Every claim above drills down through these paths:

**Repository.** [`github.com/CalmAfterReboot/BLS-platform`](https://github.com/CalmAfterReboot/BLS-platform) — full source, all infrastructure-as-code, all deployment manifests, all CI workflows. Read access is public; the commit history is the audit trail.

**Architecture Decision Records.** [`docs/adr/`](docs/adr/) — all decisions of substance, rationale and rejected alternatives included. Start with [`ADR-005-applicationset-matrix-pattern.md`](docs/adr/ADR-005-applicationset-matrix-pattern.md) for the multi-cluster delivery thinking and [`ADR-006-observability-gitops.md`](docs/adr/ADR-006-observability-gitops.md) for the observability deployment choices.

**Runbooks.** [`docs/runbooks/sealed-secrets-controller.md`](docs/runbooks/sealed-secrets-controller.md) — the operational discipline applied to the highest-blast-radius secret on the cluster.

**Release tags.** `v0.2.0-k3s-cluster-live`, `v0.3.0-argocd-live`, `v0.4.0-multicluster-gitops`, `v0.4.0-llm-gateway-live`, `v0.5.0-observability-live` — each tag points at a commit where the named capability worked. Walking `git log` between tags shows the path.

**Incident artefacts.** [`docs/what-broke.md`](docs/what-broke.md) for the early Ansible idempotency failures; the WU-2 forensic note in PHASE-2-HANDOFF.md (gitignored — local-only, surface on request) for a worked example of a platform incident with unattributed root cause.

**Live cluster.** The k3s cluster, ArgoCD reconciler, and the LLM gateway have been running through the construction of this document. Specific verification commands (Prometheus target list, ArgoCD Application sync status, gateway `/metrics` reachability) are reproduced in the per-project READMEs and in the relevant ADR's Verification section.

**Contact.** Through normal channels. Quick to respond to technical scoping questions; prefers a thirty-minute technical conversation before deeper engagement. Gitignored handoff documents are shared on request.

---

*This document is Plan-v4 Week 1 output. Sections 1–3, 5, 6, and 7 are fully written. Section 4 will fill across Plan-v4 Weeks 2 and 3 as the per-project diagrams render and the architect ports the depth content from each project's existing README. The operating doc is at [`docs/plan-v4/README.md`](docs/plan-v4/README.md); the decision record is at [`docs/adr/ADR-007-plan-v4-narrative-correction.md`](docs/adr/ADR-007-plan-v4-narrative-correction.md).*
