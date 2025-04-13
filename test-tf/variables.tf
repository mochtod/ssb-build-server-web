variable "vsphere_server" {
  description = "vSphere server hostname or IP address"
  type        = string
}

variable "vsphere_user" {
  description = "vSphere username"
  type        = string
  sensitive   = true
}

variable "vsphere_password" {
  description = "vSphere password"
  type        = string
  sensitive   = true
}

variable "datacenter" {
  description = "vSphere datacenter name"
  type        = string
}

variable "cluster" {
  description = "vSphere cluster name"
  type        = string
}

variable "datastore" {
  description = "vSphere datastore name"
  type        = string
}

variable "network" {
  description = "vSphere network name"
  type        = string
}

variable "template" {
  description = "vSphere template name"
  type        = string
}

variable "resource_pool" {
  description = "vSphere resource pool name"
  type        = string
  default     = ""  # Default to empty to use the default pool
}
