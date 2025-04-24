// Sample main.tf for VM workspace directory
// This file will be used by the Terraform executor

provider "vsphere" {
  user                 = var.vsphere_user
  password             = var.vsphere_password
  vsphere_server       = var.vsphere_server
  allow_unverified_ssl = true
}

module "vm" {
  source = "../modules/vsphere-vm"
  
  # Pass all variables from machine_inputs.tfvars
  name                = var.name
  num_cpus            = var.num_cpus
  memory              = var.memory
  disk_size           = var.disk_size
  guest_id            = var.guest_id
  adapter_type        = var.adapter_type
  resource_pool_id    = var.resource_pool_id
  datastore_id        = var.datastore_id
  datastore_cluster_id = var.datastore_cluster_id
  network_id          = var.network_id
  template_uuid       = var.template_uuid
  ipv4_address        = var.ipv4_address
  ipv4_netmask        = var.ipv4_netmask
  ipv4_gateway        = var.ipv4_gateway
  dns_servers         = var.dns_servers
  time_zone           = var.time_zone
  quantity            = var.quantity
  start_number        = var.start_number
  additional_disks    = var.additional_disks
}

output "vm_ips" {
  description = "List of IP addresses for the created VMs"
  value       = module.vm.vm_ips
}

output "vm_ids" {
  description = "List of IDs for the created VMs"
  value       = module.vm.vm_ids
}

output "vm_names" {
  description = "List of names for the created VMs"
  value       = module.vm.vm_names
}

output "summary" {
  description = "Summary of VM deployment"
  value = {
    environment = var.name != "" ? (contains(split("-", var.name), "pr2") ? "Production" : "Development") : "Unknown"
    vm_count    = var.quantity
    prefix      = var.name
    created_at  = timestamp()
  }
}