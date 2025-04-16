# Generated Terraform configuration for lin2dv2-ssb
# Request ID: 8d7047e0
# Timestamp: 20250416175136

# Base name for the virtual machines
name             = "lin2dv2-ssb"
# Resource identifiers
resource_pool_id = "<resource_pool_id>"
datastore_id     = "<datastore_id>"
network_id       = "<network_id>"
template_uuid    = "<template_uuid>"

# VM specifications
num_cpus         = 2
memory           = 4096
guest_id         = "rhel9_64Guest"
adapter_type     = "vmxnet3"
disk_size        = 50

# Network configuration
ipv4_address     = "<ipv4_address>"
ipv4_netmask     = 24
ipv4_gateway     = "<ipv4_gateway>"
dns_servers      = ["8.8.8.8", "8.8.4.4"]
time_zone        = "UTC"

# Multiple machine configuration
quantity         = 3  # Change this to create multiple identical VMs
start_number     = last number plus one # ai add this. funciton all machiens have unique nubmers # Starting number for machine names (lin2dv2-ssb-10001, lin2dv2-ssb-10002, etc.)
additional_disks = []  # Add additional disks if needed: [{size = 50, type = "thin"}]