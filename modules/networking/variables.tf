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
  description = "Name of the resource group to deploy networking resources into"
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources"
}
