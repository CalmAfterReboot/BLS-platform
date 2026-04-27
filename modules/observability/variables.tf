variable "location" {
  type        = string
  description = "Azure region for all resources"
}

variable "environment" {
  type        = string
  description = "Environment name used in resource naming and tagging"
}

variable "resource_prefix" {
  type        = string
  description = "Prefix for resource naming, typically project-environment"
}

variable "resource_group_name" {
  type        = string
  description = "Name of the resource group to deploy observability resources into"
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources"
}

variable "retention_in_days" {
  type        = number
  default     = 30
  description = "Number of days to retain log data in the workspace. Min 30, max 730."

  validation {
    condition     = var.retention_in_days >= 30 && var.retention_in_days <= 730
    error_message = "retention_in_days must be between 30 and 730."
  }
}

variable "daily_quota_gb" {
  type        = number
  default     = -1
  description = "Daily ingestion cap in GB. -1 disables the cap. CKV_AZURE_84 (MEDIUM) fires on -1 — set a positive value to silence it in environments with cost controls."
}

variable "internet_ingestion_enabled" {
  type        = bool
  default     = false
  description = "Allow log ingestion from the public internet. Azure-native diagnostic settings use the backbone and are unaffected by this flag; only external agents (on-prem, non-Azure VMs) are blocked. Set true until Azure Monitor Private Link Scope (AMPLS) is deployed."
}

variable "internet_query_enabled" {
  type        = bool
  default     = false
  description = "Allow log queries from the public internet. Set true to allow portal/workstation queries before AMPLS is deployed."
}
