# This file configures the Azure provider and remote state backend for the landing zone project.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-bls-tfstate"                       # The Azure resource group where the storage account resides
    storage_account_name = "stblstfstate001"                      # The name of the Azure storage account for storing Terraform state
    container_name       = "tfstate"                              # The name of the blob container within the storage account
    key                  = "projects/01-landing-zone/dev.tfstate" # The path/key for the Terraform state file in the container
  }
}

provider "azurerm" {
  features {}
}
