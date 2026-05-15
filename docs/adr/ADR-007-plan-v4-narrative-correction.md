# ADR-007 — Plan-v4: narrative correction, six-week closure plan, £75–85k anchor

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-16 |
| **Project** | Cross-cutting — applies to the whole BLS portfolio |
| **Deciders** | BLS DevOps |

---

## Context

The BLS portfolio reached a state at which the engineering work materially outran the planning narrative around it. Plan-v3 (`BLS-master-plan-v3.md`, local working copy, gitignored under `files/`) was authored against a zero-state assumption: an eighteen-week build schedule beginning at Week 0 with no existing infrastructure. The portfolio is no longer at zero state.

Concretely, as of 2026-05-13 (BLS-STATUS.md audit baseline):

- **P1 Azure Landing Zone** — built; resource group, hub-and-spoke VNets, two NSGs, Log Analytics live in subscription `9a3b36fe-…-uksouth`; remote Terraform state in `stblstfstate001/tfstate`.
- **P2 k3s HA Platform** — built; Terraform via `bpg/proxmox 0.66.3`, Ansible `node-hardening` role, ADR-004 documented; cluster live with three+ nodes Running for five days.
- **P3 Multi-cluster GitOps** — partial; matrix ApplicationSet and ADR-005 in place; AKS torn down for cost discipline; dangling ArgoCD cluster registration plus three `*-bls-aks-demo` Applications showing Unknown.
- **P4 LLM Gateway** — built (with drift); FastAPI + LiteLLM + Redis live on k3s for several days; chart duplication open as WU-3.
- **P5 Observability + Security** — partial; kube-prometheus-stack, Grafana, Sealed-Secrets controller all Running via ArgoCD; ServiceMonitor scraping the gateway; sealed-secrets runbook published with controller-restart test passed.
- **P6 Platform Engineering** — empty by design.

Six ADRs (ADR-002 through ADR-006, plus the nested ADR-004 under P2), two runbooks, five release tags (`v0.2.0` through `v0.5.0`), and approximately seventy commits.

Three properties of Plan-v3 do not survive contact with this state:

1. **The build schedule presumes work that is already done.** A Week-1-of-18 framing where P1 is described as "to be built" is incoherent with a cluster that has been Running for five days. Subsequent weeks in Plan-v3 inherit the same dissonance.
2. **The salary anchor (£45–65k) is wrong for the work shipped.** The portfolio's surface area — hub-spoke cloud with deny-by-default NSG posture, HA k3s on bare metal with Ansible-driven hardening, matrix-generator GitOps, in-cluster API gateway with Prometheus instrumentation, Sealed-Secrets controller with a tested restart path and an honest runbook — is the surface area the £75–85k base / £550+/day outside-IR35 band hires against. Anchoring the planning narrative below that band sells the work.
3. **No bridge document.** Plan-v3 has no artefact that translates the engineering depth to the audience that hires. Recruiters, hiring managers, and technical leads landing on the repo cold get a README written before P4 shipped, a `docs/` directory with ADRs they have to discover by listing, and no scoped reading path. The engineering work is there; the framing is not.

Plan-v4 corrects all three. The cost of the correction is the planning artefact itself (this ADR, the operating doc at `docs/plan-v4/README.md`, the bridge document at `BLS-PLATFORM-ENGINEERING-GUIDE.md`, the concept→tool mapping at `docs/plan-v4/concept-tool-mapping.md`, and the diagram catalogue). The benefit is a portfolio that can be shipped to recruiters in four weeks instead of fourteen.

---

## Options Considered

### Option A — Extend Plan-v3 in place

Continue under Plan-v3's framing; treat the existing build as Weeks 0–8 retroactively; carry forward the £45–65k anchor; add a bridge document as a Plan-v3 Week 19 deliverable.

**Rejected.** The anchor is wrong and the build schedule is wrong; an extension does not fix either. Continuing the eighteen-week framing implies eight more weeks of construction before the portfolio is shippable, which is incorrect — the construction is largely done; the polish and positioning is what remains. Bolting a bridge document onto a misaligned framing produces a bridge document that inherits the misalignment.

---

### Option B — Split the monorepo into per-project repos and write a meta-repo narrative

Split into `terraform-bls-azure`, `homelab-k3s`, `gitops-bls`, `llm-gateway`, and an `bls-platform` meta-repo with the bridge document. Each repo carries its own README at full depth; the meta-repo carries the cross-cutting narrative.

**Rejected.** The split would consume one to two weeks of Plan-v4's six-week budget for purely structural gain. It loses the cross-project links that make the portfolio coherent: ADR-005 (matrix ApplicationSet, currently in `docs/adr/`) references `k8s/workloads/` and `03-aks-multicluster/`; ADR-006 (observability) references the LLM gateway's `/metrics` exposure. Splitting forces every cross-reference through a separate repo's URL, which degrades reading flow without improving any property the portfolio is judged on. The monorepo is also explicitly the structure a hiring audience expects when assessing platform-engineering breadth — one URL, one `git log`, one set of release tags.

---

### Option C — Pause Plan-v3, deliver only certifications until 2027

Stop the portfolio work; spend the same calendar time on AZ-104, CKA, AWS SAA, and similar certifications; resume engineering-narrative work afterwards.

**Rejected.** The £75–85k band rewards demonstrated platform capability over certifications. The portfolio already demonstrates the capability; certifications without the portfolio are weaker than the portfolio without additional certifications. AZ-104 is in progress in the background at its own pace and continues; it is not on the Plan-v4 critical path. A pause is the wrong response to "the engineering work is ahead of the planning narrative."

---

### Option D — Twelve-week extended Plan-v4 (more polish, more depth, more diagrams)

Run a twelve-week instead of six-week plan. Allow time for deeper per-project deep-dives, more diagrams, a more comprehensive bridge document, a Loki addition to the observability stack, and a multi-cloud extension under P6.

**Rejected.** A twelve-week plan does not produce a meaningfully better £75–85k portfolio than a six-week plan because the marginal bridge-content and diagram additions are subject to diminishing returns. Hiring decisions for this band do not turn on whether the portfolio has six diagrams or ten; they turn on whether the engineering depth is visible and the framing is honest. Six weeks is long enough to land both. Twelve weeks costs the architect six additional weeks of application throughput, during which the salary cost of unemployment (or staying at the current MSP role at a lower band) compounds.

---

### Option E — Six-week narrative + closure plan, monorepo retained *(selected)*

Six weeks of polish-and-position on the existing monorepo. The monorepo stays. The build schedule is replaced with a six-week shape: bootstrap and bridge-document skeleton (Week 1), bridge-document expansion plus core diagrams plus WU-3 closure (Week 2), remaining diagrams plus WU-4/WU-6/WU-9 plus CV/LinkedIn rewrite (Week 3), WU-5 decision plus scope-honesty pass plus capstone post plus first applications (Week 4), interview kata plus portfolio final pass plus scaled applications (Week 5), final rounds plus negotiation prep plus retrospective (Week 6).

Salary anchor £75–85k base / £550+/day outside IR35. Bridge document and diagram catalogue are first-class deliverables. Concept-first, tool-second framing applied uniformly.

---

## Decision

**Adopt Plan-v4: six-week narrative + closure plan, monorepo retained, salary anchor £75–85k, bridge document plus diagram catalogue, concept-first framing.**

The operational expression of this decision is in `docs/plan-v4/README.md`. The narrative expression is in `BLS-PLATFORM-ENGINEERING-GUIDE.md`. The reference table that keeps the framing consistent across artefacts is in `docs/plan-v4/concept-tool-mapping.md`.

Time horizon: six weeks. Success criterion: an offer pipeline at the £75–85k base or £550+/day outside-IR35 band by the end of Week 6. Reassessment trigger: if Week 6 closes with no offer pipeline, the plan exits with a written retrospective on what the six weeks produced, what worked, what did not, and which assumptions need revising before the next attempt. No mid-plan replacement.

---

## Rationale

**The work is done; what remains is the harness around it.** Plan-v3 framed itself as construction. Plan-v4 frames itself as polish-and-position. The reframing is the smallest change that aligns the planning narrative with the portfolio state.

**The £75–85k anchor reflects what the work demonstrates, not what feels safe to claim.** The two are different. The work demonstrates capability for the higher band; the lower anchor was set under uncertainty about the work's reception, not under analysis of the work itself.

**A bridge document is load-bearing for hiring conversion.** Engineering depth without a reading path is invisible to the audience that converts the depth into offers. Six ADRs and two runbooks distributed across `docs/adr/` and `docs/runbooks/` are findable to someone who already knows the repo; they are invisible to a hiring manager scanning for five minutes. The bridge document provides the reading path.

**Monorepo retention is a calibration decision, not a default.** The split (Option B) was considered with the alternatives that motivate it (each repo carrying its own first-class README, lower cognitive cost to a single-repo reader). The split was rejected on cost-of-restructure against benefit-of-clearer-headlines; that calculation could go the other way in a different portfolio, and the rejection is documented so the reasoning is portable.

**Six weeks is calibrated against application-pipeline throughput.** A four-week plan would leave Week 4–6 of the calendar without a written gate; a twelve-week plan would consume application weeks on diminishing-return polish. Six weeks lands "shippable to recruiters" at Week 4 Day 1 and reserves Weeks 5–6 for application throughput plus interview load.

**Concept-first framing is a hiring-signal multiplier.** The audience that pays the £75–85k band picks candidates who name the architectural concept before the tool that implements it. The concept→tool mapping table makes this discipline structural — every artefact links to the same table; framing drift across artefacts is mechanically caught.

---

## Consequences

### Positive

- **Faster path to offer pipeline.** Six weeks of polish-and-position instead of fourteen of construction-plus-polish.
- **Honest positioning at the £75–85k band.** The salary anchor matches the work; recruiter conversations open at the right level.
- **Scope is visible and bounded.** The plan states explicitly what it deliberately does not do (no new infrastructure, no AKS rebuild unless WU-5 chooses it, no certifications chase, no tech-stack expansion, no multi-repo split). Future scope-creep prompts have a written answer.
- **Bridge document removes the "scan for five minutes and bounce" failure mode.** A hiring manager's first five minutes now lands them on a concept-first reading path with linked depth.
- **Phase 2 work units retain their place.** WU-3, WU-4, WU-5, WU-6, WU-8, WU-9 fit into the Plan-v4 calendar at specific weeks rather than competing with narrative work for the daily 2–3-hour budget.

### Negative

- **Drift risk on per-project READMEs.** The bridge document and the concept→tool mapping are now load-bearing; per-project READMEs need to align with them. If a project README and the bridge document disagree on the framing of a decision, the contradiction is visible to a reader. Mitigation: every WU that touches a README also checks the framing against the bridge document and the mapping table, before the WU PR opens.
- **Bridge document becomes a single high-traffic edit point.** Any change to a portfolio claim (e.g., AKS coming back under WU-5) needs to land in `BLS-PLATFORM-ENGINEERING-GUIDE.md` for the claim to remain accurate. Mitigation: PR templates for WU PRs explicitly include a "bridge-document touch-points" checklist line.
- **The £75–85k anchor commits to a band; underperforming applications produce a sharper signal.** Aiming at the higher band means a stalled pipeline reads as "positioning is not landing" rather than as "could try a higher band." Mitigation: Week 6 retrospective explicitly assesses the anchor against the pipeline outcome. The anchor is not for life; it is for this attempt.
- **Plan-v3 historical artefacts remain reachable via `git log`.** The repository is not being rewritten. A reader walking the history will see commits from the Plan-v3 era with framings that Plan-v4 supersedes. This is an honesty surface, not a defect — but it is a surface that recruiters' technical scoping may probe.

---

## Alternatives Rejected

| Alternative | Reason |
|---|---|
| Extend Plan-v3 in place | Inherits the wrong build-schedule framing and the wrong salary anchor; bolting a bridge document onto misaligned framing does not fix the misalignment. |
| Split into multi-repo + meta-repo | Consumes 1–2 weeks of the six-week budget for structural gain; loses cross-project link coherence; degrades reading flow without improving any property the portfolio is judged on. |
| Pause portfolio for certifications | The £75–85k band weights demonstrated capability over certifications; the portfolio already demonstrates the capability; pausing trades a strength for a weaker substitute. |
| Twelve-week extended plan | Marginal polish-and-diagram additions are diminishing returns; six additional weeks of unemployment (or lower-band MSP cost) outweighs the marginal portfolio gain. |

---

## Implementation

### Week 1 deliverables (this PR)

| Artefact | Path | Role |
|---|---|---|
| Cleanup audit | `docs/plan-v4/01-cleanup-audit.md` | One-screen audit; no deletions; proposals only |
| Operating doc | `docs/plan-v4/README.md` | Replaces Plan-v3 build schedule |
| Concept→tool mapping | `docs/plan-v4/concept-tool-mapping.md` | Single global reference table |
| Bridge document skeleton | `BLS-PLATFORM-ENGINEERING-GUIDE.md` | Sections 1–3, 5, 6, 7 written; section 4 placeholder |
| Diagrams conventions | `docs/diagrams/README.md` | Tool choice, naming, source-and-output, catalogue |
| Diagram render workflow | `.github/workflows/render-diagrams.yml` | CI auto-renders Python `diagrams` library sources |
| System context diagram | `docs/diagrams/00-system-context.mmd` | Bridge document §1 |
| Scope boundary diagram | `docs/diagrams/07-scope-boundary.mmd` | Bridge document §6 |
| This ADR | `docs/adr/ADR-007-plan-v4-narrative-correction.md` | The decision record itself |

### Subsequent weeks

Weeks 2 through 6 are scoped in `docs/plan-v4/README.md` §2 (the 6-week shape). The orchestration prompts that drive each week live locally at `docs/plan-v4/orchestration-prompts.md` (gitignored — weekly source-of-truth).

### Review trigger

This ADR is reviewed at end of Week 6 against the success criterion (offer pipeline at the £75–85k base or £550+/day outside-IR35 band). If the criterion is met, the ADR's Status stays Accepted; the retrospective links from here. If not, the retrospective drives the next ADR (ADR-008) that supersedes this one.
