terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
  }
  # Partial backend — actual storage account and container live in
  # `backend.tfbackend` (gitignored). Initialise with:
  #   terraform init -backend-config=backend.tfbackend
  # See `backend.tfbackend.example` for the expected shape.
  backend "azurerm" {}
}

provider "azurerm" {
  features {}
}
