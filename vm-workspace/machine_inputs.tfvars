# Machine inputs for lin2dv2-ssb
# Generated on 2025-04-24 16:42:16
# Environment: development

name             = "lin2dv2-ssb"
num_cpus         = 2
memory           = 4096
disk_size        = 50
guest_id         = "rhel9_64Guest"
adapter_type     = "vmxnet3"
time_zone        = "UTC"
quantity         = 1
start_number     = 10001
dns_servers      = ["8.8.8.8", "8.8.4.4"]

# These values will be populated from vSphere during the Terraform plan phase
resource_pool_id = "domain-c3310244"
datastore_id     = "<datastore_id>"
network_id       = "<network_id>"
template_uuid    = "vm-11682491"
ipv4_address     = "192.168.1.100"
ipv4_netmask     = 24
ipv4_gateway     = "192.168.1.1"

# Additional disk configuration
additional_disks = [
  { size = 50, type = "thin" },
]
