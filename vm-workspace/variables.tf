# Provider Variables
variable "vsphere_user" {
  description = "vSphere user name"
  type        = string
}

variable "vsphere_password" {
  description = "vSphere password"
  type        = string
  sensitive   = true
}

variable "vsphere_server" {
  description = "vSphere server"
  type        = string
}

# vSphere Resource Names for Dynamic Lookup
variable "datacenter_name" {
  description = "Name of the vSphere datacenter"
  type        = string
  default     = "Datacenter"
}

variable "datastore_name" {
  description = "Name of the vSphere datastore"
  type        = string
  default     = "datastore1"
}

variable "resource_pool_name" {
  description = "Name of the vSphere resource pool"
  type        = string
  default     = "Resources"
}

variable "network_name" {
  description = "Name of the vSphere network"
  type        = string
  default     = "VM Network"
}

variable "template_name" {
  description = "Name of the VM template"
  type        = string
  default     = "rhel9-template"
}

# VM Configuration Variables
variable "name" {
  description = "Base name for the virtual machine"
  type        = string
  default     = "rhel9-vm"
}

variable "resource_pool_id" {
  description = "Resource pool ID"
  type        = string
  default     = null
}

variable "datastore_id" {
  description = "Datastore ID"
  type        = string
  default     = null
}

variable "num_cpus" {
  description = "Number of CPUs"
  type        = number
  default     = 2
}

variable "memory" {
  description = "Memory in MB"
  type        = number
  default     = 4096
}

variable "network_id" {
  description = "Network ID"
  type        = string
  default     = null
}

variable "adapter_type" {
  description = "Network adapter type"
  type        = string
  default     = "vmxnet3"
}

variable "disk_size" {
  description = "Disk size in GB"
  type        = number
  default     = 50
}

variable "template_uuid" {
  description = "Template UUID"
  type        = string
  default     = null
}

variable "ipv4_address" {
  description = "IPv4 address"
  type        = string
  default     = null
}

variable "ipv4_netmask" {
  description = "IPv4 netmask"
  type        = number
  default     = 24
}

variable "ipv4_gateway" {
  description = "IPv4 gateway"
  type        = string
  default     = "192.168.1.1"
}

variable "dns_servers" {
  description = "DNS servers"
  type        = list(string)
  default     = ["8.8.8.8", "8.8.4.4"]
}

variable "time_zone" {
  description = "Time zone"
  type        = string
  default     = "UTC"
}

variable "start_number" {
  description = "Starting number for VM names"
  type        = number
  default     = 1
}

variable "end_number" {
  description = "Ending number for VM names"
  type        = number
  default     = 100
}

variable "additional_disks" {
  description = "List of additional disks to attach"
  type = list(object({
    size = number
    type = string
  }))
  default = []
}

# Environment Variables
variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "development"
}

variable "hostname_prefix" {
  description = "Hostname prefix for VMs"
  type        = string
  default     = "lin2dv2"
}

variable "server_count" {
  description = "Number of servers"
  type        = number
  default     = 1
}

# NetBox Integration Variables
variable "netbox_token" {
  description = "API token for NetBox"
  type        = string
  default     = ""
}

variable "netbox_api_url" {
  description = "NetBox API URL"
  type        = string
  default     = ""
}

# Vault Configuration Variables
variable "vault_token" {
  description = "Vault token"
  type        = string
  default     = ""
  sensitive   = true
}

variable "vault_role_id" {
  description = "Vault role ID"
  type        = string
  default     = ""
}

variable "vault_secret_id" {
  description = "Vault secret ID"
  type        = string
  default     = ""
  sensitive   = true
}

variable "vault_k8s_role" {
  description = "Vault Kubernetes role"
  type        = string
  default     = ""
}
