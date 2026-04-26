# This is the root module for the BLS Landing Zone.
# It orchestrates all child modules and defines the core infrastructure resources.

locals {
  resource_prefix = "${var.project_name}-${var.environment}"
  # Locals create reusable values to enforce consistent naming across all resources without repeating yourself
}

resource "azurerm_resource_group" "main" {
  name     = "${local.resource_prefix}-rg"
  location = var.location
  tags     = var.tags
  # All landing zone resources live in this resource group, and the name uses the local prefix to enforce naming convention
}

module "networking" {
  source = "../../modules/networking"

  location            = var.location
  environment         = var.environment
  resource_prefix     = local.resource_prefix
  resource_group_name = azurerm_resource_group.main.name
  tags                = var.tags
  # The networking module creates the hub VNet, spoke VNet, peering, and NSGs
}

module "security" {
  source = "../../modules/security"

  location              = var.location
  environment           = var.environment
  resource_prefix       = local.resource_prefix
  resource_group_name   = azurerm_resource_group.main.name
  tags                  = var.tags
  allowed_locations     = var.allowed_locations
}
