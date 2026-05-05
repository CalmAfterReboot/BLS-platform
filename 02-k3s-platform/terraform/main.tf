resource "proxmox_virtual_environment_vm" "control_plane" {
  for_each = local.control_plane_nodes

  name      = each.key
  node_name = var.proxmox_node
  vm_id     = each.value.vm_id
  on_boot   = true

  clone {
    vm_id = var.template_vm_id
    full  = true
  }

  agent {
    enabled = true
  }

  cpu {
    cores = each.value.vcpus
    type  = "host"
    units = 512
  }

  memory {
    dedicated = each.value.memory_mb
  }

  disk {
    datastore_id = var.storage
    interface    = "scsi0"
    size         = each.value.disk_gb
    discard      = "on"
  }

  network_device {
    bridge  = var.network_bridge
    vlan_id = var.vlan_tag
  }

  initialization {
    datastore_id = var.storage

    ip_config {
      ipv4 {
        address = "${each.value.ip}/24"
        gateway = var.gateway
      }
    }

    dns {
      servers = var.dns_servers
    }

    user_account {
      username = var.cloud_init_user
      keys     = [var.ssh_public_key]
    }
  }
}

resource "proxmox_virtual_environment_vm" "worker" {
  for_each = local.worker_nodes

  name      = each.key
  node_name = var.proxmox_node
  vm_id     = each.value.vm_id
  on_boot   = true

  clone {
    vm_id = var.template_vm_id
    full  = true
  }

  agent {
    enabled = true
  }

  cpu {
    cores = each.value.vcpus
    type  = "host"
    units = 512
  }

  memory {
    dedicated = each.value.memory_mb
  }

  disk {
    datastore_id = var.storage
    interface    = "scsi0"
    size         = each.value.disk_gb
    discard      = "on"
  }

  network_device {
    bridge  = var.network_bridge
    vlan_id = var.vlan_tag
  }

  initialization {
    datastore_id = var.storage

    ip_config {
      ipv4 {
        address = "${each.value.ip}/24"
        gateway = var.gateway
      }
    }

    dns {
      servers = var.dns_servers
    }

    user_account {
      username = var.cloud_init_user
      keys     = [var.ssh_public_key]
    }
  }
}
