output "policy_allowed_locations_id" {
  value       = azurerm_resource_group_policy_assignment.allowed_locations.id
  description = "Resource ID of the Allowed Locations policy assignment"
}

output "policy_require_environment_tag_id" {
  value       = azurerm_resource_group_policy_assignment.require_environment_tag.id
  description = "Resource ID of the Require environment tag policy assignment"
}

output "policy_require_managed_by_tag_id" {
  value       = azurerm_resource_group_policy_assignment.require_managed_by_tag.id
  description = "Resource ID of the Require managed_by tag policy assignment"
}
