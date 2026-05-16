"""
02 — Azure Landing Zone topology (P1).

Topology view of the Project 1 Azure Landing Zone. Hub-spoke VNet
pair under a single resource group, NSGs at subnet scope, Log
Analytics for diagnostics, and a Storage Account holding remote
Terraform state. The diagram shows the peering edge and the
diagnostic-log flows but deliberately omits resource policy
attachments and tagging — those live in ADR-001 and the Terraform
module READMEs respectively.

Supports: BLS-PLATFORM-ENGINEERING-GUIDE.md §4 (P1 landing zone).

Stable prefix: 02. Do not renumber.
"""

from diagrams import Cluster, Diagram, Edge
from diagrams.azure.analytics import LogAnalyticsWorkspaces
from diagrams.azure.general import Resource, Subscriptions
from diagrams.azure.network import (
    NetworkSecurityGroupsClassic,
    Subnets,
    VirtualNetworks,
)
from diagrams.azure.security import KeyVaults
from diagrams.azure.storage import StorageAccounts


graph_attr = {
    "splines": "spline",
    "fontsize": "16",
    "labelloc": "t",
}

with Diagram(
    "P1 — Azure Landing Zone topology",
    filename="02-landing-zone-topology",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
):
    with Cluster("Subscription"):
        sub = Subscriptions("Azure subscription")

        with Cluster("rg-bls-platform (resource group)"):
            rg = Resource("rg-bls-platform")

            with Cluster("Hub VNet  10.0.0.0/16"):
                hub_vnet = VirtualNetworks("hub-vnet")
                with Cluster("hub-management subnet  10.0.1.0/24"):
                    hub_mgmt_subnet = Subnets("subnet:\nmanagement")
                    hub_nsg = NetworkSecurityGroupsClassic("nsg-hub-mgmt")
                    hub_nsg >> Edge(style="dashed", label="attached") >> hub_mgmt_subnet

            with Cluster("Spoke VNet  10.1.0.0/16"):
                spoke_vnet = VirtualNetworks("spoke-vnet")
                with Cluster("spoke-workloads subnet  10.1.1.0/24"):
                    spoke_subnet = Subnets("subnet:\nworkloads")
                    spoke_nsg = NetworkSecurityGroupsClassic("nsg-spoke-workloads")
                    spoke_nsg >> Edge(style="dashed", label="attached") >> spoke_subnet

            with Cluster("Observability"):
                la = LogAnalyticsWorkspaces("log-bls-platform\n(Log Analytics)")

            with Cluster("State + secrets"):
                tfstate = StorageAccounts("st-bls-tfstate\n(remote Terraform state)")
                kv = KeyVaults("kv-bls-platform")

    # Peering between hub and spoke (bidirectional in Azure;
    # rendered as a single labelled edge)
    hub_vnet >> Edge(label="VNet peering\n(bidirectional)", color="darkorange") >> spoke_vnet

    # Diagnostic settings — NSGs and VNets ship logs to Log Analytics
    hub_nsg >> Edge(style="dotted", label="diag logs") >> la
    spoke_nsg >> Edge(style="dotted", label="diag logs") >> la
    hub_vnet >> Edge(style="dotted") >> la
    spoke_vnet >> Edge(style="dotted") >> la

    # Containment edges (informational — show RG owns the assets)
    sub >> Edge(style="invis") >> rg
    rg >> Edge(style="invis") >> hub_vnet
    rg >> Edge(style="invis") >> spoke_vnet
    rg >> Edge(style="invis") >> la
    rg >> Edge(style="invis") >> tfstate
    rg >> Edge(style="invis") >> kv
