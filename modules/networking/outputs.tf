output "vnet_hub_id" {
  value       = azurerm_virtual_network.hub.id
  description = "Resource ID of the hub VNet"
}

output "vnet_hub_name" {
  value       = azurerm_virtual_network.hub.name
  description = "Name of the hub VNet"
}

output "vnet_spoke_id" {
  value       = azurerm_virtual_network.spoke.id
  description = "Resource ID of the spoke VNet"
}

output "vnet_spoke_name" {
  value       = azurerm_virtual_network.spoke.name
  description = "Name of the spoke VNet"
}

output "management_subnet_id" {
  value       = azurerm_subnet.management.id
  description = "Resource ID of the management subnet"
}

output "workload_subnet_id" {
  value       = azurerm_subnet.workload.id
  description = "Resource ID of the workload subnet"
}

output "log_analytics_workspace_id" {
  value       = azurerm_log_analytics_workspace.main.id
  description = "Resource ID of the Log Analytics workspace — consumed by other modules until the observability module is built in Project 04"
}
