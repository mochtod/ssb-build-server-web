variable "name" {
  description = "Name of the virtual machine"
  type        = string
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
}

variable "ipv4_netmask" {
  description = "IPv4 netmask"
  type        = number
  default     = 24
}

variable "ipv4_gateway" {
  description = "IPv4 gateway"
  type        = string
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

variable "additional_disks" {
  description = "List of additional disks to attach"
  type = list(object({
    size = number
    type = string
  }))
  default = []
}

variable "hostname" {
  description = "Hostname for the VM"
  type        = string
  default     = ""
}
