"""
06 — Observability data flow (P5).

Top-to-bottom data flow for the kube-prometheus-stack:

  Top row:    nine ServiceMonitor scrape sources arranged horizontally.
              Eight live in the `monitoring` namespace; one (`llm-gateway`)
              crosses the namespace boundary and is admitted through the
              ADR-009 NetworkPolicy by the `gateway-policy` ingress rule.

  Middle row: the Prometheus stack — Prometheus (StatefulSet), the
              prometheus-operator, and the ServiceMonitor + PrometheusRule
              CRDs that the operator reconciles into scrape and rule
              configuration. CRD count notes flag the deferred work
              (PR-E: workload-specific rules).

  Bottom row: data consumers. Grafana for dashboards (PromQL queries).
              AlertManager rendered as disabled — the chart values turn
              it off in this deployment and rules fire to the Prometheus
              UI only; re-enable is PR-E scope. The human operator reads
              via `kubectl port-forward` — the only inbound surface on
              this cluster (it runs `--disable traefik`, no Ingress
              controller).

What this diagram deliberately doesn't show: log aggregation (no Loki
— see bridge §4.5), distributed tracing (no Tempo), and workload-specific
PrometheusRule resources (the ~30 visible rules are chart defaults).
The scrape-edge label "scrape /metrics every 30s" is set once on the
source cluster's title rather than repeated nine times on each edge.

Supports: BLS-PLATFORM-ENGINEERING-GUIDE.md §4.5 (P5 observability +
security depth view); ADR-006 (observability GitOps deployment);
ADR-009 (NetworkPolicy scope).

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
    "fontsize": "18",
    "labelloc": "t",
    "rankdir": "TB",
    "nodesep": "0.5",
    "ranksep": "1.2",
    "pad": "0.6",
}

source_cluster_attr = {
    "rankdir": "LR",   # lay the 9 source icons out in a horizontal row
    "fontsize": "14",
    "style": "rounded,filled",
    "fillcolor": "#f0f9ff",
}

prom_cluster_attr = {
    "fontsize": "14",
    "style": "rounded,filled",
    "fillcolor": "#fef3c7",
}

consumer_cluster_attr = {
    "rankdir": "LR",
    "fontsize": "14",
    "style": "rounded,filled",
    "fillcolor": "#f0fdf4",
}

with Diagram(
    "P5 — Observability data flow",
    filename="06-observability-data-flow",
    show=False,
    direction="TB",
    graph_attr=graph_attr,
):
    # ---------------- TOP: scrape sources (single cluster, horizontal) ----------------
    # Scrape edge label lives in the cluster title — the nine individual
    # edges then carry no repeated text.
    with Cluster(
        "9 scrape targets — Prometheus scrapes /metrics every 30s",
        graph_attr=source_cluster_attr,
    ):
        t_apiserver = APIServer("apiserver")
        t_coredns = Service("coredns")
        t_kubelet = Kubelet("kubelet\n(per node)")
        t_ksm = Pod("kube-state-\nmetrics")
        t_nodeexp = Pod("node-exporter\n(per node)")
        t_prom_self = Pod("prometheus\n(self)")
        t_op_self = Pod("operator\n(self)")
        t_grafana_self = Grafana("grafana\n(self)")
        t_gateway = Fastapi("llm-gateway\n(cross-ns,\nadmitted by\nADR-009)")

    sources = [
        t_apiserver, t_coredns, t_kubelet, t_ksm, t_nodeexp,
        t_prom_self, t_op_self, t_grafana_self, t_gateway,
    ]

    # ---------------- MIDDLE: Prometheus stack (flat, no sub-cluster) ----------------
    with Cluster(
        "Prometheus stack — monitoring namespace",
        graph_attr=prom_cluster_attr,
    ):
        prom = Prometheus("Prometheus\n(StatefulSet · 7d / 5GB)")
        operator = PrometheusOperator("prometheus-operator")
        sm_crd = CRD("ServiceMonitor\n× 9")
        rule_crd = CRD("PrometheusRule\n× ~30 chart defaults\n(workload rules → PR-E)")

    # ---------------- BOTTOM: consumers (single cluster, horizontal) ----------------
    with Cluster(
        "Consumers",
        graph_attr=consumer_cluster_attr,
    ):
        grafana = Grafana("Grafana\n(dashboards)")
        alertmanager = Pod(
            "AlertManager\n(disabled in chart values —\nrules fire to Prom UI only;\nPR-E scope)"
        )
        operator_human = User(
            "Operator\n(kubectl port-forward —\nonly inbound surface;\ncluster has --disable traefik)"
        )

    # ---------------- edges ----------------
    # 1) Nine scrape edges — no per-edge label (cluster title carries the
    #    text). Dotted green, the convention for scrape/observe flows.
    scrape_edge = Edge(style="dotted", color="darkgreen")
    for source in sources:
        source >> scrape_edge >> prom

    # 2) Operator watches CRDs; CRDs configure Prometheus. Dashed blue —
    #    configuration-time, not request-time.
    operator >> Edge(label="watches", style="dashed", color="darkblue") >> sm_crd
    operator >> Edge(label="watches", style="dashed", color="darkblue") >> rule_crd
    sm_crd >> Edge(label="configures\nscrapes", style="dashed", color="darkblue") >> prom
    rule_crd >> Edge(label="configures\nrules", style="dashed", color="darkblue") >> prom

    # 3) Prometheus → consumers.
    prom >> Edge(label="PromQL queries", color="darkorange") >> grafana
    prom >> Edge(
        label="would route fires\n(disabled — PR-E)",
        style="dashed",
        color="grey",
    ) >> alertmanager

    # 4) Operator-human reads via kubectl port-forward — bypasses
    #    NetworkPolicy entirely (apiserver-mediated tunnel, not pod-to-pod
    #    IP traffic). Rendered as a single fan-out to both UIs.
    operator_human >> Edge(
        label="port-forward",
        style="dotted",
        color="darkred",
    ) >> [grafana, prom]
