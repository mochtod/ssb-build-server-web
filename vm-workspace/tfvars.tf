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

variable "netbox_token" {
  description = "Token for NetBox API"
  type        = string
  sensitive   = true
}