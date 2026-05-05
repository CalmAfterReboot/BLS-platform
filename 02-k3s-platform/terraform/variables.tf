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
  description = "VLAN tag for VM network interfaces"
  type        = number
  default     = 200
}

variable "gateway" {
  description = "Default gateway for VMs"
  type        = string
  default     = "192.168.200.1"
}

variable "dns_servers" {
  description = "DNS servers for VMs"
  type        = list(string)
  default     = ["192.168.200.1", "1.1.1.1"]
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
