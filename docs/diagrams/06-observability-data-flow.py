"""
06 — Observability data flow (P5).

Topology view of the Project 5 observability stack. The left column
holds the nine ServiceMonitor scrape sources (eight inside the
`monitoring` namespace plus one across the namespace boundary in
`llm-gateway`). The centre column holds the Prometheus stack — the
StatefulSet itself, the prometheus-operator that watches CRDs, and
the ServiceMonitor and PrometheusRule CRDs that configure the scrapes
and the rule evaluator respectively. The right column holds the data
consumers — Grafana for dashboard reads, AlertManager for routing
(rendered as deferred — the chart values disable Alertmanager on this
deployment; rules fire to the Prometheus UI only), and the operator
human reading via `kubectl port-forward` (the only inbound surface,
since this homelab cluster runs `--disable traefik` and there is no
public ingress for any observability UI).

The cluster-egress story for this stack is deliberately small:
Prometheus does not scrape across the cluster boundary, the operator
talks only to the kube-apiserver, and Grafana has no external
datasources configured. The diagram therefore has no external nodes —
P5's observability is in-cluster end to end.

What this diagram deliberately does not show: log aggregation (no
Loki — deferred per bridge §4.5), distributed tracing (no Tempo — no
workload emits OpenTelemetry spans cleanly today), and custom
PrometheusRule resources (none today — the ~30 rules visible in the
cluster are the chart's defaults; workload-specific rules are PR-E
scope).

Supports: BLS-PLATFORM-ENGINEERING-GUIDE.md §4 (P5 observability +
security depth view); ADR-006 (observability GitOps deployment);
ADR-009 (NetworkPolicy scope — the llm-gateway scrape edge crosses
the NetworkPolicy-enforced namespace boundary, allowed by the
gateway-policy ingress rule).

Stable prefix: 06. Filename and prefix must not change once committed
— external references depend on it (per docs/diagrams/README.md
naming rule).
"""

from diagrams import Cluster, Diagram, Edge
from diagrams.k8s.compute import Pod
from diagrams.k8s.controlplane import APIServer, Kubelet
from diagrams.k8s.network import Service
from diagrams.k8s.others import CRD
from diagrams.onprem.client import User
from diagrams.onprem.monitoring import Grafana, Prometheus, PrometheusOperator
from diagrams.programming.framework import Fastapi


graph_attr = {
    "splines": "spline",
    "fontsize": "16",
    "labelloc": "t",
    "rankdir": "LR",
    "nodesep": "0.6",
    "ranksep": "1.0",
}

with Diagram(
    "P5 — Observability data flow",
    filename="06-observability-data-flow",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
):
    # ---------------- scrape sources (left) ----------------
    with Cluster("Scrape targets — monitoring namespace"):
        t_apiserver = APIServer("apiserver")
        t_coredns = Service("coredns\n(kube-system)")
        t_kubelet = Kubelet("kubelet\n(per node)")
        t_ksm = Pod("kube-state-metrics")
        t_nodeexp = Pod("node-exporter\n(DaemonSet)")
        t_prom_self = Pod("prometheus\n(self-scrape)")
        t_operator_self = Pod("operator\n(self-scrape)")

    with Cluster("Scrape target — llm-gateway namespace"):
        t_gateway = Fastapi("llm-gateway\n(/metrics on :8000)")

    # ---------------- Prometheus stack (centre) ----------------
    with Cluster("Prometheus stack — monitoring namespace"):
        prom = Prometheus("Prometheus\n(StatefulSet, retention 7d / 5GB)")
        operator = PrometheusOperator("prometheus-operator\n(Deployment)")

        with Cluster("CRDs (declarative config)"):
            sm_crd = CRD("ServiceMonitor\n(× 9 in cluster)")
            rule_crd = CRD("PrometheusRule\n(× ~30 chart defaults;\nworkload rules deferred → PR-E)")

    # ---------------- consumers (right) ----------------
    with Cluster("Consumers"):
        grafana = Grafana("Grafana\n(dashboards;\nalso self-scraped, see edge)")
        alertmanager = Pod(
            "AlertManager\n(DISABLED in chart values —\nrules fire to Prom UI only;\nre-enable tracked → PR-E)"
        )
        operator_human = User("Operator\n(kubectl port-forward —\nthe only inbound surface)")

    # ---------------- scrape edges ----------------
    # All scrape sources land in Prometheus on dotted edges (the
    # convention used in diagrams 01 and 03 for observe/scrape flows).
    scrape_style = {"style": "dotted", "color": "darkgreen"}
    for source in [t_apiserver, t_coredns, t_kubelet, t_ksm,
                   t_nodeexp, t_prom_self, t_operator_self, t_gateway]:
        source >> Edge(label="scrape /metrics\nevery 30s", **scrape_style) >> prom

    # Grafana is also a scrape target (it exposes its own /metrics).
    # Rendered separately so the right-column placement reads cleanly.
    grafana >> Edge(label="scrape\n(self)", **scrape_style) >> prom

    # ---------------- CRD-driven configuration ----------------
    # Operator watches CRDs and reconciles Prometheus's scrape and rule
    # configuration from them. Rendered dashed because the relationship
    # is configuration-time, not request-time.
    config_edge = Edge(style="dashed", color="darkblue")
    operator >> Edge(label="watches", style="dashed", color="darkblue") >> sm_crd
    operator >> Edge(label="watches", style="dashed", color="darkblue") >> rule_crd
    sm_crd >> Edge(label="configures\nscrapes", style="dashed", color="darkblue") >> prom
    rule_crd >> Edge(label="configures\nrules", style="dashed", color="darkblue") >> prom

    # ---------------- data-out edges ----------------
    prom >> Edge(label="PromQL queries", color="darkorange") >> grafana

    # Alertmanager is rendered with a deliberately greyed/dashed edge
    # to signal "would route, but disabled in this deployment". This
    # is the gap PR-E closes (workload-specific rules + an explicit
    # scope decision on whether to re-enable Alertmanager).
    prom >> Edge(
        label="would route fires\n(disabled — PR-E)",
        style="dashed",
        color="grey",
    ) >> alertmanager

    # Operator human reads via kubectl port-forward. This bypasses
    # NetworkPolicy entirely (apiserver-mediated tunnel, not pod-to-pod
    # IP traffic), which is why the observability UIs are reachable
    # despite the cluster running no public Ingress.
    operator_human >> Edge(
        label="kubectl port-forward",
        style="dotted",
        color="darkred",
    ) >> grafana
    operator_human >> Edge(
        label="kubectl port-forward",
        style="dotted",
        color="darkred",
    ) >> prom
