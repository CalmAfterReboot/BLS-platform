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
- No hand-drawn aesthetics. The portfolio reads to a hiring audience; doodles read as undergrad coursework.
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
python3 02-k3s-cluster-topology.py
# produces 02-k3s-cluster-topology.png in the same directory
```

If a contributor edits a `.py` and pushes without rendering locally, the CI workflow renders and commits the `.png` on their behalf. If a contributor renders locally, the workflow detects no diff and exits cleanly.

## Catalogue

The catalogue is the index. Every diagram below has a row; every row links to source, output (where applicable), the supporting document, and the one-paragraph caption.

| # | Source | Type | Caption | Supports |
|---|---|---|---|---|
| 00 | [`00-system-context.mmd`](./00-system-context.mmd) | Mermaid (C4-style) | System context diagram: the BLS Platform monorepo at the centre, with the four external actors (Engineer, Hiring Manager / Technical Lead, Recruiter, External Reviewer) on one axis and the three external systems (GitHub, Microsoft Azure, Proxmox Homelab, LLM Providers) on the other. Each edge names the interaction. | Bridge document §1 (the signal); [`BLS-PLATFORM-ENGINEERING-GUIDE.md`](../../BLS-PLATFORM-ENGINEERING-GUIDE.md) |
| 07 | [`07-scope-boundary.mmd`](./07-scope-boundary.mmd) | Mermaid flowchart | Scope discipline: two columns side by side — what this portfolio claims (left) versus what it deliberately does not claim (right). Reads as a visual summary of bridge document §3 (portfolio at a glance) and §6 (deliberate non-claims). | Bridge document §6 (what this portfolio deliberately doesn't claim); Plan-v4 operating doc §5 |

Future diagrams (planned, Plan-v4 Weeks 2–3):

| # | Planned source | Type | Planned caption | Supports |
|---|---|---|---|---|
| 01 | `01-azure-landing-zone.py` | Python topology | Azure hub-spoke landing zone — RG, hub VNet with one NSG, spoke VNet with one NSG, Log Analytics workspace, peering edges. | Bridge document §4.1 |
| 02 | `02-k3s-cluster-topology.py` | Python topology | k3s cluster on Proxmox — three control-plane nodes with kube-vip, two workers, etcd cluster, the Ansible-applied hardening layer rendered as a banner on each node. | Bridge document §4.2 |
| 03 | `03-gitops-reconciliation.mmd` | Mermaid flowchart | GitOps reconciliation loop — push to Git, ArgoCD application controller pulls, matrix ApplicationSet expands to N×M Applications, sync to cluster, drift detected via reconciliation interval. | Bridge document §4.3; ADR-005 |
| 04 | `04-llm-gateway-request-path.mmd` | Mermaid sequence | LLM gateway request path — client request, FastAPI route, LiteLLM provider selection, Redis cache hit/miss branch, response, `/metrics` observation. | Bridge document §4.4 |
| 05 | `05-observability-scrape.py` | Python topology | Prometheus scrape graph — Prometheus instance in `monitoring`, ServiceMonitor selectors, scrape targets across `llm-gateway`, `argocd`, `sealed-secrets`, `kube-system` namespaces. | Bridge document §4.5; ADR-006 |
| 06 | `06-sealed-secrets-backup.mmd` | Mermaid sequence | Sealed-secrets master-key backup procedure — kubectl export, off-workstation transfer, controller-restart test, throwaway round-trip verification. | [`sealed-secrets-controller.md`](../runbooks/sealed-secrets-controller.md) |
