output "workspace_id" {
  value       = azurerm_log_analytics_workspace.main.id
  description = "Resource ID of the Log Analytics workspace — pass to modules that emit diagnostic settings"
}

output "workspace_name" {
  value       = azurerm_log_analytics_workspace.main.name
  description = "Name of the Log Analytics workspace"
}

output "workspace_guid" {
  value       = azurerm_log_analytics_workspace.main.workspace_id
  description = "GUID of the Log Analytics workspace — used by VM agents and Data Collection Rules"
}

output "primary_shared_key" {
  value       = azurerm_log_analytics_workspace.main.primary_shared_key
  sensitive   = true
  description = "Primary shared key for agent authentication. Prefer managed identity + DCR over key-based auth where possible."
}
