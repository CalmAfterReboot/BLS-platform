# Azure Policy and RBAC for the BLS landing zone resource group.
# Policy assignments are scoped to the resource group — subscription-scope assignments
# are out of scope until a management group hierarchy is built in a later project.

data "azurerm_client_config" "current" {}

locals {
  resource_group_id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.resource_group_name}"
}

resource "azurerm_resource_group_policy_assignment" "allowed_locations" {
  name                 = "${var.resource_prefix}-pol-locations"
  resource_group_id    = local.resource_group_id
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/e56962a6-4747-49cd-b67b-bf8b01975c4c"
  display_name         = "Allowed locations — BLS Landing Zone"
  description          = "Restricts resource deployment to approved Azure regions"

  parameters = jsonencode({
    listOfAllowedLocations = {
      value = var.allowed_locations
    }
  })
}

resource "azurerm_resource_group_policy_assignment" "require_environment_tag" {
  name                 = "${var.resource_prefix}-pol-env-tag"
  resource_group_id    = local.resource_group_id
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/871b6d14-10aa-478d-b590-94f262ecfa99"
  display_name         = "Require environment tag — BLS Landing Zone"
  description          = "Audits resources missing the environment tag"

  parameters = jsonencode({
    tagName = {
      value = "environment"
    }
  })
}

resource "azurerm_resource_group_policy_assignment" "require_managed_by_tag" {
  name                 = "${var.resource_prefix}-pol-mgdby-tag"
  resource_group_id    = local.resource_group_id
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/871b6d14-10aa-478d-b590-94f262ecfa99"
  display_name         = "Require managed_by tag — BLS Landing Zone"
  description          = "Audits resources missing the managed_by tag"

  parameters = jsonencode({
    tagName = {
      value = "managed_by"
    }
  })
}

resource "azurerm_role_assignment" "contributor" {
  count                = var.contributor_object_id != "" ? 1 : 0
  scope                = local.resource_group_id
  role_definition_name = "Contributor"
  principal_id         = var.contributor_object_id
}

resource "azurerm_role_assignment" "reader" {
  count                = var.reader_object_id != "" ? 1 : 0
  scope                = local.resource_group_id
  role_definition_name = "Reader"
  principal_id         = var.reader_object_id
}
