terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
  }
  backend "azurerm" {
    resource_group_name  = "rg-bls-tfstate"
    storage_account_name = "stblstfstate001"
    container_name       = "tfstate"
    key                  = "03-aks-multicluster.tfstate"
  }
}

provider "azurerm" {
  features {}
}
