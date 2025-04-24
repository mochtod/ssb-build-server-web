/**
 * VSphere VM Module
 * This module creates VSphere virtual machines based on the provided configuration
 */

# VM Resource
resource "vsphere_virtual_machine" "vm" {
  count = var.quantity

  name             = "${var.name}-${var.start_number + count.index}"
  resource_pool_id = var.resource_pool_id
  
  # Handle either datastore_id or datastore_cluster_id
  datastore_id        = var.datastore_id != null ? var.datastore_id : null
  datastore_cluster_id = var.datastore_cluster_id != null ? var.datastore_cluster_id : null
  
  num_cpus         = var.num_cpus
  memory           = var.memory
  guest_id         = var.guest_id
  
  network_interface {
    network_id   = var.network_id
    adapter_type = var.adapter_type
  }
  
  disk {
    label            = "disk0"
    size             = var.disk_size
    eagerly_scrub    = false
    thin_provisioned = true
    unit_number      = 0
  }

  # Add additional disks if specified
  dynamic "disk" {
    for_each = var.additional_disks
    content {
      label            = "disk${disk.key + 1}"
      size             = disk.value.size
      eagerly_scrub    = false
      thin_provisioned = disk.value.type == "thin"
      unit_number      = disk.key + 1
    }
  }

  # Clone from template
  clone {
    template_uuid = var.template_uuid
    
    customize {
      linux_options {
        host_name = "${var.name}-${var.start_number + count.index}"
        domain    = "localdomain"
        time_zone = var.time_zone
      }
      
      network_interface {
        ipv4_address = var.ipv4_address
        ipv4_netmask = var.ipv4_netmask
      }
      
      ipv4_gateway    = var.ipv4_gateway
      dns_server_list = var.dns_servers
    }
  }

  lifecycle {
    prevent_destroy = false
  }
}

output "vm_ips" {
  description = "List of IP addresses for the created VMs"
  value       = [for vm in vsphere_virtual_machine.vm : vm.guest_ip_addresses[0]]
}

output "vm_ids" {
  description = "List of IDs for the created VMs"
  value       = [for vm in vsphere_virtual_machine.vm : vm.id]
}

output "vm_names" {
  description = "List of names for the created VMs"
  value       = [for vm in vsphere_virtual_machine.vm : vm.name]
}