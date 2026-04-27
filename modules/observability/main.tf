# Centralised Log Analytics workspace for the BLS landing zone.
# All modules that emit diagnostic settings consume this workspace's ID as an input
# rather than creating their own — prevents fragmented log data across workspaces.

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.resource_prefix}-law"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = var.retention_in_days
  daily_quota_gb      = var.daily_quota_gb

  # Azure-native diagnostic settings route via the backbone and are unaffected by
  # these flags. Only external agents (on-prem, non-Azure VMs connecting over public
  # internet) are gated here. Both default to false; override once AMPLS is deployed.
  internet_ingestion_enabled = var.internet_ingestion_enabled
  internet_query_enabled     = var.internet_query_enabled

  tags = var.tags
}
