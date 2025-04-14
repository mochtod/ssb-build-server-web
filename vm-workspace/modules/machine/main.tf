resource "vsphere_virtual_machine" "vm" {
  name             = var.name
  resource_pool_id = var.resource_pool_id
  datastore_id     = var.datastore_id
  num_cpus         = var.num_cpus
  memory           = var.memory
  
  network_interface {
    network_id   = var.network_id
    adapter_type = var.adapter_type
  }
  
  disk {
    label            = "disk0"
    size             = var.disk_size
    eagerly_scrub    = false
    thin_provisioned = true
  }
  
  dynamic "disk" {
    for_each = var.additional_disks
    content {
      label            = "disk${disk.key + 1}"
      size             = disk.value.size
      eagerly_scrub    = false
      thin_provisioned = disk.value.type == "thin"
    }
  }

  clone {
    template_uuid = var.template_uuid
    customize {
      linux_options {
        host_name = var.hostname != "" ? var.hostname : var.name
        domain    = ""
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
}

output "vm_ip" {
  description = "IP address of the created VM"
  value       = vsphere_virtual_machine.vm.guest_ip_addresses[0]
}

output "vm_id" {
  description = "ID of the created VM"
  value       = vsphere_virtual_machine.vm.id
}
