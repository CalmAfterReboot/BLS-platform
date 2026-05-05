locals {
  control_plane_nodes = {
    "k3s-control-01" = {
      vm_id     = 201
      ip        = "192.168.200.10"
      vcpus     = 2
      memory_mb = 4096
      disk_gb   = 32
    }
    "k3s-control-02" = {
      vm_id     = 202
      ip        = "192.168.200.11"
      vcpus     = 2
      memory_mb = 4096
      disk_gb   = 32
    }
    "k3s-control-03" = {
      vm_id     = 203
      ip        = "192.168.200.12"
      vcpus     = 2
      memory_mb = 4096
      disk_gb   = 32
    }
  }

  worker_nodes = {
    "k3s-worker-01" = {
      vm_id     = 204
      ip        = "192.168.200.20"
      vcpus     = 2
      memory_mb = 16384
      disk_gb   = 80
    }
    "k3s-worker-02" = {
      vm_id     = 205
      ip        = "192.168.200.21"
      vcpus     = 2
      memory_mb = 16384
      disk_gb   = 80
    }
  }
}
