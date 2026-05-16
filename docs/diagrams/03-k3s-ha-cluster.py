"""
03 — k3s HA cluster topology (P2).

Topology view of the Project 2 k3s high-availability cluster on
Proxmox. Three control-plane nodes share a kube-vip-managed virtual
IP; two worker nodes carry the workload pods. All five nodes have
the Ansible node-hardening role applied (annotated as a banner). The
ArgoCD installation that drives every subsequent project (P3 onward)
runs in-cluster.

The kube-vip VIP and any VLAN identifiers are rendered as
placeholders — the cluster runs on a private LAN and concrete IPs /
VLANs are deliberately not committed to public artefacts.

Supports: BLS-PLATFORM-ENGINEERING-GUIDE.md §4 (P2 k3s platform);
ADR-002 (homelab over cloud-only), ADR-003 (Ansible over cloud-init).

Stable prefix: 03. Do not renumber.
"""

from diagrams import Cluster, Diagram, Edge
from diagrams.k8s.compute import Pod
from diagrams.k8s.infra import ETCD, Master, Node
from diagrams.k8s.network import Service
from diagrams.onprem.gitops import ArgoCD
from diagrams.onprem.iac import Ansible
from diagrams.onprem.proxmox import Pve


graph_attr = {
    "splines": "spline",
    "fontsize": "16",
    "labelloc": "t",
    "rankdir": "TB",
}

with Diagram(
    "P2 — k3s HA cluster on Proxmox",
    filename="03-k3s-ha-cluster",
    show=False,
    direction="TB",
    graph_attr=graph_attr,
):
    # The hardening banner — applies to all five nodes
    with Cluster("Node hardening (applied to every node)"):
        hardening = Ansible(
            "ansible: node-hardening role\n"
            "(SSH lockdown, ufw, fail2ban,\nunattended-upgrades, kernel tuning)"
        )

    with Cluster("Proxmox hypervisor (private LAN, VLAN-X / VLAN-Y)"):
        with Cluster("Control plane (HA via kube-vip)"):
            vip = Service("kube-vip VIP\n<vip-ip>:6443")
            cp1 = Master("k3s-cp-1")
            cp2 = Master("k3s-cp-2")
            cp3 = Master("k3s-cp-3")
            etcd = ETCD("embedded etcd\n(quorum across cp-1..3)")

            vip >> Edge(label="floats across", style="dashed") >> [cp1, cp2, cp3]
            [cp1, cp2, cp3] >> Edge(style="dotted") >> etcd

        with Cluster("Workers"):
            w1 = Node("k3s-worker-1")
            w2 = Node("k3s-worker-2")

        with Cluster("namespace: argocd"):
            argocd = ArgoCD("ArgoCD\n(installed via Helm,\nbootstraps every later project)")

    # Logical hosting — workers host most pods (incl. argocd, in practice)
    [w1, w2] >> Edge(label="hosts", style="dotted") >> argocd

    # Hardening edge (rendered loosely — applies to all)
    hardening >> Edge(style="dotted", label="applied to") >> cp1
    hardening >> Edge(style="dotted") >> w1

    # External Proxmox hypervisor context (renders above)
    proxmox = Pve("Proxmox host\n(hypervisor)")
    proxmox >> Edge(label="virtualises", style="dashed") >> cp1
    proxmox >> Edge(style="invis") >> w1
