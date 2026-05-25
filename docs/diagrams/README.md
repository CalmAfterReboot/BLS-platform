# Diagrams

> Source-of-truth conventions for every diagram in this repository. Diagrams are part of the bridge document's reading path — they exist to make architectural intent visible in seconds, not to decorate.

## Tool choice

Two tools, used for different purposes.

**Mermaid** — sequence, flowchart, state, simple C4-style system context. Renders natively in GitHub `.md` files; no build step needed; the source itself is reviewable in a diff. Use Mermaid when the diagram describes *intent* (request paths, scope boundaries, decision trees, state transitions). Mermaid files carry the `.mmd` extension.

**Python `diagrams` library (mingrammer)** — cloud and infrastructure topology with real provider icons. Renders to PNG via a CI workflow (see [`.github/workflows/render-diagrams.yml`](../../.github/workflows/render-diagrams.yml)). Use the Python library when the diagram describes *topology* — Azure resources with their service icons, k3s nodes with kube-vip, Prometheus scrape targets with their service icons. Python source files carry the `.py` extension; rendered output carries `.png`.

The choice is not aesthetic — it is reviewability. A Mermaid flowchart edit is one line in a diff. A Python `diagrams` edit is also one line but the PNG output is a binary blob; CI rendering keeps the blob's history consistent with the source.

## Naming

`NN-descriptive-name.{mmd,py,png}` where `NN` is a two-digit stable-ordering prefix.

- `00–09` — overview and scope (system context, scope boundary)
- `10–19` — project-level topology (Azure landing zone, k3s cluster, multi-cluster GitOps)
- `20–29` — workload and request paths (LLM gateway request path, observability scrape graph)
- `30–39` — operational flows (sealed-secrets backup, restore-from-backup, WU forensic timelines)
- `40+` — reserved for future expansion

The prefix is stable: once a diagram is published with `02-`, that prefix stays even if the diagram is later renamed. New diagrams take the next free number in the relevant band rather than re-numbering existing diagrams. This rule exists so that external references (blog posts, CV, LinkedIn share images) do not break.

Descriptive name is lowercase, hyphen-separated, and reads like a noun phrase. `02-k3s-cluster-topology.py` is correct; `02-cluster.py` is not (which cluster?); `02-K3sTopology.py` is not (case style).

## Source-and-output pattern

- **Mermaid:** the `.mmd` source is the only file committed. GitHub renders it in the rendered Markdown view. There is no `.png` output.
- **Python:** the `.py` source and the rendered `.png` output are both committed. CI re-renders on push when the `.py` changes; the resulting `.png` is checked in by a follow-up commit if the rendered output differs (the workflow handles this).

The Mermaid-only-source rule keeps the diff clean. The Python-source-plus-PNG rule is the trade-off for using a non-native renderer: readers who do not run the Python library still see the rendered artefact in the repo.

## Caption rule

Every diagram has a one-paragraph caption in this README's catalogue table below. The caption answers two questions: what does this diagram show, and which document (bridge document section, ADR, README) does it support? A diagram without a caption is a diagram without a purpose.

## Style

- Real provider icons where applicable (the Python `diagrams` library handles this for Azure, AWS, GCP, Kubernetes).
- No emoji decoration in node labels. Node labels are nouns; verbs go on edges.
- No hand-drawn aesthetics. Diagrams read as engineering artefacts; doodles do not.
- Colour use is functional, not decorative. If two node types share a colour, that colour means something (e.g., "in scope" green, "out of scope" grey).
- Edge labels are short. If an edge needs a sentence, the sentence belongs in the supporting document, not the diagram.

## Render workflow (Python)

The Python `diagrams` library has runtime dependencies (Graphviz; the `diagrams` Python package). CI handles both — the workflow at [`.github/workflows/render-diagrams.yml`](../../.github/workflows/render-diagrams.yml) installs Graphviz and the package, runs every `.py` in this directory, and commits any changed `.png` outputs back to the same branch.

Local rendering is supported but not required:

```bash
# One-time setup
sudo apt-get install -y graphviz
python3 -m pip install --user diagrams

# Render a single diagram
cd docs/diagrams/
python3 03-k3s-ha-cluster.py
# produces 03-k3s-ha-cluster.png in the same directory
```

If a contributor edits a `.py` and pushes without rendering locally, the CI workflow renders and commits the `.png` on their behalf. If a contributor renders locally, the workflow detects no diff and exits cleanly.

## Catalogue

The catalogue is the index. Every diagram below has a row; every row links to source, output (where applicable), the supporting document, and the one-paragraph caption.

| # | Source | Type | Caption | Supports |
|---|---|---|---|---|
| 00 | [`00-system-context.mmd`](./00-system-context.mmd) | Mermaid (C4 L1) | System context: the BLS Platform at the centre and the systems it genuinely interacts with at runtime — GitHub (source of truth + CI), Microsoft Azure (P1 landing zone + Terraform remote state), the Proxmox homelab (k3s cluster, ArgoCD, workloads P4 and P5), and the upstream LLM providers (OpenAI, Azure OpenAI, Ollama) consumed via the FastAPI/LiteLLM gateway. The single human actor is an API client (developer or service) hitting the LLM gateway — a real runtime user. The dotted edge from GitHub to Proxmox names the GitOps reconciliation path (Git is the source, ArgoCD pulls). Non-technical reader actors are deliberately not in this diagram; a system context diagram records technical interactions, not reader audiences. | Bridge document §1 (the signal); [`BLS-PLATFORM-ENGINEERING-GUIDE.md`](../../BLS-PLATFORM-ENGINEERING-GUIDE.md) |
| 01 | [`01-container-view.py`](./01-container-view.py) | Python topology (C4 L2) | Container-level view of the entire BLS platform. GitHub + Actions on the left; Azure landing zone (P1) and Proxmox homelab k3s cluster (P2 + P4 + P5) in the centre; external LLM providers on the right (Ollama on the Proxmox host, plus DeepSeek / Azure OpenAI / OpenAI as cloud providers — the last reached only via the opt-in live verification suite). Shows GitOps reconciliation, the CI image-push edge, Prometheus scrape edges, the LiteLLM-to-backend request paths, and a dashed provisioning-time edge from the sealed-secrets controller to the gateway and LiteLLM showing how `llm-gateway-secrets` (BLS_API_KEYS, LITELLM_MASTER_KEY, OLLAMA_ENDPOINT) is injected as env vars at pod start. | Bridge document §4 (project-by-project landing page) |
| 02 | [`02-landing-zone-topology.py`](./02-landing-zone-topology.py) | Python topology | P1 — Azure Landing Zone. Hub VNet `10.0.0.0/16` and Spoke VNet `10.1.0.0/16` peered bidirectionally; subnet-scoped NSGs; Log Analytics workspace receiving diagnostic logs from VNets and NSGs; Storage Account for remote Terraform state; Key Vault. | Bridge document §4 (P1) |
| 03 | [`03-k3s-ha-cluster.py`](./03-k3s-ha-cluster.py) | Python topology | P2 — k3s HA cluster on Proxmox. Three control-plane nodes behind a kube-vip-managed VIP (placeholder `<vip-ip>`), embedded etcd quorum, two workers, ArgoCD running in-cluster, the Ansible `node-hardening` role rendered as a banner. VLAN identifiers placeheld per the private-network sanitisation rule. | Bridge document §4 (P2); ADR-002, ADR-003 |
| 04 | [`04-multi-cluster-gitops.mmd`](./04-multi-cluster-gitops.mmd) | Mermaid sequence | P3 — multi-cluster GitOps reconciliation. Git push → ApplicationSet matrix generator expands `[clusters] × [workloads]` → ArgoCD reconciles each child Application to its target cluster (k3s in-cluster and `bls-aks-demo`) in parallel → health rolls back up to the UI. The `bls-aks-demo` arm is annotated with its current `Unknown` sync state — AKS is torn down for cost discipline (rebuild tracked as WU-5), so the reconcile leg is intentionally unreachable rather than broken. The closing note captures why `selfHeal=true` is load-bearing for the reachable arm. | Bridge document §4 (P3); ADR-005 |
| 05 | [`05-llm-gateway-request-path.mmd`](./05-llm-gateway-request-path.mmd) | Mermaid sequence | P4 — LLM gateway request path. Three runtime credentials are sourced from the SealedSecret `llm-gateway-secrets` at pod start (rendered as a banner note, not a request-time edge): `BLS_API_KEYS` gates Bearer auth at the FastAPI edge, `LITELLM_MASTER_KEY` authorises gateway→LiteLLM, and `OLLAMA_ENDPOINT` is substituted into LiteLLM's `api_base` via its `os.environ/VAR` syntax — so no homelab-internal address is committed in plaintext. Auth failures return a typed JSON envelope (401 missing-token / 403 invalid-key). LiteLLM router carries the cache-hit/cache-miss branch and backend selection (Ollama on the Proxmox host vs Azure OpenAI). The Prometheus `/metrics` scrape is rendered as a separate async edge — deliberately not part of the request path. | Bridge document §4 (P4); ADR-008; [`k8s/workloads/llm-gateway/SECURITY.md`](../../k8s/workloads/llm-gateway/SECURITY.md) |
| 06 | [`06-observability-data-flow.py`](./06-observability-data-flow.py) | Python topology | P5 — observability data flow. Top-to-bottom three-row topology of the kube-prometheus-stack: nine ServiceMonitor scrape sources arranged horizontally at the top (eight in the `monitoring` namespace plus the `llm-gateway` ServiceMonitor across the namespace boundary — admitted through the NetworkPolicy boundary by the `gateway-policy` ingress rule per [`ADR-009`](../adr/ADR-009-networkpolicy-scope.md)); the Prometheus stack in the middle (Prometheus StatefulSet, prometheus-operator, and the ServiceMonitor + PrometheusRule CRDs that the operator reconciles); and the data consumers at the bottom (Grafana for dashboard reads, AlertManager rendered as disabled — chart values turn it off today, rules fire to the Prometheus UI only, re-enable is PR-E scope, and the human operator reading via `kubectl port-forward` — the only inbound surface because this cluster runs `--disable traefik`). The scrape edge label "scrape /metrics every 30s" is set once on the source cluster's title rather than repeated on each of the nine edges. No external nodes — Prometheus does not scrape across the cluster boundary, the operator talks only to the kube-apiserver, and Grafana has no external datasources configured. Deliberately omitted: log aggregation (no Loki — see bridge §4.5), distributed tracing (no Tempo), and workload-specific `PrometheusRule` resources (the ~30 rules visible are the chart's defaults; workload rules are PR-E scope). | Bridge document §4 (P5); [`ADR-006`](../adr/ADR-006-observability-gitops.md); [`ADR-009`](../adr/ADR-009-networkpolicy-scope.md) |
| 07 | [`07-scope-boundary.mmd`](./07-scope-boundary.mmd) | Mermaid flowchart | Scope discipline: two columns — what the portfolio claims (left) versus what it deliberately does not claim (right). Labels stay short and uniform (3-5 words each); detail lives here. Left, one row per project: Azure landing zone (Terraform), HA k3s on Proxmox, matrix ApplicationSet GitOps, the LLM gateway with its committed live OpenAI verification evidence, kube-prometheus-stack with Sealed Secrets, and NetworkPolicy enforcement on the `llm-gateway` namespace (scope decision in [`ADR-009`](../adr/ADR-009-networkpolicy-scope.md) — `monitoring` and `sealed-secrets` explicitly deferred). Right, one row per non-claim: no multi-tenant production workload; no AWS/GCP production depth inside this repo (GCP is on the P6 roadmap, not built); no platform-team-of-N coordination (one-architect portfolio); no live AKS (torn down for cost discipline, rebuild tracked as WU-5); no formal 24/7 SRE on-call (that's MSP context, not this repo). Dropped from the prior version: an "ADRs, runbooks, release tags" row (process commentary, not project scope) and an "every WU closed" row (meta-commentary). The detail those rows carried lives in [`docs/adr/`](../adr/), the bridge document, and the per-project READMEs. | Bridge document §6 (what this portfolio deliberately doesn't claim); Plan-v4 operating doc §5 |

Future diagrams (planned, Plan-v4 Week 3):

| # | Planned source | Type | Planned caption | Supports |
|---|---|---|---|---|
| 08 | `08-sealed-secrets-backup.mmd` | Mermaid sequence | Sealed-secrets master-key backup procedure — kubectl export, off-workstation transfer, controller-restart test, throwaway round-trip verification. | [`sealed-secrets-controller.md`](../runbooks/sealed-secrets-controller.md) |
