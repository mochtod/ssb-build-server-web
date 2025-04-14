# Data sources for dynamic resource lookup
data "vsphere_datacenter" "dc" {
  name = var.datacenter_name
}

data "vsphere_datastore" "datastore" {
  name          = var.datastore_name
  datacenter_id = data.vsphere_datacenter.dc.id
}

data "vsphere_network" "network" {
  name          = var.network_name
  datacenter_id = data.vsphere_datacenter.dc.id
}

data "vsphere_resource_pool" "pool" {
  name          = var.resource_pool_name
  datacenter_id = data.vsphere_datacenter.dc.id
}

data "vsphere_virtual_machine" "template" {
  name          = var.template_name
  datacenter_id = data.vsphere_datacenter.dc.id
}

# IP address allocation from NetBox
data "external" "next_ip" {
  program = ["python", "${path.module}/fetch_next_ip.py"]
  query = {
    range   = "192.168.1.0/24"  # Should be a variable or derived from environment
    token   = var.netbox_token
    api_url = var.netbox_api_url
  }
}

locals {
  vm_base_name = "${var.hostname_prefix}-${var.name}"
}

module "rhel9_vm" {
  source  = "./modules/machine"
  count   = var.server_count

  name             = "${local.vm_base_name}-${var.start_number + count.index}"
  hostname         = "${local.vm_base_name}-${var.start_number + count.index}"
  
  # Use data source references instead of IDs
  resource_pool_id = data.vsphere_resource_pool.pool.id
  datastore_id     = data.vsphere_datastore.datastore.id
  network_id       = data.vsphere_network.network.id
  template_uuid    = data.vsphere_virtual_machine.template.id
  
  # Use IP from NetBox if available, or the specified one
  ipv4_address     = data.external.next_ip.result.ip
  
  # Pass through other variables
  num_cpus         = var.num_cpus
  memory           = var.memory
  adapter_type     = var.adapter_type
  disk_size        = var.disk_size
  ipv4_netmask     = var.ipv4_netmask
  ipv4_gateway     = var.ipv4_gateway
  dns_servers      = var.dns_servers
  time_zone        = var.time_zone
  additional_disks = var.additional_disks
}

output "vm_ips" {
  description = "List of IP addresses for the created VMs"
  value       = module.rhel9_vm[*].vm_ip
}

output "vm_ids" {
  description = "List of IDs for the created VMs"
  value       = module.rhel9_vm[*].vm_id
}
