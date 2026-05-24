variable "proxmox_api_endpoint" {
  description = "Proxmox VE API endpoint URL"
  type        = string
}

variable "proxmox_api_token" {
  description = "Proxmox VE API token (format: USER@REALM!TOKENID=SECRET)"
  type        = string
  sensitive   = true
}

variable "proxmox_node" {
  description = "Proxmox VE node name"
  type        = string
  default     = "proxmox"
}

variable "proxmox_ssh_user" {
  description = "SSH user for Proxmox node direct access"
  type        = string
  default     = "root"
}

variable "proxmox_ssh_password" {
  description = "SSH password for Proxmox node direct access"
  type        = string
  sensitive   = true
}

variable "template_vm_id" {
  description = "VM ID of the Ubuntu 24.04 cloud-init template"
  type        = number
  default     = 9000
}

variable "storage" {
  description = "Proxmox storage pool for VM disks and cloud-init drives"
  type        = string
  default     = "local-lvm"
}

variable "network_bridge" {
  description = "Network bridge for VM network interfaces"
  type        = string
  default     = "VLAN"
}

variable "vlan_tag" {
  description = "VLAN tag for VM network interfaces. Provide via terraform.tfvars (gitignored)."
  type        = number
}

variable "gateway" {
  description = "Default gateway for VMs. Provide via terraform.tfvars (gitignored)."
  type        = string
}

variable "dns_servers" {
  description = "DNS servers for VMs. Provide via terraform.tfvars (gitignored)."
  type        = list(string)
}

variable "control_plane_node_ips" {
  description = "Map of control-plane hostname to IP address (e.g. {\"k3s-control-01\" = \"<homelab-subnet>.10\"}). Provide via terraform.tfvars (gitignored)."
  type        = map(string)
}

variable "worker_node_ips" {
  description = "Map of worker hostname to IP address (e.g. {\"k3s-worker-01\" = \"<homelab-subnet>.20\"}). Provide via terraform.tfvars (gitignored)."
  type        = map(string)
}

variable "cloud_init_user" {
  description = "Cloud-init default user for Ansible management"
  type        = string
  default     = "ansible"
}

variable "ssh_public_key" {
  description = "SSH public key to inject via cloud-init for the ansible user"
  type        = string
  sensitive   = true
}
