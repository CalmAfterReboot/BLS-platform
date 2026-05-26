terraform {
  backend "azurerm" {
    # Partial config: storage account, container, RG are supplied at
    # init time via `terraform init -backend-config=backend.tfbackend`.
    # See backend.tfbackend.example for the expected keys.
    key = "projects/06-platform-hardening/cloudflare/dev.tfstate"
  }
}
