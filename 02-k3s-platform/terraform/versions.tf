terraform {
  required_version = ">= 1.9.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.66.3"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-bls-tfstate"
    storage_account_name = "stblstfstate001"
    container_name       = "tfstate"
    key                  = "k3s-proxmox.tfstate"
  }
}
