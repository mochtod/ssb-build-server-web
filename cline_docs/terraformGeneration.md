# Terraform Module Generation Implementation Plan

## Current Issue

The `generate_terraform_config()` function in app.py is incomplete and cannot properly generate Terraform module files that Atlantis can read and action on. This is a critical issue preventing the application from being fully functional.

## Analysis of Current Implementation

The current implementation of `generate_terraform_config()` only:
1. Extracts configuration values from the user input
2. Formats additional disks for Terraform
3. Does not generate the complete Terraform configuration

The function is missing:
1. The actual Terraform resource definition
2. Variable declarations
3. Provider configuration
4. Module references
5. Output definitions

## Implementation Plan

### 1. Complete the `generate_terraform_config()` Function

Update the function to generate a complete Terraform configuration file based on the VM workspace structure:

```python
def generate_terraform_config(config):
    """Generate Terraform configuration based on user input"""
    server_name = config['server_name']
    quantity = config['quantity']
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
    
    # Generate the Terraform configuration
    tf_config = f"""
# Generated Terraform configuration for {server_name}
# Request ID: {config['request_id']}
# Timestamp: {config['timestamp']}

variable "quantity" {{
  description = "Number of machines to create"
  type        = number
  default     = {quantity}
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

variable "guest_id" {{
  description = "Guest OS ID"
  type        = string
  default     = "rhel9_64Guest"
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

resource "vsphere_virtual_machine" "vm" {{
  count = var.quantity

  name             = "${{var.name}}-${{var.start_number + count.index}}"
  resource_pool_id = var.resource_pool_id
  datastore_id     = var.datastore_id
  num_cpus         = var.num_cpus
  memory           = var.memory
  guest_id         = var.guest_id
  
  network_interface {{
    network_id   = var.network_id
    adapter_type = var.adapter_type
  }}
  
  disk {{
    label            = "disk0"
    size             = var.disk_size
    eagerly_scrub    = false
    thin_provisioned = true
  }}

  dynamic "disk" {{
    for_each = var.additional_disks
    content {{
      label            = "disk${{disk.key + 1}}"
      size             = disk.value.size
      eagerly_scrub    = false
      thin_provisioned = disk.value.type == "thin"
    }}
  }}

  clone {{
    template_uuid = var.template_uuid
  }}

  custom_attributes = {{
    ipv4_address = var.ipv4_address
  }}
}}

output "vm_ips" {{
  description = "List of IP addresses for the created VMs"
  value       = [for vm in vsphere_virtual_machine.vm : vm.custom_attributes["ipv4_address"]]
}}

output "vm_ids" {{
  description = "List of IDs for the created VMs"
  value       = [for vm in vsphere_virtual_machine.vm : vm.id]
}}
"""
    
    return tf_config
```

### 2. Implement the `generate_variables_file()` Function

Create a function to generate the Terraform variables file:

```python
def generate_variables_file(variables_file, config):
    """Generate Terraform variables file based on user input"""
    # Extract configuration values
    server_name = config['server_name']
    environment = config['environment']
    
    # Determine environment-specific values
    if environment == "production":
        resource_pool = "Production"
        network = "PROD-NETWORK"
    else:
        resource_pool = "Development"
        network = "DEV-NETWORK"
    
    # Generate variables content
    variables_content = f"""
# Terraform variables for {server_name}
# Generated on {config['timestamp']}

# VM Configuration
name             = "{server_name}"
num_cpus         = {config['num_cpus']}
memory           = {config['memory']}
disk_size        = {config['disk_size']}
quantity         = {config['quantity']}
start_number     = {config['start_number']}

# Environment Configuration
environment      = "{environment}"

# These values need to be replaced with actual values from your vSphere environment
resource_pool_id = "resource-pool-id-placeholder"
datastore_id     = "datastore-id-placeholder"
network_id       = "network-id-placeholder"
template_uuid    = "template-uuid-placeholder"
ipv4_address     = "192.168.1.100"
ipv4_netmask     = 24
ipv4_gateway     = "192.168.1.1"
dns_servers      = ["8.8.8.8", "8.8.4.4"]
time_zone        = "UTC"
"""
    
    # Write to file
    with open(variables_file, 'w') as f:
        f.write(variables_content)
    
    return variables_content
```

### 3. Update the Atlantis Integration

Modify the `run_atlantis_plan()` function to properly communicate with the containerized Atlantis:

```python
def run_atlantis_plan(config_data, tf_directory):
    """Run a Terraform plan in Atlantis"""
    try:
        # Read the Terraform files
        machine_tf_file = os.path.join(tf_directory, "machine.tf")
        variables_file = os.path.join(tf_directory, "terraform.tfvars")
        
        with open(machine_tf_file, 'r') as f:
            machine_tf_content = f.read()
        
        with open(variables_file, 'r') as f:
            variables_content = f.read()
        
        # Prepare the Atlantis payload
        atlantis_payload = {
            'terraform_files': {
                'machine.tf': machine_tf_content,
                'terraform.tfvars': variables_content
            },
            'workspace': config_data['environment'],
            'plan_only': True,
            'comment': f"VM Provisioning Plan: {config_data['server_name']}",
            'user': config_data['build_owner'],
            'verbose': True
        }
        
        # Call Atlantis API to plan
        headers = {
            'Content-Type': 'application/json',
            'X-Atlantis-Token': ATLANTIS_TOKEN
        }
        
        response = requests.post(f"{ATLANTIS_URL}/api/plan", json=atlantis_payload, headers=headers)
        
        if response.status_code != 200:
            return {
                'status': 'error',
                'message': f"Failed to trigger Atlantis plan: {response.text}"
            }
        
        plan_response = response.json()
        plan_id = plan_response.get('plan_id')
        
        # Generate plan log
        plan_log = f"""
Terraform Plan Output:
----------------------
Plan ID: {plan_id}
Environment: {config_data['environment']}
Server: {config_data['server_name']}
Planned Resources:
- {config_data['quantity']} virtual machines
- {len(config_data['additional_disks'])} additional disks

This plan will:
- Create {config_data['quantity']} new VM(s)
- Configure networking and storage
- Register VMs with Ansible

Atlantis Plan URL: {ATLANTIS_URL}/plan/{plan_id}
        """
        
        return {
            'status': 'success',
            'atlantis_url': f"{ATLANTIS_URL}/plan/{plan_id}",
            'plan_log': plan_log,
            'plan_id': plan_id,
            'details': {
                'workspace': config_data['environment'],
                'resources': f"{config_data['quantity']} VMs"
            }
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'message': f"Error running Terraform plan: {str(e)}"
        }
```

### 4. Testing Plan

1. **Unit Testing**:
   - Test the `generate_terraform_config()` function with sample inputs
   - Verify the generated Terraform files are valid
   - Test the `generate_variables_file()` function

2. **Integration Testing**:
   - Test the communication with Atlantis API
   - Verify plan and apply operations work correctly
   - Test the end-to-end workflow

3. **Validation**:
   - Validate the generated Terraform files with `terraform validate`
   - Test with a containerized Atlantis setup
   - Verify VM creation in a test environment

## Implementation Timeline

1. **Day 1**: Complete the `generate_terraform_config()` and `generate_variables_file()` functions
2. **Day 2**: Update the Atlantis integration functions
3. **Day 3**: Set up containerized Atlantis and test integration
4. **Day 4**: End-to-end testing and validation
5. **Day 5**: Documentation and deployment

## Success Criteria

1. The application can generate valid Terraform files
2. Atlantis can successfully plan and apply the generated files
3. VMs are created in VMware vSphere according to the configuration
4. The entire workflow from configuration to VM creation works end-to-end
