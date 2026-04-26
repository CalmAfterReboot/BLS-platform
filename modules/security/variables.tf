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
  description = "Name of the resource group to deploy security resources into"
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources"
}

variable "allowed_locations" {
  type        = list(string)
  default     = ["uksouth"]
  description = "Azure regions permitted by the Allowed Locations policy assignment"
}

variable "contributor_object_id" {
  type        = string
  default     = ""
  description = "Entra ID object ID of a user or group to assign the Contributor role; leave empty to skip"
}

variable "reader_object_id" {
  type        = string
  default     = ""
  description = "Entra ID object ID of a user or group to assign the Reader role; leave empty to skip"
}
