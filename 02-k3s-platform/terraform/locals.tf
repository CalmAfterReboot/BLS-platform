locals {
  # IPs are sourced from `var.control_plane_node_ips` and
  # `var.worker_node_ips` so no homelab-subnet address is committed to
  # git. Real values live in `terraform.tfvars` (gitignored); see
  # `terraform.tfvars.example` for the expected shape.

  control_plane_nodes = {
    "k3s-control-01" = {
      vm_id     = 201
      ip        = var.control_plane_node_ips["k3s-control-01"]
      vcpus     = 2
      memory_mb = 4096
      disk_gb   = 32
    }
    "k3s-control-02" = {
      vm_id     = 202
      ip        = var.control_plane_node_ips["k3s-control-02"]
      vcpus     = 2
      memory_mb = 4096
      disk_gb   = 32
    }
    "k3s-control-03" = {
      vm_id     = 203
      ip        = var.control_plane_node_ips["k3s-control-03"]
      vcpus     = 2
      memory_mb = 4096
      disk_gb   = 32
    }
  }

  worker_nodes = {
    "k3s-worker-01" = {
      vm_id     = 204
      ip        = var.worker_node_ips["k3s-worker-01"]
      vcpus     = 2
      memory_mb = 16384
      disk_gb   = 80
    }
    "k3s-worker-02" = {
      vm_id     = 205
      ip        = var.worker_node_ips["k3s-worker-02"]
      vcpus     = 2
      memory_mb = 16384
      disk_gb   = 80
    }
  }
}
