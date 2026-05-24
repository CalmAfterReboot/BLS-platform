# Concept → Tool Mapping

> Global reference for every concept the BLS portfolio implements, the tool that implements it, and the one- or two-sentence reason that tool was chosen over its alternatives. Depth lives in the linked ADR or project README — this table is the index, not the argument.

Every README, every ADR's Decision section, and every section of the bridge document links here rather than restating the framing. If a concept is missing, it is either implemented but undocumented (add the row, link the source) or not in scope (do not pad the table).

## Reading order

The columns mean:

- **Concept** — the architectural property being implemented. Reader-facing language, no tool names.
- **Tool** — the chosen implementation.
- **Why this tool** — the discriminator versus the leading alternative(s). Not the full argument; the gist.
- **Evidence** — project number plus a link to the ADR or README that does the depth.

## Table

| Concept | Tool | Why this tool | Evidence |
|---|---|---|---|
| **Declarative state with reconciliation** — describe the desired state in code, let a controller make reality match | Terraform | Provider ecosystem is the broadest in the market and the state model is the easiest to reason about for hub-spoke landing zones. Bicep is Azure-only and ties the portfolio to one cloud; Pulumi adds a programming-language surface area without paying for it in this scope. | P1 — see [`projects/01-landing-zone/README.md`](../../projects/01-landing-zone/README.md) |
| **Configuration management as code** — describe what a node should look like, converge it idempotently | Ansible | Push-model agentless execution fits the bare-metal Proxmox topology where cloud-init's first-boot-only semantics don't cover the lifecycle (re-converge after kernel updates, drift correction, role re-application). | P2 — see [`ADR-003-ansible-over-cloud-init.md`](../adr/ADR-003-ansible-over-cloud-init.md) |
| **Container orchestration with high availability on commodity hardware** — three control-plane nodes, automatic VIP failover, no managed-service lock-in | k3s with kube-vip | k3s gives a single-binary HA control plane with a footprint that fits the homelab's resource budget; AKS would shift the same workload to a managed service at recurring cost and remove the "operate a cluster from etcd outward" learning surface the portfolio needs to demonstrate. | P2 — see [`ADR-002-homelab-over-cloud-only.md`](../adr/ADR-002-homelab-over-cloud-only.md) |
| **GitOps as the deployment boundary** — Git is the source of truth, a controller pulls and reconciles | ArgoCD | Application-as-first-class-resource model surfaces sync state, health, and drift in the API server itself — debuggable with `kubectl` alone. Flux's CRD layout splits the same information across more resources without changing the underlying model. | P3 — see [`03-aks-multicluster/README.md`](../../03-aks-multicluster/README.md) |
| **Declarative fleet management** — one manifest generates per-cluster per-workload Applications | ArgoCD ApplicationSet (matrix generator) | The matrix of Git-directory × clusters generates `N × M` Applications from one spec. List/Git generators alone produce one axis; only the matrix scales without manifest multiplication. | P3 — see [`ADR-005-applicationset-matrix-pattern.md`](../adr/ADR-005-applicationset-matrix-pattern.md) |
| **API gateway pattern for backend abstraction** — a single endpoint normalises calls across heterogeneous backends | LiteLLM + FastAPI | LiteLLM provides the OpenAI-compatible surface across 100+ LLM providers; FastAPI provides the typed request layer, dependency-injection, and `/metrics` exposure. Together they decouple the gateway's contract from any one model provider. | P4 — see [`k8s/workloads/llm-gateway/`](../../k8s/workloads/llm-gateway/) |
| **Pull-based metrics with label-based aggregation** — targets expose `/metrics`, a central scraper pulls on a schedule | Prometheus (via kube-prometheus-stack) | Pull-based scraping makes the scrape itself observable (target up/down is a first-class metric) and keeps the workloads stateless w.r.t. observability. Datadog is push-based, hosted, and a recurring cost; push-based agents shift failure modes into the agent's outbound delivery path. | P5 — see [`ADR-006-observability-gitops.md`](../adr/ADR-006-observability-gitops.md) |
| **Encrypted secrets in Git** — secret material is committed encrypted, decrypted only by an in-cluster controller | Sealed Secrets (Bitnami) | Asymmetric encryption keeps the encrypting client (`kubeseal`) credential-free — only the controller's private key decrypts. SOPS requires distributing decryption keys to every operator; ESO and Vault require a separate secret backend to operate alongside the cluster. | P5 — see [`docs/runbooks/sealed-secrets-controller.md`](../runbooks/sealed-secrets-controller.md) |
| **Defence-in-depth on bootstrap nodes** — every fresh VM is hardened to the same baseline before joining the cluster | Ansible `node-hardening` role (auditd, fail2ban, ssh hardening, sysctl tuning, ufw, ntp) | Hardening as a role makes the baseline both re-runnable (correct drift) and reviewable (a PR diff shows the change). Doing this at cloud-init time would gate the entire baseline behind first boot and lose the re-converge property. | P2 — see [`ADR-003-ansible-over-cloud-init.md`](../adr/ADR-003-ansible-over-cloud-init.md) and [`ansible/roles/node-hardening/`](../../ansible/roles/node-hardening/) |
| **Multi-source ArgoCD Application** — pin an upstream Helm chart to a version while keeping values in a reviewable Git file | ArgoCD multi-source `Application` (chart source + `$values` source) | Separates "which chart version" from "which values" — each is a one-file Git diff and each is independently reviewable. The umbrella-chart alternative requires committing chart tarballs or runtime `helm dependency update` against a credentialled registry. | P5 — see [`ADR-006-observability-gitops.md`](../adr/ADR-006-observability-gitops.md) |
| **Tagging discipline + spend control** — every Azure resource carries an owner, environment, and project tag; policy denies untagged resources | Azure Policy (assigned via Terraform) | Policy enforcement at the platform layer means the rule is uniform across human and machine creators. Tag-only policies catch the most common cost-attribution failures cheaply; cost-cap policies catch the rest before invoicing. | P1 — see [`projects/01-landing-zone/README.md`](../../projects/01-landing-zone/README.md) |
| **Remote Terraform state with locking** — state is held in a backend that supports concurrent-access protection, never on a workstation | Azure Storage account with blob-locking | Workstation-local `terraform.tfstate` is a single point of failure and a leak surface (sensitive outputs are stored unencrypted). Azure blob storage with `use_azuread_auth` plus blob lease locking is the lowest-overhead remote backend in this stack. | P1 — Azure Storage account / `tfstate` container (BLS subscription; names redacted) |
| **Cluster-API audit trail** — every CRUD on Kubernetes API objects is logged with subject, verb, and resource | k3s `--audit-log-path` + audit policy (planned: WU-8) | The Linux `auditd` covers process and filesystem events but does not observe Kubernetes API calls. Enabling k3s audit logging closes the WU-2 forensic gap (Application CR deletion was unattributable). Deferred to WU-8 with explicit log-volume budget. | P5 — see [`PHASE-2-HANDOFF.md`](../../PHASE-2-HANDOFF.md) WU-8 (gitignored — local) |
| **Pre-commit safety net** — static checks gate every commit at the workstation, not at CI | `pre-commit` framework: terraform fmt/validate, tflint, Checkov, detect-secrets, hadolint | Workstation-side hooks catch the cheap failures (formatting, syntax, obvious secrets) before they reach the branch. CI handles what depends on a clean environment (Semgrep, Trivy, integration tests). Splitting the responsibility means CI cost is not spent on what `fmt` could have caught. | Repo-wide — see [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) |

## How to extend this table

Add a row when:

- A new ADR lands that introduces a tool to the portfolio.
- A re-read of an existing ADR surfaces a concept the table does not name yet.
- A reader of the bridge document or a project README asks "why this tool?" and the answer is not one click away from a concept name.

Do not add a row when:

- The tool is internal-only and never named in the candidate-facing artefacts (e.g., `jq`, `kubectl`, `helm` as a CLI). The mapping table is for architectural decisions, not for the standard developer toolbelt.
- The "why" cell would need more than two sentences. That is a sign the depth belongs in an ADR; write the ADR first, link it from the table.
