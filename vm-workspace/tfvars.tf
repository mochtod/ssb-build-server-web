variable "vsphere_user" {
  description = "vSphere username"
  type        = string
}

variable "vsphere_password" {
  description = "vSphere password"
  type        = string
  sensitive   = true
}

variable "vsphere_server" {
  description = "vSphere server address"
  type        = string
}

variable "hostname_prefix" {
  description = "Prefix for the server hostname"
  type        = string
}

variable "server_count" {
  description = "Number of servers to create"
  type        = number
}

variable "quantity" {
  description = "Number of machines to create"
  type        = number
  default     = 1
}

variable "netbox_token" {
  description = "Token for NetBox API"
  type        = string
  sensitive   = true
}

variable "netbox_api_url" {
  description = "URL for NetBox API"
  type        = string
  default     = "https://netbox.chrobinson.com/api"
}

# Vault authentication variables
variable "vault_token" {
  description = "Token for Vault authentication"
  type        = string
  sensitive   = true
  default     = ""
}

variable "vault_role_id" {
  description = "Role ID for Vault AppRole authentication"
  type        = string
  sensitive   = true
  default     = ""
}

variable "vault_secret_id" {
  description = "Secret ID for Vault AppRole authentication"
  type        = string
  sensitive   = true
  default     = ""
}

variable "vault_k8s_role" {
  description = "Role for Vault Kubernetes authentication"
  type        = string
  default     = ""
}

# Additional variables needed for machine.tf
variable "name" {
  description = "Name of the virtual machine"
  type        = string
  default     = "rhel9-vm"
}

variable "resource_pool_id" {
  description = "ID of the resource pool"
  type        = string
}

variable "datastore_id" {
  description = "ID of the datastore"
  type        = string
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

variable "guest_id" {
  description = "Guest OS ID"
  type        = string
  default     = "rhel9_64Guest"
}

variable "network_id" {
  description = "ID of the network"
  type        = string
}

variable "adapter_type" {
  description = "Network adapter type"
  type        = string
  default     = "vmxnet3"
}

variable "disk_size" {
  description = "Disk size in GB"
  type        = number
  default     = 20
}

variable "template_uuid" {
  description = "UUID of the template"
  type        = string
}

variable "ipv4_address" {
  description = "IPv4 address"
  type        = string
  default     = "192.168.1.100"
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
  description = "List of DNS servers"
  type        = list(string)
  default     = ["8.8.8.8", "8.8.4.4"]
}

variable "time_zone" {
  description = "Time zone"
  type        = string
  default     = "UTC"
}

variable "start_number" {
  description = "Starting number for machine names"
  type        = number
  default     = 1
}

variable "end_number" {
  description = "Ending number for machine names"
  type        = number
  default     = 100
}

variable "additional_disks" {
  description = "Additional disks to attach to the VM"
  type = list(object({
    size = number
    type = string
  }))
  default = []
}
