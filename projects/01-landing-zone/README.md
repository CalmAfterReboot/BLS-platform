# Project 01 — Azure Landing Zone

A production-grade Azure landing zone built with Terraform, implementing hub-spoke network topology, NSG security baselines, Azure Policy governance, and centralised diagnostic logging. Deployed to UK South via remote state in Azure Blob Storage.

---

## Architecture

```
Subscription: BLS (<subscription-id>)
└── Resource Group: bls-landing-zone-dev-rg (uksouth)
    ├── Networking
    │   ├── Hub VNet: 10.0.0.0/16
    │   │   ├── GatewaySubnet:       10.0.0.0/27  (no NSG — Azure requirement)
    │   │   ├── AzureFirewallSubnet: 10.0.1.0/26  (no NSG — Azure requirement)
    │   │   └── ManagementSubnet:    10.0.2.0/24  ← NSG: deny-all baseline
    │   ├── Spoke VNet: 10.1.0.0/16
    │   │   └── WorkloadSubnet:      10.1.0.0/24  ← NSG: deny-all baseline
    │   └── VNet Peering (bidirectional)
    ├── Security
    │   ├── Policy: Allowed locations (uksouth, ukwest)
    │   ├── Policy: Require environment tag (audit)
    │   └── Policy: Require managed_by tag (audit)
    └── Observability
        └── Log Analytics Workspace (30-day retention)
            ├── Diagnostic: hub VNet metrics
            ├── Diagnostic: spoke VNet metrics
            ├── Diagnostic: management NSG events + rule counters
            └── Diagnostic: workload NSG events + rule counters
```

**Remote state:** Azure Storage account (name redacted) / `tfstate` container / `projects/01-landing-zone/dev.tfstate`

---

## Module Structure

```
modules/
├── networking/   Hub-spoke VNets, subnets, peering, NSGs, diagnostic settings, LAW
└── security/     Azure Policy assignments, RBAC role assignments (stubbed)

projects/
└── 01-landing-zone/
    ├── main.tf           Root module — wires networking and security modules
    ├── variables.tf      Input declarations
    ├── outputs.tf        Exposes RG name/location and hub VNet ID/name
    ├── providers.tf      azurerm ~> 3.100, backend config
    └── terraform.tfvars  Dev environment values (gitignored)
```

---

## Design Decisions

**Hub-spoke over flat VNet**
Separates shared infrastructure (gateway, firewall, management) from workload traffic. Enables centralised routing and inspection when Azure Firewall or VPN Gateway is added. GatewaySubnet and AzureFirewallSubnet deliberately have no NSGs — Azure blocks deployment otherwise.

**Deny-all NSG baseline at priority 4096**
All inbound and outbound traffic is blocked by default on ManagementSubnet and WorkloadSubnet. Explicit allow rules must be added at lower priority numbers before any traffic flows. This fails closed — misconfiguration produces no connectivity rather than unintended exposure.

**`lifecycle { ignore_changes = [security_rule] }`** on both NSGs
Prevents Terraform from fighting with Azure Security Center or manual rule additions during development. Without this, any out-of-band rule change triggers a plan diff on every run.

**Policy scoped to resource group, not subscription**
Subscription-scope policy requires a management group hierarchy. RG-scope is correct for a single-project landing zone and sufficient to demonstrate governance in a portfolio context. Management group hierarchy is out of scope until a multi-subscription architecture is built.

**Constructed local resource group ID instead of data source lookup**
`data "azurerm_resource_group"` fails at plan time when the RG doesn't exist yet. Constructing the ID from subscription ID and RG name resolves the dependency without requiring the RG to pre-exist:
```hcl
locals {
  resource_group_id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.resource_group_name}"
}
```

**Log Analytics workspace in the networking module (temporary)**
Diagnostic settings require a workspace ID at deploy time. A permanent centralised observability module is planned for Project 04. The workspace will be migrated and this temporary one removed.

**`allow_gateway_transit = true` on hub peering, `use_remote_gateways = false` on spoke**
`allow_gateway_transit` tells the hub to advertise its gateway to peered spokes. `use_remote_gateways` is false on the spoke because no VPN or ExpressRoute gateway exists yet — enabling it without a deployed gateway causes a plan error. This is the correct staging pattern.

---

## Security Baseline

| Control | Implementation | Effect |
|---|---|---|
| Network segmentation | Hub-spoke with NSG deny-all | Blocks all traffic by default |
| Region restriction | Allowed locations policy | Deny — blocks deployment outside uksouth/ukwest |
| Tag enforcement (environment) | Require tag policy | Audit — flags non-compliant resources |
| Tag enforcement (managed_by) | Require tag policy | Audit — flags non-compliant resources |
| Diagnostic logging | Azure Monitor → Log Analytics | NSG events, VNet metrics captured |

**Policy note:** The tag policies are set to `Audit` (not `Deny`). They surface compliance gaps without blocking deployment — appropriate for a dev environment. Switch `enforce = true` → `enforce = false` in the policy assignment to change to audit-only, or change the policy effect at definition level for deny enforcement.

---

## Known Limitations and Next Steps

- **No Key Vault** — secrets management deferred to Project 02 (CI/CD pipeline introduces the need)
- **No Azure Firewall** — AzureFirewallSubnet reserved, firewall not deployed (cost: ~£800/mo, out of scope for portfolio)
- **No VPN Gateway** — GatewaySubnet reserved, gateway not deployed (cost: ~£100/mo)
- **RBAC assignments stubbed** — `contributor_object_id` and `reader_object_id` variables exist but are empty; role assignments skipped until a service principal for CI/CD is created in the next session
- **Log Analytics temporary** — will be superseded by the centralised observability module in Project 04
- **Single spoke** — production landing zones have multiple spokes per workload class; additional spokes added as portfolio projects grow

---

## Operational Notes

**Authentication** — az login drops every terminal session on the DevVM. Always authenticate before running Terraform:
```bash
az login --tenant <tenant-id> --use-device-code
az account set --subscription <subscription-id>
```

**State lock** — if a plan or apply is interrupted (Ctrl+C), the remote state blob remains locked. Force-unlock with the lock ID shown in the error:
```bash
terraform force-unlock <lock-id>
# Enter: yes (lowercase — Terraform is case-sensitive)
```

**terraform state list** — must be run from `projects/01-landing-zone/`, not the repo root. Remote state is scoped to the project directory.

**Policy assignment latency** — Azure Policy assignments take 60-100 seconds to provision. This is normal and not a Terraform bug.

**Policy definition IDs** — built-in policy definition IDs vary by one character between Azure environments and subscription tiers. Always verify with `az policy definition list` before hardcoding an ID.

---

## Resource Inventory

| Resource | Name | Type |
|---|---|---|
| Resource Group | bls-landing-zone-dev-rg | Microsoft.Resources/resourceGroups |
| Log Analytics Workspace | bls-landing-zone-dev-law | Microsoft.OperationalInsights/workspaces |
| Hub VNet | bls-landing-zone-dev-vnet-hub | Microsoft.Network/virtualNetworks |
| Spoke VNet | bls-landing-zone-dev-vnet-spoke | Microsoft.Network/virtualNetworks |
| GatewaySubnet | GatewaySubnet | subnet |
| AzureFirewallSubnet | AzureFirewallSubnet | subnet |
| ManagementSubnet | ManagementSubnet | subnet |
| WorkloadSubnet | WorkloadSubnet | subnet |
| Hub→Spoke peering | hub-to-spoke | Microsoft.Network/virtualNetworkPeerings |
| Spoke→Hub peering | spoke-to-hub | Microsoft.Network/virtualNetworkPeerings |
| Management NSG | bls-landing-zone-dev-nsg-management | Microsoft.Network/networkSecurityGroups |
| Workload NSG | bls-landing-zone-dev-nsg-workload | Microsoft.Network/networkSecurityGroups |
| NSG association (management) | — | subnet association |
| NSG association (workload) | — | subnet association |
| Diag: hub VNet | bls-landing-zone-dev-diag-hub-vnet | diagnostic setting |
| Diag: spoke VNet | bls-landing-zone-dev-diag-spoke-vnet | diagnostic setting |
| Diag: management NSG | bls-landing-zone-dev-diag-nsg-management | diagnostic setting |
| Diag: workload NSG | bls-landing-zone-dev-diag-nsg-workload | diagnostic setting |
| Policy: allowed locations | bls-landing-zone-dev-pol-locations | Microsoft.Authorization/policyAssignments |
| Policy: environment tag | bls-landing-zone-dev-pol-env-tag | Microsoft.Authorization/policyAssignments |
| Policy: managed_by tag | bls-landing-zone-dev-pol-mgdby-tag | Microsoft.Authorization/policyAssignments |

**Total: 21 resources**

---

## Cost

| Resource | Monthly cost |
|---|---|
| VNets, subnets, peering | £0 |
| NSGs | £0 |
| Log Analytics (<5GB/day free tier) | £0 |
| Azure Policy assignments | £0 |
| Remote state (Blob Storage, LRS) | <£0.01 |
| **Total** | **~£0** |# Pipeline test - Day 5
