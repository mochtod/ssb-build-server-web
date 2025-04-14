#!/usr/bin/env python3
"""
Functions for generating Terraform files with vSphere resources.
These functions replace the old environment variable approach with a per-VM approach.
"""
import os
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_variables_file(variables_file, config):
    """Generate Terraform variables file based on user input"""
    # Extract configuration values
    server_name = config['server_name']
    environment = config['environment']
    
    # Get vSphere resource IDs from the VM configuration
    # No fallback to environment variables - resources must be explicitly specified in the config
    if 'vsphere_resources' in config:
        resource_pool_id = config['vsphere_resources'].get('resource_pool_id', '')
        datastore_id = config['vsphere_resources'].get('datastore_id', '')
        network_id = config['vsphere_resources'].get('network_id', '')
        template_uuid = config['vsphere_resources'].get('template_uuid', '')
    else:
        logger.warning("VM configuration missing vsphere_resources section")
        resource_pool_id = ''
        datastore_id = ''
        network_id = ''
        template_uuid = ''
    
    # Validate that all required resources are present
    if not resource_pool_id or not datastore_id or not network_id or not template_uuid:
        logger.error("Missing required vSphere resources in VM configuration")
    
    # Build additional disks configuration as a string
    additional_disks_str = "["
    for disk in config.get('additional_disks', []):
        additional_disks_str += f'\n    {{ size = {disk["size"]}, type = "{disk["type"]}" }},'
    additional_disks_str += "\n  ]"
    
    # Get environment variables for vsphere connection
    vsphere_user = os.environ.get('VSPHERE_USER', '')
    vsphere_password = os.environ.get('VSPHERE_PASSWORD', '')
    vsphere_server = os.environ.get('VSPHERE_SERVER', '')
    
    # Get NetBox token from environment
    netbox_token = os.environ.get('NETBOX_TOKEN', '')
    netbox_api_url = os.environ.get('NETBOX_URL', 'https://netbox.chrobinson.com/api')
    
    # Format hostname prefix based on server name components
    hostname_prefix = server_name.split('-')[0] if '-' in server_name else server_name
    
# Generate variables content - including ALL variables from tfvars.tf
    variables_content = f"""
# Terraform variables for {server_name}
# Generated on {config['timestamp']}

# VM Configuration
name             = "{server_name}"
num_cpus         = {config['num_cpus']}
memory           = {config['memory']}
disk_size        = {config['disk_size']}
start_number     = {config.get('start_number', 1)}
end_number       = 100  # Hard-coded default

# Environment Configuration
environment      = "{environment}"
hostname_prefix  = "{hostname_prefix}"
server_count     = {config['quantity']}  # Using server_count consistently

# vSphere Connection
vsphere_user     = "{vsphere_user}"
vsphere_password = "{vsphere_password}"
vsphere_server   = "{vsphere_server}"

# vSphere Resources
resource_pool_id = "{resource_pool_id}"
datastore_id     = "{datastore_id}"
network_id       = "{network_id}"
template_uuid    = "{template_uuid}"

# Guest Configuration
adapter_type     = "vmxnet3"

# Network Configuration
ipv4_address     = "192.168.1.100"  # Will be overridden by NetBox
ipv4_netmask     = 24
ipv4_gateway     = "192.168.1.1"
dns_servers      = ["8.8.8.8", "8.8.4.4"]
time_zone        = "UTC"

# NetBox Integration
netbox_token     = "{netbox_token}"
netbox_api_url   = "{netbox_api_url}"

# Additional Storage
additional_disks = {additional_disks_str}

# Vault Configuration - Empty defaults as these are typically used in production
vault_token      = ""
vault_role_id    = ""
vault_secret_id  = ""
vault_k8s_role   = ""
"""
    
    # Write to file
    with open(variables_file, 'w') as f:
        f.write(variables_content)
    
    return variables_content

def generate_terraform_config(config):
    """Generate Terraform configuration based on user input"""
    server_name = config['server_name']
    server_count = config['quantity']  # Use server_count consistently
    num_cpus = config['num_cpus']
    memory = config['memory']
    disk_size = config['disk_size']
    additional_disks = config['additional_disks']
    start_number = config['start_number']
    environment = config['environment']
    
    # Format additional disks for Terraform
    additional_disks_tf = "[\n"
    for disk in additional_disks:
        additional_disks_tf += f'    {{ size = {disk["size"]}, type = "{disk["type"]}" }},\n'
    additional_disks_tf += "  ]"
    
    # Generate the Terraform configuration using the expected module pattern
    tf_config = f"""
# Generated Terraform configuration for {server_name}
# Request ID: {config['request_id']}
# Timestamp: {config['timestamp']}

variable "server_count" {{
  description = "Number of machines to create"
  type        = number
  default     = {server_count}
}}

variable "name" {{
  description = "Base name for the virtual machines"
  type        = string
  default     = "{server_name}"
}}

variable "resource_pool_id" {{
  description = "Resource pool ID"
  type        = string
}}

variable "datastore_id" {{
  description = "Datastore ID"
  type        = string
}}

variable "num_cpus" {{
  description = "Number of CPUs"
  type        = number
  default     = {num_cpus}
}}

variable "memory" {{
  description = "Memory in MB"
  type        = number
  default     = {memory}
}}

variable "network_id" {{
  description = "Network ID"
  type        = string
}}

variable "adapter_type" {{
  description = "Network adapter type"
  type        = string
  default     = "vmxnet3"
}}

variable "disk_size" {{
  description = "Disk size in GB"
  type        = number
  default     = {disk_size}
}}

variable "template_uuid" {{
  description = "Template UUID"
  type        = string
}}

variable "ipv4_address" {{
  description = "IPv4 address"
  type        = string
}}

variable "ipv4_netmask" {{
  description = "IPv4 netmask"
  type        = number
  default     = 24
}}

variable "ipv4_gateway" {{
  description = "IPv4 gateway"
  type        = string
}}

variable "dns_servers" {{
  description = "DNS servers"
  type        = list(string)
  default     = ["8.8.8.8", "8.8.4.4"]
}}

variable "time_zone" {{
  description = "Time zone"
  type        = string
  default     = "UTC"
}}

variable "start_number" {{
  description = "Starting number for VM names"
  type        = number
  default     = {start_number}
}}

variable "additional_disks" {{
  description = "Additional disks to attach"
  type        = list(object({{
    size = number
    type = string
  }}))
  default     = {additional_disks_tf}
}}

# Use the rhel9_vm module as expected by the VM workspace
module "rhel9_vm" {{
  source = "./modules/machine"
  count  = var.server_count

  name             = "${{var.name}}-${{var.start_number + count.index}}"
  resource_pool_id = var.resource_pool_id
  datastore_id     = var.datastore_id
  num_cpus         = var.num_cpus
  memory           = var.memory
  network_id       = var.network_id
  adapter_type     = var.adapter_type
  disk_size        = var.disk_size
  template_uuid    = var.template_uuid
  ipv4_address     = var.ipv4_address
  ipv4_netmask     = var.ipv4_netmask
  ipv4_gateway     = var.ipv4_gateway
  dns_servers      = var.dns_servers
  time_zone        = var.time_zone
}}

# Remove duplicate VM resource - use only the module approach
output "vm_ips" {{
  description = "List of IP addresses for the created VMs"
  value       = module.rhel9_vm[*].vm_ip
}}

output "vm_ids" {{
  description = "List of IDs for the created VMs"
  value       = module.rhel9_vm[*].vm_id
}}
"""
    
    return tf_config
