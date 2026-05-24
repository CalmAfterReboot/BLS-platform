"""
01 — Container-level view of the BLS Platform.

A C4 Container-style view showing every running container/process in
the portfolio, grouped by their cluster of execution. The diagram is
the second-zoom-in from the system context diagram (00); it answers
"what actually runs, and where" without yet drilling into a single
project's internals.

Supports: BLS-PLATFORM-ENGINEERING-GUIDE.md §4 (concept-to-tool
mapping, project-by-project landing page).

Stable prefix: 01. Filename and prefix must not change once committed
— external references depend on it (per docs/diagrams/README.md naming
rule).
"""

from diagrams import Cluster, Diagram, Edge
from diagrams.azure.network import VirtualNetworks, NetworkSecurityGroupsClassic
from diagrams.azure.security import KeyVaults
from diagrams.azure.storage import StorageAccounts
from diagrams.azure.analytics import LogAnalyticsWorkspaces
from diagrams.azure.ml import CognitiveServices
from diagrams.k8s.compute import Pod
from diagrams.k8s.infra import Master, Node
from diagrams.k8s.network import Ingress
from diagrams.onprem.client import User
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.container import Docker
from diagrams.onprem.gitops import ArgoCD
from diagrams.onprem.monitoring import Grafana, Prometheus
from diagrams.onprem.vcs import Github
from diagrams.programming.framework import Fastapi
from diagrams.programming.language import Python


graph_attr = {
    "splines": "spline",
    "fontsize": "16",
    "labelloc": "t",
    "rankdir": "LR",
}

with Diagram(
    "BLS Platform — Container view (C4 L2)",
    filename="01-container-view",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
):
    # Audience / hiring-side reader
    with Cluster("Audience"):
        hiring = User("Hiring manager /\nrecruiter")

    # Source of truth + CI
    with Cluster("GitHub (source of truth)"):
        repo = Github("CalmAfterReboot/\nBLS-DevOps")
        actions = GithubActions("CI: build, lint,\ndiagram render")

    # External LLM providers
    with Cluster("External LLM providers"):
        deepseek = CognitiveServices("DeepSeek API")
        aoai = CognitiveServices("Azure OpenAI")
        openai = CognitiveServices("OpenAI\n(live verification path)")

    # Azure landing zone (P1)
    with Cluster("Azure subscription (P1)"):
        with Cluster("rg-bls-platform"):
            hub = VirtualNetworks("Hub VNet")
            spoke = VirtualNetworks("Spoke VNet")
            nsg = NetworkSecurityGroupsClassic("NSGs (subnet)")
            log_analytics = LogAnalyticsWorkspaces("Log Analytics")
            tfstate = StorageAccounts("Storage —\ntfstate")
            kv = KeyVaults("Key Vault")
            hub - Edge(label="peering") - spoke

    # Proxmox homelab cluster (P2 + P4 + P5)
    with Cluster("Proxmox homelab — k3s HA cluster"):
        with Cluster("control plane (3 nodes + kube-vip VIP)"):
            cp = [Master("cp-1"), Master("cp-2"), Master("cp-3")]
        with Cluster("workers"):
            workers = [Node("worker-1"), Node("worker-2")]

        with Cluster("namespace: argocd (in-cluster)"):
            argocd = ArgoCD("ArgoCD\n(ApplicationSet matrix)")

        with Cluster("namespace: llm-gateway (P4)"):
            ingress = Ingress("Traefik ingress")
            fastapi = Fastapi("FastAPI proxy")
            litellm = Python("LiteLLM router")
            redis = Pod("Redis cache")
            ingress >> fastapi >> litellm >> redis

        with Cluster("namespace: monitoring (P5)"):
            prom = Prometheus("Prometheus")
            grafana = Grafana("Grafana")
            prom >> grafana

        with Cluster("namespace: sealed-secrets (P5)"):
            sealed = Pod("sealed-secrets\ncontroller")

        # Ollama runs outside k3s on the Proxmox host
        with Cluster("Proxmox host (outside k3s)"):
            ollama = Docker("Ollama\n(open models)")

    # Edges across the diagram
    hiring >> Edge(label="reads") >> repo
    repo >> Edge(label="builds image") >> actions
    actions >> Edge(label="pushes\nghcr.io image") >> fastapi
    repo << Edge(label="reconciles\nfrom main", style="dashed") << argocd
    argocd >> Edge(label="applies", style="dashed") >> fastapi
    argocd >> Edge(label="applies", style="dashed") >> prom
    argocd >> Edge(label="applies", style="dashed") >> sealed

    litellm >> Edge(label="HTTP\n11434", color="darkgreen") >> ollama
    litellm >> Edge(label="HTTPS", color="darkblue") >> deepseek
    litellm >> Edge(label="HTTPS", color="darkblue") >> aoai
    litellm >> Edge(label="HTTPS\n(live verification only)", color="darkblue", style="dashed") >> openai

    # Sealed-secrets controller unseals committed SealedSecrets into
    # in-namespace Secrets that the gateway and LiteLLM mount as env vars
    # (BLS_API_KEYS, LITELLM_MASTER_KEY, OLLAMA_ENDPOINT). Edge is
    # rendered dashed because the relationship is provisioning-time,
    # not request-time.
    sealed >> Edge(label="unseals\nllm-gateway-secrets", style="dashed", color="darkred") >> fastapi
    sealed >> Edge(label="OLLAMA_ENDPOINT", style="dashed", color="darkred") >> litellm

    prom >> Edge(label="scrapes /metrics", style="dotted") >> fastapi
    prom >> Edge(label="scrapes", style="dotted") >> argocd
    prom >> Edge(label="scrapes", style="dotted") >> sealed

    # Azure side — show landing zone is observed by Log Analytics
    nsg >> Edge(style="dotted", label="diag logs") >> log_analytics
    spoke >> Edge(style="dotted") >> log_analytics
    tfstate >> Edge(style="invis") >> kv  # alignment hint only
