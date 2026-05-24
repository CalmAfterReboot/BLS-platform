terraform {
  required_version = ">= 1.9.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.66.3"
    }
  }

  # Partial backend — actual storage account and container live in
  # `backend.tfbackend` (gitignored). Initialise with:
  #   terraform init -backend-config=backend.tfbackend
  # See `backend.tfbackend.example` for the expected shape.
  backend "azurerm" {}
}
