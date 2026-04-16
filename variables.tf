variable "pm_api_token_secret" {
  description = "Proxmox API token secret"
  sensitive   = true
}

variable "vm_name" {
  description = "Name of the VM"
  default     = "ubuntu-vm-01"
}

variable "vm_cores" {
  description = "Number of CPU cores"
  default     = 2
}

variable "vm_memory" {
  description = "RAM in MB"
  default     = 2048
}

variable "vm_disk_size" {
  description = "Disk size"
  default     = "20G"
}

variable "vm_user" {
  description = "Default cloud-init username"
  default     = "ubuntu"
}

variable "vm_password" {
  description = "Default cloud-init password"
  sensitive   = true
}

variable "ssh_public_key" {
  description = "SSH public key for VM access"
  default     = ""
}
