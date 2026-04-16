# Proxmox Terraform

Terraform configuration for provisioning Ubuntu VMs on a Proxmox homelab using the [bpg/proxmox](https://registry.terraform.io/providers/bpg/proxmox/latest) provider.

## Prerequisites

- Terraform >= 1.0
- Proxmox VE instance with API access
- A VM template (clone source) at VM ID `9000`
- A Proxmox API token for a user with provisioning permissions

## Setup

1. Clone the repo and navigate to this directory.

2. Create a `terraform.tfvars` file with your values (this file is gitignored — never commit it):

```hcl
pm_api_token_secret = "your-api-token-secret"
vm_name             = "ubuntu-vm-01"
vm_cores            = 2
vm_memory           = 2048
vm_disk_size        = "20G"
vm_user             = "ubuntu"
vm_password         = "your-password"
ssh_public_key      = "ssh-ed25519 AAAA..."
```

3. Initialize Terraform:

```bash
terraform init
```

4. Preview the plan:

```bash
terraform plan
```

5. Apply:

```bash
terraform apply
```

## Variables

| Name | Description | Default |
|------|-------------|---------|
| `pm_api_token_secret` | Proxmox API token secret | required |
| `vm_name` | Name of the VM | `ubuntu-vm-01` |
| `vm_cores` | Number of CPU cores | `2` |
| `vm_memory` | RAM in MB | `2048` |
| `vm_disk_size` | Disk size | `20G` |
| `vm_user` | Cloud-init username | `ubuntu` |
| `vm_password` | Cloud-init password | required |
| `ssh_public_key` | SSH public key for VM access | `""` |

## Notes

- The Proxmox endpoint is hardcoded to `https://192.168.1.50:8006/` — update `main.tf` if your IP differs.
- `insecure = true` is set to allow self-signed certs on the Proxmox web UI.
- `terraform.tfvars` and `terraform.tfstate` are gitignored to prevent credential exposure.
