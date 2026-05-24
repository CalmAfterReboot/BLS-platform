# Tools and URLs

> Public reference for every tool the BLS Platform uses, with links to its
> documentation and the version pinned (where one is committed). This is
> the index — depth lives in the linked ADR, runbook, or project README.
> For the conceptual mapping of *why* each tool was chosen, see
> [`docs/plan-v4/concept-tool-mapping.md`](plan-v4/concept-tool-mapping.md).

Internal homelab URLs (ArgoCD UI, Grafana UI, kube-vip VIP, Proxmox host)
are deliberately omitted — per the sanitisation rule, no
private-network address is committed to a public artefact.

## This repository

| Resource | URL |
|---|---|
| Source of truth (GitHub) | <https://github.com/CalmAfterReboot/BLS-platform> |
| Gateway container image (GHCR) | `ghcr.io/calmafterreboot/bls-llm-gateway` (`:latest` + `:<sha>`) |
| CI build workflow | [`.github/workflows/build-gateway.yaml`](../.github/workflows/build-gateway.yaml) |
| Diagram render workflow | [`.github/workflows/render-diagrams.yml`](../.github/workflows/render-diagrams.yml) |
| Terraform CI / plan / apply | [`.github/workflows/terraform-{ci,plan,apply}.yml`](../.github/workflows/) |

## Cloud platform — P1 Landing Zone

| Tool | Use in portfolio | URL | Version |
|---|---|---|---|
| Terraform | Hub-spoke VNet, NSGs, Log Analytics, Storage (remote state), Key Vault | <https://developer.hashicorp.com/terraform> | ≥ 1.5 (CI) |
| Terraform Azure provider | Azure resource provisioning | <https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs> | pinned in `modules/` |
| Microsoft Azure docs | Subscription, RG, policy reference | <https://learn.microsoft.com/azure/> | n/a |
| Azure CLI | Local subscription auth, occasional ad-hoc checks | <https://learn.microsoft.com/cli/azure/> | n/a |

## Provisioning & configuration — P2

| Tool | Use in portfolio | URL | Version |
|---|---|---|---|
| Ansible | `node-hardening` role across all k3s nodes (SSH lockdown, ufw, fail2ban, sysctl, NTP) | <https://docs.ansible.com/> | n/a (system-installed) |
| k3s | HA Kubernetes on Proxmox VMs | <https://docs.k3s.io/> | per `02-k3s-platform/` |
| kube-vip | VIP for HA control plane | <https://kube-vip.io/> | per `02-k3s-platform/` |
| Proxmox VE | Hypervisor for the homelab cluster | <https://www.proxmox.com/en/proxmox-virtual-environment/overview> | n/a |

## GitOps — P3

| Tool | Use in portfolio | URL | Version |
|---|---|---|---|
| ArgoCD | Reconciles every workload manifest from `main` to in-cluster + bls-aks-demo | <https://argo-cd.readthedocs.io/> | per `k8s/apps/` |
| ArgoCD ApplicationSet | Matrix generator `[clusters] × [workloads]` produces N×M Applications from one spec | <https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/> | bundled with ArgoCD |
| Helm | Templating engine for every chart under `k8s/workloads/` | <https://helm.sh/docs/> | ≥ 3.12 |

## Workload — P4 LLM Gateway

| Tool | Use in portfolio | URL | Version |
|---|---|---|---|
| FastAPI | HTTP edge (`app/main.py`), Bearer auth middleware, `/healthz`, `/metrics` | <https://fastapi.tiangolo.com/> | `0.111.0` (`app/requirements.txt`) |
| LiteLLM (proxy + SDK) | Backend routing across Ollama / Azure OpenAI / OpenAI / DeepSeek; cache-aware Router with `num_retries` and `routing_strategy: least-busy` | <https://docs.litellm.ai/> | proxy `ghcr.io/berriai/litellm:main-latest`; SDK `>=1.40,<2.0` (`requirements-dev.txt`) |
| Uvicorn | ASGI server for the FastAPI app | <https://www.uvicorn.org/> | `0.30.0` (`app/requirements.txt`) |
| httpx | Async HTTP client (gateway → LiteLLM forwarding) | <https://www.python-httpx.org/> | `0.27.0` (`app/requirements.txt`) |
| Pydantic v2 | Request schemas (`ChatRequest`) | <https://docs.pydantic.dev/2/> | `2.7.0` (`app/requirements.txt`) |
| prometheus-fastapi-instrumentator | `/metrics` endpoint | <https://github.com/trallnag/prometheus-fastapi-instrumentator> | `7.1.0` (`app/requirements.txt`) |
| Ollama | Open-model backend (llama3.2, mistral, deepseek-r1) on the Proxmox host | <https://ollama.com/> · <https://github.com/ollama/ollama> | n/a (host-installed) |
| Redis | Exact-match response cache for LiteLLM | <https://redis.io/docs/latest/> | `7-alpine` (`values.yaml`) |
| OpenAI Python client (via LiteLLM) | Live verification suite calls OpenAI directly through LiteLLM SDK | <https://platform.openai.com/docs/api-reference> | bundled with `litellm` |
| Azure OpenAI Service | Cloud premium-tier backend (configured in LiteLLM `model_list`) | <https://learn.microsoft.com/azure/ai-services/openai/> | n/a |

## Observability — P5

| Tool | Use in portfolio | URL | Version |
|---|---|---|---|
| Prometheus | Pull-based metrics, ServiceMonitor scrape every 30s | <https://prometheus.io/docs/> | via kube-prometheus-stack |
| kube-prometheus-stack (Helm chart) | All-in-one Prometheus + Alertmanager + Grafana + Operator | <https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack> | pinned in `k8s/apps/monitoring.yaml` |
| Grafana | Dashboards over Prometheus data source | <https://grafana.com/docs/grafana/latest/> | bundled with kube-prometheus-stack |
| Alertmanager | Alert routing | <https://prometheus.io/docs/alerting/latest/alertmanager/> | bundled with kube-prometheus-stack |
| ServiceMonitor CRD | Declarative Prometheus scrape configs | <https://prometheus-operator.dev/docs/operator/api/#monitoring.coreos.com/v1.ServiceMonitor> | bundled with prometheus-operator |

## Secrets

| Tool | Use in portfolio | URL | Version |
|---|---|---|---|
| Sealed Secrets (Bitnami) | Encrypted-in-git Secret manifests; `llm-gateway-secrets` sealed `--scope=strict` to namespace + name | <https://github.com/bitnami-labs/sealed-secrets> · <https://sealed-secrets.netlify.app/> | controller via `k8s/apps/sealed-secrets.yaml`; `kubeseal` v0.36.6 locally |
| detect-secrets (Yelp) | Pre-commit hook blocking accidental commits of high-entropy strings / known secret patterns | <https://github.com/Yelp/detect-secrets> | `v1.5.0` (`.pre-commit-config.yaml`) |

## CI / dev hygiene

| Tool | Use in portfolio | URL | Version |
|---|---|---|---|
| pre-commit | Hook runner | <https://pre-commit.com/> | n/a (system-installed) |
| `pre-commit-hooks` (trailing-whitespace, end-of-file-fixer, check-yaml, etc.) | Standard hygiene | <https://github.com/pre-commit/pre-commit-hooks> | `v4.6.0` |
| Ruff | Python lint + format (scoped to `k8s/workloads/llm-gateway/tests/`) | <https://docs.astral.sh/ruff/> | `v0.6.9` |
| pre-commit-terraform | `terraform fmt`, `terraform validate`, Checkov | <https://github.com/antonbabenko/pre-commit-terraform> | `v1.92.0` |
| Checkov | Terraform static analysis | <https://www.checkov.io/> | via pre-commit-terraform |
| Hadolint | Dockerfile lint | <https://github.com/hadolint/hadolint> | `v2.12.0` |
| pytest | Test runner for the live OpenAI verification suite | <https://docs.pytest.org/> | `>=8.0,<9.0` (`requirements-dev.txt`) |
| pytest-asyncio | Async test mode | <https://github.com/pytest-dev/pytest-asyncio> | `>=0.23,<1.0` |
| python-dotenv | `.env` loading in the live test suite | <https://github.com/theskumar/python-dotenv> | `>=1.0,<2.0` |

## Diagrams

| Tool | Use in portfolio | URL | Version |
|---|---|---|---|
| Mermaid | Sequence + flowchart + C4-style intent diagrams; renders natively in GitHub `.md` | <https://mermaid.js.org/> | GitHub-bundled |
| Python `diagrams` library (mingrammer) | Cloud / Kubernetes topology with provider icons; CI-rendered to PNG | <https://diagrams.mingrammer.com/> | system-installed in CI runner |
| Graphviz | Layout engine used by `diagrams` | <https://graphviz.org/> | apt-installed in CI runner |
| Diagram catalogue | All diagrams + captions | [`docs/diagrams/README.md`](diagrams/README.md) | n/a |

## C4 / architecture method references

| Reference | URL |
|---|---|
| C4 Model | <https://c4model.com/> |
| ADR pattern (Michael Nygard) | <https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions> |
| `adr-tools` (informational) | <https://github.com/npryce/adr-tools> |

## Updating this file

When adding a tool to the platform:

1. Add a row in the relevant section.
2. Link to **upstream documentation**, not to a vendor's marketing landing page.
3. Pin the version where one is committed (in `*.yaml`, `requirements.txt`, `.pre-commit-config.yaml`, Helm `Chart.yaml`). Use `n/a` when the version is system-installed or otherwise not pinned.
4. If the tool justifies an architectural choice, also add a row in [`docs/plan-v4/concept-tool-mapping.md`](plan-v4/concept-tool-mapping.md) linking the ADR.
5. If a tool is **removed**, delete the row in the same PR that removes its usage. A row pointing at unused infrastructure is worse than no row.
