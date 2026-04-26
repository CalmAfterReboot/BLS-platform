# This file defines all input variables for the landing zone project.

variable "location" {
  type        = string
  default     = "uksouth"
  description = "Azure region for all resources"
  # uksouth is the default because it ensures data residency within the UK and is the closest Azure region for UK-based operations
}

variable "environment" {
  type        = string
  default     = "dev"
  description = "Environment name used in resource naming and tagging"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod"
  }
  # Validation blocks prevent accidental deploys to wrong environments
}

variable "project_name" {
  type        = string
  default     = "bls-landing-zone"
  description = "Project name used in resource naming conventions"
}

variable "tags" {
  type = map(string)
  default = {
    environment = "dev"
    project     = "bls-landing-zone"
    owner       = "BLS"
    managed_by  = "terraform"
  }
  description = "Default tags applied to all resources"
  # Tagging everything is mandatory in production for cost allocation, resource management, and governance compliance
}
variable "allowed_locations" {
  type        = list(string)
  default     = ["uksouth", "ukwest"]
  description = "Azure regions permitted by the Allowed Locations policy assignment"
}
