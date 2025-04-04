# Layman's form for machine.tf inputs

name             = "rhel9-vm"
resource_pool_id = "<resource_pool_id>"
datastore_id     = "<datastore_id>"
num_cpus         = 2
memory           = 4096
guest_id         = "rhel9_64Guest"
network_id       = "<network_id>"
adapter_type     = "vmxnet3"
disk_size        = 20
template_uuid    = "<template_uuid>"
ipv4_address     = "192.168.1.100"
ipv4_netmask     = 24
ipv4_gateway     = "192.168.1.1"
dns_servers      = ["8.8.8.8", "8.8.4.4"]
time_zone        = "UTC"
quantity         = 1  # Number of machines to create
start_number     = 1  # Starting number for machine names
end_number       = 100  # Ending number for machine names
additional_disks = [
  { size = 50, type = "thin" },
  { size = 100, type = "thick" }
]