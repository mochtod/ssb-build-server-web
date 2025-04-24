
variable "name" {
  description = "Base name for the virtual machines"
  type        = string
}

variable "resource_pool_id" {
  description = "Resource pool ID"
  type        = string
}

variable "datastore_id" {
  description = "Datastore ID"
  type        = string
  default     = null
}

variable "datastore_cluster_id" {
  description = "Datastore cluster ID"
  type        = string
  default     = null
}

variable "num_cpus" {
  description = "Number of CPUs"
  type        = number
}

variable "memory" {
  description = "Memory in MB"
  type        = number
}

variable "guest_id" {
  description = "Guest OS ID"
  type        = string
}

variable "network_id" {
  description = "Network ID"
  type        = string
}

variable "adapter_type" {
  description = "Network adapter type"
  type        = string
}

variable "disk_size" {
  description = "Disk size in GB"
  type        = number
}

variable "template_uuid" {
  description = "Template UUID"
  type        = string
}

variable "ipv4_address" {
  description = "IPv4 address"
  type        = string
}

variable "ipv4_netmask" {
  description = "IPv4 netmask"
  type        = number
}

variable "ipv4_gateway" {
  description = "IPv4 gateway"
  type        = string
}

variable "dns_servers" {
  description = "DNS servers"
  type        = list(string)
}

variable "time_zone" {
  description = "Time zone"
  type        = string
}

variable "start_number" {
  description = "Starting number for VM names"
  type        = number
}

variable "quantity" {
  description = "Number of machines to create"
  type        = number
}

variable "additional_disks" {
  description = "Additional disks to attach"
  type        = list(object({
    size = number
    type = string
  }))
  default     = []
}

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
  description = "vSphere server"
  type        = string
}
