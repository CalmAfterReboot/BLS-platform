# Plan-v4 — Operating doc

> Replaces the build schedule in `BLS-master-plan-v3.md`. Treat this file as the single source of truth for what gets built in the next six weeks and what does not.

The substantive engineering is done. P1–P5 are built. The work that remains is narrative: making the portfolio legible to the audience that hires for permanent UK platform engineer roles at the £75–85k base salary band. Plan-v4 is the six-week harness that closes that gap.

## 1. North Star

**Interview-ready portfolio in 6 weeks at the £75–85k base band (permanent, UK remote-first).**

"Interview-ready" has a hard definition: a hiring manager landing on the repo's root README, the bridge document, and the diagram catalogue gets the £80k signal in 90 seconds — concept depth visible, scope honest, tools justified, evidence linked. If they want more, every claim drills down to an ADR, a runbook, a diagram, or a live Application in the cluster.

The plan is not a rebuild. The engineering work that earned the salary band has already happened: a hub-spoke Azure landing zone (P1), an HA k3s cluster on Proxmox with an Ansible hardening role (P2), a matrix ApplicationSet driving multi-cluster GitOps (P3), a FastAPI/LiteLLM gateway live on the cluster for days (P4), and a kube-prometheus-stack + Sealed-Secrets observability + secrets layer (P5). Six ADRs, two runbooks, five release tags, ~70 commits, real incidents documented. The work is there. The plan moves it into the form an interviewer can verify in ninety seconds.

Two anchors that are not negotiable:

- **The architect's day-job title is Technical Operations Engineer at a UK MSP. The capability the portfolio demonstrates — and the target role this plan is calibrated for — is senior platform engineer.** Both are true simultaneously: the day job has not yet caught up to the capability. The portfolio is the evidence that bridges that gap. Positioning language honours both facts — no "transitioning," "aspiring," "junior," or "learning"; equally, no overclaim that the current title is already Platform Engineer.
- **Salary anchor is £75–85k base salary, permanent roles only, UK remote-first.** Every artefact in this plan is calibrated for that band and that employment type. The earlier £45–65k anchor in Plan-v3 was wrong for the work shipped and is retired (see §6). Contract, day-rate, and outside-IR35 work are explicitly out of scope for this attempt — base salary security is the deliberate prioritisation while the portfolio bridges the current-title-versus-capability gap.

## 2. The 6-week shape

| Week | Theme | Streams | Output |
|---|---|---|---|
| **1** | Bootstrap + bridge document skeleton + scope-boundary diagram | Narrative + diagrams | Plan-v4 operating doc, concept→tool mapping, bridge document spine, first two diagrams, ADR-007. **First merge.** |
| **2** | Bridge document expanded + 3 core diagrams + WU-3 closure | Narrative + diagrams + hardening | P4 chart deduplicated (canonical chart wins), topology diagrams committed (Azure landing zone, k3s cluster, multi-cluster GitOps), WU-9 P4 README rebuilt. |
| **3** | Remaining diagrams + WU-4 + WU-6 + CV/LinkedIn rewrite | Hardening + positioning | Bootstrap secrets converted to SealedSecret refs (WU-4), P5 README written (WU-6), CV/LinkedIn rebuilt to the £75–85k positioning. Portfolio narrative complete. |
| **4** | WU-5 decision + scope-honesty pass + capstone blog post + **first applications** | Application sprint begins | WU-5 resolved (clean dangling AKS refs or rebuild AKS), scope-discipline pass on every README, capstone post published. First 5 applications out. |
| **5** | Interview kata + portfolio final pass + scaled applications | Application sprint | Interview prep round (system design, deep-dives, behavioural), portfolio final read-through, 15+ applications out, phone screens starting. |
| **6** | Final rounds + negotiation prep + retrospective | Application sprint close | Offer pipeline or honest reassessment. Either way: a written retrospective on what the six weeks produced. |

**Build window:** nominally Thu 14 May → Wed 24 Jun 2026. Flex permitted. The plan is calibrated to the calendar, not to a rigid sprint cadence — daily budget is 2–3 hours, not a full work-week.

**Definition of "shippable to recruiters":** the repo is presentable from Week 4 Day 1. Weeks 5–6 are application throughput plus interview load, not building. If Week 4 starts and the portfolio is not shippable, the diagnosis is "Week 3 missed scope," not "more building needed."

## 3. Operating rules

These rules apply to every week's PR and every Claude Code orchestration prompt. They are not aspirational — every artefact in this directory honours them or it does not land.

### Branches and PRs

- **Never commit to `main`.** Feature branches only, named for the week (`feat/plan-v4-week-N-…`) or the work unit (`fix/wu-3-chart-dedup`).
- **Open a PR.** The architect merges. Direct commits to main are tolerated only for trivial typo fixes that touch a single character and never anything in `docs/adr/`, `docs/plan-v4/`, or the bridge document.
- **Every PR includes a Review Summary** in the description: every file changed, why, what to review carefully, and what was deliberately left undone. The Review Summary format is non-negotiable — it is the artefact that lets a tired reader merge confidently at 22:00.

### Commits

- **Conventional commits throughout.** `feat`, `fix`, `docs`, `refactor`, `chore`, `test`, `ci` — no exceptions. Subject lines are imperative-mood, body explains why.
- **Single-purpose commits.** A cleanup-audit commit does not bundle in a README rewrite. A WU-3 chart deletion does not bundle in a bridge-document edit. If a commit's body has two paragraphs starting with "and also," it should have been two commits.
- **Pre-commit hooks gate every commit.** `terraform fmt`/`validate`, `tflint`, `Checkov`, `detect-secrets`, `hadolint`. The hooks pass before the commit lands. `--no-verify` is not in scope.

### Cleanup gates

- **Every Plan-v4 weekly prompt opens with a cleanup audit** before generating new content. The audit lists files that may be obsolete given that week's work and proposes actions. **The audit does not delete.** Deletions are surfaced as commands the architect runs in a separate PR.
- This rule exists because Plan-v3 left enough scattered scaffolding (`files/` working artefacts, duplicate Helm chart, older planning docs) that subsequent passes wasted time deciding what was load-bearing. The Week 1 audit at [01-cleanup-audit.md](./01-cleanup-audit.md) is the template.

### Destructive operations

- **Surface, never automate.** `terraform destroy`, `kubectl delete`, `git reset --hard`, `git push --force`, `rm -rf` on any committed path, `helm uninstall` against the live cluster — all of these are commands the architect runs, not commands Claude Code runs. The orchestration prompt produces the command with its blast-radius commentary and stops.
- This is not theoretical. WU-2 closed with one unattributable Application CR deletion in a three-minute window (forensic note in PHASE-2-HANDOFF.md). The cluster has no K8s API audit logging yet (WU-8, deferred). Until WU-8 lands, the only audit log for destructive cluster operations is the architect's bash history and `git log`. Both rules above keep both logs useful.

### Concept-first, tool-second

- **Every artefact in this plan introduces a concept before naming the tool that implements it.** "Encrypted secrets in Git, decrypted only by a cluster-side controller — implemented with Bitnami Sealed Secrets" is correct. "Sealed Secrets, a tool for…" is wrong.
- This rule exists because the audience for the portfolio (hiring managers, technical leads, recruiters with technical scoping) picks the candidate who can name the concept. The tool is the implementation detail. ADR-005 demonstrates the pattern: the matrix-generator concept is named, the alternatives are evaluated against the concept, and the chosen tool inherits its justification from that evaluation.
- The single global reference for this mapping is [concept-tool-mapping.md](./concept-tool-mapping.md). Every ADR, every README, and every section of the bridge document links to it.

### ADRs

- **Every architectural decision gets an ADR.** ADRs live in `docs/adr/`. They follow the existing template (Context → Options Considered → Decision → Rationale → Consequences → Alternatives Rejected → Implementation).
- The bar for "architectural" is: would a future maintainer benefit from knowing why this choice was made over the alternatives? If yes, ADR. If the decision is purely tactical (a flag value, a one-off script structure), no ADR.

## 4. Concept→tool mapping

The single global mapping table lives at [`concept-tool-mapping.md`](./concept-tool-mapping.md). Every concept used anywhere in the portfolio appears there, with the tool that implements it, a one-or-two-sentence "why this tool" cell, and a link to the ADR or project README that does the depth.

That table is referenced (not copied) from the bridge document, from each project README, and from every ADR's "Decision" section. Editing the table updates the portfolio's framing globally. Editing it carelessly fragments the framing — treat it as load-bearing.

## 5. What this plan deliberately doesn't do

The plan is bounded. The boundaries are stated explicitly so the next "wouldn't it be cool if…" moment has a written answer.

- **No new infrastructure builds.** P1–P5 are built. P6 is empty by design and stays empty until at least one of its workstreams ships outside Plan-v4 — it is not part of the six-week scope. If a Plan-v4 week reads as "build a new project," the week's prompt was written wrong.
- **No AKS rebuild unless WU-5 decision goes that way.** WU-5 (clean dangling AKS refs vs rebuild AKS) is a decision, not a default. Rebuilding AKS costs money (the £60 hard cap), costs time, and changes the P3 narrative from "tore down to preserve spend discipline" to "kept running" — both stories are defensible. The decision lands in Week 4. Until then, no AKS infrastructure work.
- **No certifications chase.** AZ-104 is in progress in the background; that is fine and continues at its own pace. But certifications are not a Plan-v4 deliverable. The £75–85k band rewards demonstrated platform capability, not pieces of paper. If application replies stall in Weeks 5–6, the diagnostic is "positioning or pipeline," not "more certs."
- **No tech-stack expansion.** The portfolio is Azure + Proxmox + k3s + ArgoCD + Terraform + Ansible + Python (FastAPI) + Helm + Prometheus + Sealed Secrets. That stack is enough for the role band targeted. Adding GCP, AWS, or a second observability tool inside the six-week window dilutes signal and consumes the daily 2–3-hour budget that should go to bridge content and applications.
- **No multi-repo split.** The monorepo stays. Splitting `terraform-bls-azure`, `homelab-k3s`, `gitops-bls`, `llm-gateway` into separate repos was considered and rejected (ADR-007, alternatives section). The split would consume 1–2 weeks of Plan-v4's budget for purely cosmetic gain and would lose the cross-project links that make the portfolio coherent.
- **No "rewrite Plan-v3 from scratch" energy.** The salvageable parts of Plan-v3 — templates, prompts library, the engineering-standards section — carry forward. The build schedule, the weeks 1–18 narrative, and the £45–65k anchor are retired (§6). No litigation of why Plan-v3 was wrong beyond the ADR-007 entry.

## 6. Plan-v3 deprecation note

Plan-v3 (`BLS-master-plan-v3.md`, in local `files/` workspace — gitignored) drove the substantive build work that produced P1–P5. It did its job. The reasons it does not drive Plan-v4 are scoped and recorded here so the next time someone (the architect, a future collaborator, a recruiter doing diligence) asks "what changed," the answer is in one place.

### What carries forward from Plan-v3

- **Templates** under the working `files/` workspace — ADR template, incident-report template, weekly-review template. These are still good. The committed `docs/adr/000-template.md` is derived from one of them.
- **Prompts library** where prompts are still useful — the orchestration-prompts file kept in `docs/plan-v4/orchestration-prompts.md` (local-only) carries forward the prompt-engineering patterns that worked. The weekly prompts in Plan-v4 inherit the structure (read context, execute tasks, open PR with Review Summary) from Plan-v3 prompts.
- **Engineering standards.** Conventional commits, pre-commit hook stack, ADR-per-decision, tagging discipline, Azure spend cap, no-hardcoded-secrets, adversarial RLS tests on tenant data. None of these change.
- **The "what got built" register.** P1–P5 status as recorded in BLS-STATUS.md and the audit baseline (2026-05-12 → 2026-05-13) is the ground truth Plan-v4 builds on.

### What is retired from Plan-v3

- **The build schedule.** Plan-v3 framed an 18-week build out of scope from Week 0 (zero-state). The portfolio is no longer at zero state. The 18-week build schedule does not map onto the work that remains.
- **Weeks 1–18 narrative.** Anything that reads "in Week 9 we will…" or refers to a build phase by number does not survive Plan-v4. The narrative is now six weeks of polish-and-position on a built portfolio, not eighteen weeks of construction.
- **£45–65k salary anchor.** The anchor in Plan-v3 reflected a different assumption about the candidate's positioning. The work that landed (a hub-spoke landing zone with state in a remote backend, a hardened HA k3s cluster on bare hardware with documented incident recovery, a matrix-generator ApplicationSet, an in-cluster LLM gateway with metrics exposed to Prometheus, a Sealed-Secrets controller with a runbook and a tested restart path) is calibrated to the £75–85k band. Plan-v4 is built to that anchor. Any artefact that mentions £45–65k is wrong and should be corrected on sight.
- **References to Plan-v3 by name in committed content.** The bridge document and the project READMEs do not cite Plan-v3 as the source of any decision. The ADRs are the source of decisions. Plan-v3 was the harness that produced them; the ADRs themselves stand on their own.

### Disposal of the Plan-v3 source

`BLS-master-plan-v3.md` lives in the local `files/` workspace, which is gitignored. It is not in the public repo history and is not being deleted from the architect's machine — it remains a working artefact for reference. The decision to leave it local rather than commit it to a `docs/archive/` directory is deliberate: the public repo's framing should be Plan-v4 and forward. Reaching back to Plan-v3 should require intent.

---

## Index

- [01-cleanup-audit.md](./01-cleanup-audit.md) — Week 1 cleanup audit (no deletions; proposals only)
- [concept-tool-mapping.md](./concept-tool-mapping.md) — global concept→tool reference table
- `orchestration-prompts.md` — local-only weekly source-of-truth (gitignored)
- [`../adr/ADR-007-plan-v4-narrative-correction.md`](../adr/ADR-007-plan-v4-narrative-correction.md) — the decision record this operating doc implements
