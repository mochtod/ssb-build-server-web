# VM resource names for dynamic lookup
datacenter_name    = "Datacenter"
datastore_name     = "datastore1"
resource_pool_name = "Resources"
network_name       = "VM Network"
template_name      = "rhel9-template"

# VM Configuration
name             = "rhel9-vm"
num_cpus         = 2
memory           = 4096
adapter_type     = "vmxnet3"
disk_size        = 20
ipv4_address     = "192.168.1.100"
ipv4_netmask     = 24
ipv4_gateway     = "192.168.1.1"
dns_servers      = ["8.8.8.8", "8.8.4.4"]
time_zone        = "UTC"
server_count     = 1  # Number of machines to create (renamed from quantity)
hostname_prefix  = "lin2dv2"
start_number     = 1  # Starting number for machine names
end_number       = 100  # Ending number for machine names
additional_disks = [
  { size = 50, type = "thin" },
  { size = 100, type = "thick" }
]

# NetBox integration for IP allocation
netbox_token  = "your-netbox-token-here"
netbox_api_url = "https://netbox.chrobinson.com/api"
