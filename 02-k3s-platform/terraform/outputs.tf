output "control_plane_ips" {
  description = "Map of control plane node names to IP addresses"
  value = {
    for name, node in local.control_plane_nodes : name => node.ip
  }
}

output "worker_ips" {
  description = "Map of worker node names to IP addresses"
  value = {
    for name, node in local.worker_nodes : name => node.ip
  }
}

output "first_control_plane_ip" {
  description = "IP address of the first control plane node (k3s bootstrap node)"
  value       = local.control_plane_nodes["k3s-control-01"].ip
}
