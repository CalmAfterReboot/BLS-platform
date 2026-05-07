resource "azurerm_resource_group" "aks" {
  name     = "rg-bls-aks-demo"
  location = "uksouth"
}

resource "azurerm_kubernetes_cluster" "aks" {
  name                = "bls-aks-demo"
  location            = azurerm_resource_group.aks.location
  resource_group_name = azurerm_resource_group.aks.name
  dns_prefix          = "bls-aks-demo"

  default_node_pool {
    name       = "system"
    node_count = 1
    vm_size    = "Standard_D2pls_v6"
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin = "kubenet"
  }
}
