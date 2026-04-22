# This file defines what information Terraform exposes after a successful apply.
# Outputs are used by other Terraform projects, CI/CD pipelines, and operators to retrieve key resource identifiers without going into the Azure portal.

output "resource_group_name" {
  value       = azurerm_resource_group.main.name
  description = "Name of the primary resource group"
  # This is referenced by other modules that need to place resources in this resource group
}

output "resource_group_location" {
  value       = azurerm_resource_group.main.location
  description = "Location of the primary resource group"
}

output "vnet_hub_id" {
  value       = module.networking.vnet_hub_id
  description = "Resource ID of the hub VNet"
  # This ID is needed when peering spoke VNets to the hub for network connectivity
}

output "vnet_hub_name" {
  value       = module.networking.vnet_hub_name
  description = "Name of the hub VNet"
}