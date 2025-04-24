#!/usr/bin/env python3
"""
Terraform Command Executor

This module provides direct interaction with a Terraform container
instead of using Atlantis as a wrapper. It executes Terraform commands
directly on the Terraform container, which simplifies the deployment
workflow and removes the dependency on GitHub integration.
"""

import os
import subprocess
import logging
import json
import uuid
import time
import datetime
import shutil
from pathlib import Path
from vsphere_redis_cache import VSphereRedisCache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("terraform-executor")

# Default Terraform container name
TERRAFORM_CONTAINER = os.environ.get('TERRAFORM_CONTAINER', 'terraform')
VM_WORKSPACE_DIR = os.environ.get('VM_WORKSPACE_DIR', '/app/vm-workspace')
TERRAFORM_DIR = os.environ.get('TERRAFORM_DIR', '/app/terraform')

def run_terraform_command(command, working_dir, env=None):
    """
    Run a Terraform command directly using the local filesystem
    
    Args:
        command (str): The Terraform command to run
        working_dir (str): The working directory
        env (dict): Environment variables to set
        
    Returns:
        dict: Output from the command
    """
    try:
        # Prepare the environment
        cmd_env = os.environ.copy()
        if env:
            cmd_env.update(env)
        
        # Set explicit TF_PLUGIN_CACHE_DIR to a writable location
        if "TF_PLUGIN_CACHE_DIR" not in cmd_env:
            plugin_cache_dir = os.path.join(working_dir, ".terraform_plugin_cache")
            os.makedirs(plugin_cache_dir, exist_ok=True)
            try:
                # Try to make the plugin cache directory writable by everyone
                os.chmod(plugin_cache_dir, 0o777)
            except Exception as e:
                logger.warning(f"Could not set permissions on plugin cache directory: {str(e)}")
            
            cmd_env["TF_PLUGIN_CACHE_DIR"] = plugin_cache_dir
            
        # Add environment variable to fix potential file permission issues
        cmd_env["TF_PLUGIN_CACHE_DIR_PERMISSIONS"] = "0755"
        
        logger.info(f"Running Terraform command: {command} in {working_dir}")
        
        # Run the command
        result = subprocess.run(
            command,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            cwd=working_dir,
            env=cmd_env
        )
        
        # Check for errors
        if result.returncode != 0:
            logger.error(f"Terraform command failed: {result.stderr}")
            return {
                'success': False,
                'exit_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'command': command
            }
        
        # Return success
        return {
            'success': True,
            'exit_code': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'command': command
        }
    except Exception as e:
        logger.exception(f"Error running Terraform command: {str(e)}")
        return {
            'success': False,
            'exit_code': -1,
            'error': str(e),
            'command': command
        }

def prepare_terraform_workspace(request_id, timestamp, config_data, tf_directory):
    """
    Prepare the Terraform workspace
    
    Args:
        request_id (str): The unique request ID
        timestamp (str): Timestamp for the request
        config_data (dict): Configuration data
        tf_directory (str): Path to the Terraform directory
        
    Returns:
        dict: Result of the operation
    """
    try:
        # Create a unique workspace directory path
        workspace_id = f"{request_id}-{timestamp}"
        workspace_dir = os.path.join(VM_WORKSPACE_DIR, workspace_id)
        
        # Create the directory with error handling
        try:
            os.makedirs(workspace_dir, exist_ok=True)
            logger.info(f"Created workspace directory: {workspace_dir}")
        except PermissionError as pe:
            logger.error(f"Permission error creating workspace directory: {str(pe)}")
            return {
                'success': False,
                'message': f"Permission error: Cannot create workspace directory. Please check that the container has write permissions to {VM_WORKSPACE_DIR}"
            }
        except Exception as e:
            logger.error(f"Error creating workspace directory: {str(e)}")
            return {
                'success': False,
                'message': f"Error creating workspace directory: {str(e)}"
            }
        
        # Get machine_inputs.tfvars content - FIRST READ THE CONTENT instead of copying the file
        machine_inputs_src = os.path.join(VM_WORKSPACE_DIR, "machine_inputs.tfvars")
        machine_inputs_dst = os.path.join(workspace_dir, "machine_inputs.tfvars")
        
        # First try to read the file content instead of copying the file
        try:
            if os.path.exists(machine_inputs_src):
                with open(machine_inputs_src, 'r') as f:
                    machine_inputs_content = f.read()
                logger.info(f"Read machine_inputs.tfvars content from {machine_inputs_src}")
            else:
                # Create default content if file doesn't exist
                logger.warning(f"machine_inputs.tfvars not found at {machine_inputs_src}, creating default content")
                machine_inputs_content = """# Default machine_inputs.tfvars created by terraform_executor
name             = "default-vm"
num_cpus         = 2
memory           = 4096
disk_size        = 50
guest_id         = "rhel9_64Guest"
adapter_type     = "vmxnet3"
time_zone        = "UTC"
quantity         = 1
start_number     = 10001
dns_servers      = ["8.8.8.8", "8.8.4.4"]
resource_pool_id = "resource-pool-id"
datastore_id     = "datastore-id" 
network_id       = "network-id"
template_uuid    = "template-uuid"
ipv4_address     = "192.168.1.100"
ipv4_netmask     = 24
ipv4_gateway     = "192.168.1.1"
additional_disks = []
"""
            
            # Now write the content to the destination file
            with open(machine_inputs_dst, 'w') as f:
                f.write(machine_inputs_content)
            logger.info(f"Successfully wrote machine_inputs.tfvars to {machine_inputs_dst}")
                
        except PermissionError as pe:
            logger.error(f"Permission error handling machine_inputs.tfvars: {str(pe)}")
            return {
                'success': False,
                'message': f"Permission error: Cannot copy machine_inputs.tfvars. Please check file permissions."
            }
        except Exception as e:
            logger.error(f"Error handling machine_inputs.tfvars: {str(e)}")
            return {
                'success': False, 
                'message': f"Error handling machine_inputs.tfvars: {str(e)}"
            }
        
        # Create main.tf with error handling - directly write content instead of copying
        main_tf_src = os.path.join(VM_WORKSPACE_DIR, "main.tf")
        main_tf_dst = os.path.join(workspace_dir, "main.tf")
        
        try:
            # If main.tf exists, read its content
            if os.path.exists(main_tf_src):
                with open(main_tf_src, 'r') as f:
                    main_tf_content = f.read()
                logger.info(f"Read main.tf content from {main_tf_src}")
            else:
                # Create a generic main.tf content
                main_tf_content = """
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
"""
            
            # Write the content to the destination file
            with open(main_tf_dst, 'w') as f:
                f.write(main_tf_content)
            logger.info(f"Successfully wrote main.tf to {main_tf_dst}")
            
        except Exception as e:
            logger.error(f"Error creating main.tf: {str(e)}")
            return {
                'success': False,
                'message': f"Error creating main.tf: {str(e)}"
            }
        
        # Create variables.tf with error handling - directly write content
        variables_tf_path = os.path.join(workspace_dir, "variables.tf")
        try:
            variables_tf = """
variable "name" {
  description = "Base name for the virtual machines"
  type        = string
}

variable "resource_pool_id" {
  description = "Resource pool ID"
  type        = string
}

variable "datastore_id" {
  description = "Datastore ID"
  type        = string
  default     = null
}

variable "datastore_cluster_id" {
  description = "Datastore cluster ID"
  type        = string
  default     = null
}

variable "num_cpus" {
  description = "Number of CPUs"
  type        = number
}

variable "memory" {
  description = "Memory in MB"
  type        = number
}

variable "guest_id" {
  description = "Guest OS ID"
  type        = string
}

variable "network_id" {
  description = "Network ID"
  type        = string
}

variable "adapter_type" {
  description = "Network adapter type"
  type        = string
}

variable "disk_size" {
  description = "Disk size in GB"
  type        = number
}

variable "template_uuid" {
  description = "Template UUID"
  type        = string
}

variable "ipv4_address" {
  description = "IPv4 address"
  type        = string
}

variable "ipv4_netmask" {
  description = "IPv4 netmask"
  type        = number
}

variable "ipv4_gateway" {
  description = "IPv4 gateway"
  type        = string
}

variable "dns_servers" {
  description = "DNS servers"
  type        = list(string)
}

variable "time_zone" {
  description = "Time zone"
  type        = string
}

variable "start_number" {
  description = "Starting number for VM names"
  type        = number
}

variable "quantity" {
  description = "Number of machines to create"
  type        = number
}

variable "additional_disks" {
  description = "Additional disks to attach"
  type        = list(object({
    size = number
    type = string
  }))
  default     = []
}

variable "vsphere_user" {
  description = "vSphere username"
  type        = string
}

variable "vsphere_password" {
  description = "vSphere password"
  type        = string
  sensitive   = true
}

variable "vsphere_server" {
  description = "vSphere server"
  type        = string
}
"""
            with open(variables_tf_path, 'w') as f:
                f.write(variables_tf)
            logger.info(f"Created variables.tf at {variables_tf_path}")
        except Exception as e:
            logger.error(f"Error creating variables.tf: {str(e)}")
            return {
                'success': False,
                'message': f"Error creating variables.tf: {str(e)}"
            }
            
        # Ensure the modules directory exists for Terraform to work properly
        modules_path = os.path.join(workspace_dir, "..", "modules")
        if not os.path.exists(modules_path):
            try:
                os.makedirs(modules_path, exist_ok=True)
                logger.info(f"Created modules directory at {modules_path}")
            except Exception as e:
                logger.warning(f"Could not create modules directory: {str(e)}")
                # Not fatal, continue anyway
                
        # Create backend.tf file
        backend_tf_path = os.path.join(workspace_dir, "backend.tf")
        try:
            backend_tf = """
# Local backend configuration
terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
"""
            with open(backend_tf_path, 'w') as f:
                f.write(backend_tf)
            logger.info(f"Created backend.tf at {backend_tf_path}")
        except Exception as e:
            logger.warning(f"Error creating backend.tf: {str(e)}")
            # Not fatal, continue anyway
        
        return {
            'success': True,
            'message': f"Terraform workspace prepared successfully",
            'workspace_dir': workspace_dir,
            'workspace_id': workspace_id
        }
        
    except Exception as e:
        logger.exception(f"Error preparing Terraform workspace: {str(e)}")
        return {
            'success': False,
            'message': f"Error preparing Terraform workspace: {str(e)}"
        }

def prepare_terraform_workspace_for_multiple_servers(request_id, timestamp, config_data, tf_directory):
    """
    Prepare the Terraform workspace for multiple servers with different configurations
    
    Args:
        request_id (str): The unique request ID
        timestamp (str): Timestamp for the request
        config_data (dict): Configuration data containing multiple server definitions
        tf_directory (str): Path to the Terraform directory
        
    Returns:
        dict: Result of the operation
    """
    try:
        # Create a unique workspace directory path
        workspace_id = f"{request_id}-{timestamp}"
        workspace_dir = os.path.join(VM_WORKSPACE_DIR, workspace_id)
        
        # Create the directory with error handling
        try:
            os.makedirs(workspace_dir, exist_ok=True)
            logger.info(f"Created workspace directory: {workspace_dir}")
        except PermissionError as pe:
            logger.error(f"Permission error creating workspace directory: {str(pe)}")
            return {
                'success': False,
                'message': f"Permission error: Cannot create workspace directory. Please check that the container has write permissions to {VM_WORKSPACE_DIR}"
            }
        except Exception as e:
            logger.error(f"Error creating workspace directory: {str(e)}")
            return {
                'success': False,
                'message': f"Error creating workspace directory: {str(e)}"
            }
        
        # Extract server configurations from config_data
        server_configs = config_data.get('server_configs', [])
        
        if not server_configs:
            # If no server_configs provided, fall back to single server mode
            logger.info("No multiple server configurations found, falling back to single server mode")
            return prepare_terraform_workspace(request_id, timestamp, config_data, tf_directory)
        
        # Create a tfvars file for each server configuration
        for idx, server_config in enumerate(server_configs):
            server_name = server_config.get('server_name', f"server-{idx+1}")
            tfvars_filename = f"machine_inputs_{server_name}.tfvars"
            tfvars_path = os.path.join(workspace_dir, tfvars_filename)
            
            try:
                # Create the tfvars content from the server configuration
                tfvars_content = "# Generated by terraform_executor for multiple servers\n"
                
                # Add each key-value pair from the server configuration
                for key, value in server_config.items():
                    if isinstance(value, str):
                        tfvars_content += f'{key} = "{value}"\n'
                    elif isinstance(value, list):
                        if all(isinstance(item, str) for item in value):
                            value_str = '[' + ', '.join(f'"{item}"' for item in value) + ']'
                        else:
                            value_str = json.dumps(value)
                        tfvars_content += f'{key} = {value_str}\n'
                    else:
                        tfvars_content += f'{key} = {json.dumps(value)}\n'
                
                # Write the tfvars file
                with open(tfvars_path, 'w') as f:
                    f.write(tfvars_content)
                logger.info(f"Created {tfvars_filename} at {tfvars_path}")
                
            except Exception as e:
                logger.error(f"Error creating tfvars file for server {server_name}: {str(e)}")
                return {
                    'success': False,
                    'message': f"Error creating tfvars file for server {server_name}: {str(e)}"
                }
        
        # Create a modified main.tf for multiple server configurations
        main_tf_path = os.path.join(workspace_dir, "main.tf")
        try:
            main_tf_content = """
provider "vsphere" {
  user                 = var.vsphere_user
  password             = var.vsphere_password
  vsphere_server       = var.vsphere_server
  allow_unverified_ssl = true
}

"""
            
            # Add a module block for each server configuration
            for idx, server_config in enumerate(server_configs):
                server_name = server_config.get('server_name', f"server-{idx+1}")
                main_tf_content += f"""
module "vm_{server_name}" {{
  source = "../modules/vsphere-vm"
  
  # All variables will be loaded from the specific tfvars file during apply
  name                = var.{server_name}_name
  num_cpus            = var.{server_name}_num_cpus
  memory              = var.{server_name}_memory
  disk_size           = var.{server_name}_disk_size
  guest_id            = var.{server_name}_guest_id
  adapter_type        = var.{server_name}_adapter_type
  resource_pool_id    = var.{server_name}_resource_pool_id
  datastore_id        = var.{server_name}_datastore_id
  datastore_cluster_id = var.{server_name}_datastore_cluster_id
  network_id          = var.{server_name}_network_id
  template_uuid       = var.{server_name}_template_uuid
  ipv4_address        = var.{server_name}_ipv4_address
  ipv4_netmask        = var.{server_name}_ipv4_netmask
  ipv4_gateway        = var.{server_name}_ipv4_gateway
  dns_servers         = var.{server_name}_dns_servers
  time_zone           = var.{server_name}_time_zone
  quantity            = var.{server_name}_quantity
  start_number        = var.{server_name}_start_number
  additional_disks    = var.{server_name}_additional_disks
}}
"""
            
            # Add outputs for all server configurations
            main_tf_content += """
output "all_vm_ips" {
  description = "List of IP addresses for all created VMs"
  value = {
"""
            
            for idx, server_config in enumerate(server_configs):
                server_name = server_config.get('server_name', f"server-{idx+1}")
                main_tf_content += f'    {server_name} = module.vm_{server_name}.vm_ips\n'
            
            main_tf_content += """
  }
}

output "all_vm_ids" {
  description = "List of IDs for all created VMs"
  value = {
"""
            
            for idx, server_config in enumerate(server_configs):
                server_name = server_config.get('server_name', f"server-{idx+1}")
                main_tf_content += f'    {server_name} = module.vm_{server_name}.vm_ids\n'
            
            main_tf_content += """
  }
}
"""
            
            # Write the main.tf file
            with open(main_tf_path, 'w') as f:
                f.write(main_tf_content)
            logger.info(f"Created multi-server main.tf at {main_tf_path}")
            
        except Exception as e:
            logger.error(f"Error creating main.tf for multiple servers: {str(e)}")
            return {
                'success': False,
                'message': f"Error creating main.tf for multiple servers: {str(e)}"
            }
        
        # Create variables.tf with all required variables for all server configurations
        variables_tf_path = os.path.join(workspace_dir, "variables.tf")
        try:
            variables_tf_content = """
# Global vSphere provider variables
variable "vsphere_user" {
  description = "vSphere username"
  type        = string
}

variable "vsphere_password" {
  description = "vSphere password"
  type        = string
  sensitive   = true
}

variable "vsphere_server" {
  description = "vSphere server"
  type        = string
}

"""
            
            # Add variables for each server configuration with server name prefix
            for idx, server_config in enumerate(server_configs):
                server_name = server_config.get('server_name', f"server-{idx+1}")
                
                variables_tf_content += f"""
# Variables for {server_name}
variable "{server_name}_name" {{
  description = "Base name for the virtual machines for {server_name}"
  type        = string
}}

variable "{server_name}_resource_pool_id" {{
  description = "Resource pool ID for {server_name}"
  type        = string
}}

variable "{server_name}_datastore_id" {{
  description = "Datastore ID for {server_name}"
  type        = string
  default     = null
}}

variable "{server_name}_datastore_cluster_id" {{
  description = "Datastore cluster ID for {server_name}"
  type        = string
  default     = null
}}

variable "{server_name}_num_cpus" {{
  description = "Number of CPUs for {server_name}"
  type        = number
}}

variable "{server_name}_memory" {{
  description = "Memory in MB for {server_name}"
  type        = number
}}

variable "{server_name}_guest_id" {{
  description = "Guest OS ID for {server_name}"
  type        = string
}}

variable "{server_name}_network_id" {{
  description = "Network ID for {server_name}"
  type        = string
}}

variable "{server_name}_adapter_type" {{
  description = "Network adapter type for {server_name}"
  type        = string
}}

variable "{server_name}_disk_size" {{
  description = "Disk size in GB for {server_name}"
  type        = number
}}

variable "{server_name}_template_uuid" {{
  description = "Template UUID for {server_name}"
  type        = string
}}

variable "{server_name}_ipv4_address" {{
  description = "IPv4 address for {server_name}"
  type        = string
}}

variable "{server_name}_ipv4_netmask" {{
  description = "IPv4 netmask for {server_name}"
  type        = number
}}

variable "{server_name}_ipv4_gateway" {{
  description = "IPv4 gateway for {server_name}"
  type        = string
}}

variable "{server_name}_dns_servers" {{
  description = "DNS servers for {server_name}"
  type        = list(string)
}}

variable "{server_name}_time_zone" {{
  description = "Time zone for {server_name}"
  type        = string
}}

variable "{server_name}_start_number" {{
  description = "Starting number for VM names for {server_name}"
  type        = number
}}

variable "{server_name}_quantity" {{
  description = "Number of machines to create for {server_name}"
  type        = number
}}

variable "{server_name}_additional_disks" {{
  description = "Additional disks to attach for {server_name}"
  type        = list(object({{
    size = number
    type = string
  }}))
  default     = []
}}
"""
            
            # Write the variables.tf file
            with open(variables_tf_path, 'w') as f:
                f.write(variables_tf_content)
            logger.info(f"Created multi-server variables.tf at {variables_tf_path}")
            
        except Exception as e:
            logger.error(f"Error creating variables.tf for multiple servers: {str(e)}")
            return {
                'success': False,
                'message': f"Error creating variables.tf for multiple servers: {str(e)}"
            }
            
        # Create a terraform.tfvars file with combined variables from all server configurations
        terraform_tfvars_path = os.path.join(workspace_dir, "terraform.tfvars")
        try:
            terraform_tfvars_content = "# Combined terraform.tfvars for all server configurations\n\n"
            
            # Add variables for each server configuration with server name prefix
            for idx, server_config in enumerate(server_configs):
                server_name = server_config.get('server_name', f"server-{idx+1}")
                terraform_tfvars_content += f"# Variables for {server_name}\n"
                
                for key, value in server_config.items():
                    var_name = f"{server_name}_{key}"
                    if isinstance(value, str):
                        terraform_tfvars_content += f'{var_name} = "{value}"\n'
                    elif isinstance(value, list):
                        if all(isinstance(item, str) for item in value):
                            value_str = '[' + ', '.join(f'"{item}"' for item in value) + ']'
                        else:
                            value_str = json.dumps(value)
                        terraform_tfvars_content += f'{var_name} = {value_str}\n'
                    else:
                        terraform_tfvars_content += f'{var_name} = {json.dumps(value)}\n'
                
                terraform_tfvars_content += "\n"
            
            # Write the terraform.tfvars file
            with open(terraform_tfvars_path, 'w') as f:
                f.write(terraform_tfvars_content)
            logger.info(f"Created multi-server terraform.tfvars at {terraform_tfvars_path}")
            
        except Exception as e:
            logger.error(f"Error creating terraform.tfvars for multiple servers: {str(e)}")
            return {
                'success': False,
                'message': f"Error creating terraform.tfvars for multiple servers: {str(e)}"
            }
            
        # Create backend.tf file
        backend_tf_path = os.path.join(workspace_dir, "backend.tf")
        try:
            backend_tf = """
# Local backend configuration
terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
"""
            with open(backend_tf_path, 'w') as f:
                f.write(backend_tf)
            logger.info(f"Created backend.tf at {backend_tf_path}")
        except Exception as e:
            logger.warning(f"Error creating backend.tf: {str(e)}")
            # Not fatal, continue anyway
            
        # Ensure the modules directory exists for Terraform to work properly
        modules_path = os.path.join(workspace_dir, "..", "modules")
        if not os.path.exists(modules_path):
            try:
                os.makedirs(modules_path, exist_ok=True)
                logger.info(f"Created modules directory at {modules_path}")
            except Exception as e:
                logger.warning(f"Could not create modules directory: {str(e)}")
                # Not fatal, continue anyway
        
        return {
            'success': True,
            'message': f"Terraform workspace prepared successfully for multiple servers",
            'workspace_dir': workspace_dir,
            'workspace_id': workspace_id
        }
        
    except Exception as e:
        logger.exception(f"Error preparing Terraform workspace for multiple servers: {str(e)}")
        return {
            'success': False,
            'message': f"Error preparing Terraform workspace for multiple servers: {str(e)}"
        }

def run_terraform_plan(request_id, timestamp, config_data, tf_directory):
    """
    Run a Terraform plan
    
    Args:
        request_id (str): The unique request ID
        timestamp (str): Timestamp for the request
        config_data (dict): Configuration data
        tf_directory (str): Path to the Terraform directory
        
    Returns:
        dict: Result of the operation including the plan output
    """
    try:
        # Check if we're using multiple server configurations
        using_multiple_servers = 'server_configs' in config_data and len(config_data.get('server_configs', [])) > 0
        
        # Prepare the workspace - choose the appropriate function based on whether we have multiple servers
        if using_multiple_servers:
            logger.info("Using multiple server configurations for Terraform plan")
            workspace_result = prepare_terraform_workspace_for_multiple_servers(request_id, timestamp, config_data, tf_directory)
        else:
            logger.info("Using single server configuration for Terraform plan")
            workspace_result = prepare_terraform_workspace(request_id, timestamp, config_data, tf_directory)
        
        if not workspace_result['success']:
            return {
                'status': 'error',
                'message': workspace_result['message']
            }
        
        workspace_dir = workspace_result['workspace_dir']
        workspace_id = workspace_result['workspace_id']
        
        # Validate template UUIDs before proceeding
        logger.info("Validating template UUIDs before running Terraform plan")
        template_validation = validate_template_uuids(workspace_dir)
        if not template_validation['success']:
            return {
                'status': 'error',
                'message': template_validation['message']
            }
        
        # Get vSphere credentials from environment
        vsphere_server = os.environ.get('VSPHERE_SERVER', '')
        vsphere_user = os.environ.get('VSPHERE_USER', '')
        vsphere_password = os.environ.get('VSPHERE_PASSWORD', '')
        
        # Set up environment variables for Terraform
        env = {
            'TF_VAR_vsphere_server': vsphere_server,
            'TF_VAR_vsphere_user': vsphere_user,
            'TF_VAR_vsphere_password': vsphere_password,
            'TF_IN_AUTOMATION': 'true',
            # Add environment variable to skip provider verification which can cause permission issues
            'TF_SKIP_PROVIDER_VERIFY': 'true'
        }

        # Make sure the Terraform module directory exists
        modules_dir = os.path.join(TERRAFORM_DIR, "modules")
        vsphere_vm_dir = os.path.join(modules_dir, "vsphere-vm")
        
        if not os.path.exists(vsphere_vm_dir):
            os.makedirs(vsphere_vm_dir, exist_ok=True)
            logger.info(f"Created Terraform modules directory: {vsphere_vm_dir}")
            # Here we would need to create the module files if they don't exist
            # This is just a placeholder - you would need to add the actual module files
        
        # Create a Terraform init command with additional flags to avoid permission issues
        init_cmd = "terraform init -plugin-dir=.terraform_plugin_cache"
        init_result = run_terraform_command(init_cmd, workspace_dir, env)
        
        if not init_result['success']:
            # If init fails with provider issues, try again with minimal flags
            logger.warning("Initial terraform init failed, trying with minimal configuration")
            init_cmd = "terraform init"
            init_result = run_terraform_command(init_cmd, workspace_dir, env)
        
        if not init_result['success']:
            return {
                'status': 'error',
                'message': f"Terraform init failed: {init_result['stderr']}",
                'details': init_result
            }
        
        # Run Terraform plan - use different command based on whether we have multiple servers
        if using_multiple_servers:
            # For multiple servers, use the combined terraform.tfvars file
            plan_cmd = "terraform plan -out=plan.tfplan"
        else:
            # For single server, use the machine_inputs.tfvars file
            plan_cmd = "terraform plan -var-file=machine_inputs.tfvars -out=plan.tfplan"
        
        plan_result = run_terraform_command(plan_cmd, workspace_dir, env)
        
        if not plan_result['success']:
            return {
                'status': 'error',
                'message': f"Terraform plan failed: {plan_result['stderr']}",
                'details': plan_result
            }
        
        # Generate plan ID and URL for the UI
        plan_id = workspace_id
        
        # Format a nice plan output with resource details
        if using_multiple_servers:
            server_configs = config_data.get('server_configs', [])
            total_vms = sum(server_config.get('quantity', 1) for server_config in server_configs)
            server_names = [server_config.get('server_name', f"server-{i+1}") for i, server_config in enumerate(server_configs)]
            
            plan_log = f"""
Terraform Plan Output:
----------------------
Plan ID: {plan_id}
Environment: {config_data['environment']}
Servers: {', '.join(server_names)}
Workspace: {workspace_id}

Plan Output:
{plan_result['stdout']}

This plan will:
- Create {total_vms} new VM(s) across {len(server_configs)} server configurations
- Configure networking and storage for each server type
- Process the following server configurations: {', '.join(server_names)}

Note: This plan was executed using direct Terraform execution (not Atlantis) with multiple server configurations.
"""
        else:
            plan_log = f"""
Terraform Plan Output:
----------------------
Plan ID: {plan_id}
Environment: {config_data['environment']}
Server: {config_data['server_name']}
Workspace: {workspace_id}

Plan Output:
{plan_result['stdout']}

This plan will:
- Create {config_data['quantity']} new VM(s)
- Configure networking and storage
- Set up additional disks: {len(config_data.get('additional_disks', []))}

Note: This plan was executed using direct Terraform execution (not Atlantis).
"""
        
        return {
            'status': 'success',
            'plan_id': plan_id,
            'workspace_id': workspace_id,
            'plan_log': plan_log,
            'workspace_dir': workspace_dir,
            'details': plan_result
        }
        
    except Exception as e:
        logger.exception(f"Error running Terraform plan: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error running Terraform plan: {str(e)}"
        }

def apply_terraform_plan(request_id, timestamp, config_data, tf_directory):
    """
    Apply a Terraform plan
    
    Args:
        request_id (str): The unique request ID
        timestamp (str): Timestamp for the request
        config_data (dict): Configuration data
        tf_directory (str): Path to the Terraform directory
        
    Returns:
        dict: Result of the operation
    """
    try:
        # Get the workspace ID from the config if available
        workspace_id = config_data.get('workspace_id', f"{request_id}-{timestamp}")
        workspace_dir = os.path.join(VM_WORKSPACE_DIR, workspace_id)
        
        # Validate template UUIDs before proceeding
        logger.info("Validating template UUIDs before running Terraform apply")
        template_validation = validate_template_uuids(workspace_dir)
        if not template_validation['success']:
            return {
                'status': 'error',
                'message': template_validation['message']
            }
        
        # Get vSphere credentials from environment
        vsphere_server = os.environ.get('VSPHERE_SERVER', '')
        vsphere_user = os.environ.get('VSPHERE_USER', '')
        vsphere_password = os.environ.get('VSPHERE_PASSWORD', '')
        
        # Set up environment variables for Terraform
        env = {
            'TF_VAR_vsphere_server': vsphere_server,
            'TF_VAR_vsphere_user': vsphere_user,
            'TF_VAR_vsphere_password': vsphere_password,
            'TF_IN_AUTOMATION': 'true'
        }
        
        # Run Terraform apply
        apply_cmd = "terraform apply -auto-approve plan.tfplan"
        apply_result = run_terraform_command(apply_cmd, workspace_dir, env)
        
        if not apply_result['success']:
            return {
                'status': 'error',
                'message': f"Terraform apply failed: {apply_result['stderr']}",
                'details': apply_result
            }
        
        # Check if we're using multiple server configurations
        using_multiple_servers = 'server_configs' in config_data and len(config_data.get('server_configs', [])) > 0
        
        # Generate a build receipt
        build_url = f"/build/{request_id}_{timestamp}"
        
        if using_multiple_servers:
            server_configs = config_data.get('server_configs', [])
            total_vms = sum(server_config.get('quantity', 1) for server_config in server_configs)
            server_names = [server_config.get('server_name', f"server-{i+1}") for i, server_config in enumerate(server_configs)]
            
            text_receipt = f"""
MULTIPLE VM BUILD RECEIPT
------------------------
Request ID: {config_data['request_id']}
Timestamp: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Server Names: {', '.join(server_names)}
Total VMs: {total_vms}
Apply ID: {workspace_id}
Workspace: {config_data['environment']}
Approved By: {config_data.get('approved_by', 'Unknown')}

Apply Output:
{apply_result['stdout']}

NEXT STEPS:
1. VMs are now being created in vSphere
2. The creation process may take 10-15 minutes
3. You will receive a notification when the build is complete
            """
        else:
            text_receipt = f"""
VM BUILD RECEIPT
---------------
Request ID: {config_data['request_id']}
Timestamp: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Server Name: {config_data['server_name']}
Quantity: {config_data['quantity']}
Apply ID: {workspace_id}
Workspace: {config_data['environment']}
Approved By: {config_data.get('approved_by', 'Unknown')}

Apply Output:
{apply_result['stdout']}

NEXT STEPS:
1. VMs are now being created in vSphere
2. The creation process may take 10-15 minutes
3. You will receive a notification when the build is complete
            """
        
        return {
            'status': 'success',
            'build_url': build_url,
            'build_receipt': text_receipt,
            'apply_id': workspace_id,
            'workspace': config_data['environment'],
            'details': apply_result,
            'multiple_servers': using_multiple_servers
        }
        
    except Exception as e:
        logger.exception(f"Error applying Terraform plan: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error applying Terraform plan: {str(e)}"
        }

def validate_template_uuids(workspace_dir):
    """
    Validate the template UUIDs in the Terraform workspace
    
    Args:
        workspace_dir (str): Path to the Terraform workspace directory
        
    Returns:
        dict: Validation result with success flag and message
    """
    try:
        logger.info(f"Validating template UUIDs in workspace {workspace_dir}")
        
        # Determine if this is a multi-server workspace
        tfvars_files = [f for f in os.listdir(workspace_dir) if f.endswith('.tfvars')]
        is_multi_server = any(f.startswith('machine_inputs_') for f in tfvars_files)
        
        # Initialize the vSphere cache client
        vsphere_cache = VSphereRedisCache()
        invalid_templates = []
        warnings = []
        
        if is_multi_server:
            # For multi-server workspaces, check all machine_inputs_*.tfvars files
            for tfvars_file in tfvars_files:
                if tfvars_file.startswith('machine_inputs_'):
                    # Extract server name from filename (machine_inputs_server-name.tfvars)
                    server_name = tfvars_file.replace('machine_inputs_', '').replace('.tfvars', '')
                    
                    # Parse the tfvars file to get template_uuid
                    tfvars_path = os.path.join(workspace_dir, tfvars_file)
                    template_uuid = extract_template_uuid_from_tfvars(tfvars_path)
                    
                    if template_uuid:
                        # Validate the template UUID
                        validation_result = vsphere_cache.validate_template_uuid(template_uuid)
                        if not validation_result['valid']:
                            invalid_templates.append({
                                'server_name': server_name,
                                'template_uuid': template_uuid,
                                'message': validation_result['message'],
                                'troubleshooting': validation_result.get('troubleshooting', {})
                            })
                        elif validation_result.get('warning'):
                            # Template is considered valid but with a warning
                            warnings.append({
                                'server_name': server_name,
                                'template_uuid': template_uuid,
                                'message': validation_result.get('warning'),
                                'details': validation_result.get('message', '')
                            })
        else:
            # For single server workspaces, check machine_inputs.tfvars
            tfvars_path = os.path.join(workspace_dir, 'machine_inputs.tfvars')
            template_uuid = extract_template_uuid_from_tfvars(tfvars_path)
            
            if template_uuid:
                # Validate the template UUID
                validation_result = vsphere_cache.validate_template_uuid(template_uuid)
                if not validation_result['valid']:
                    invalid_templates.append({
                        'server_name': 'default',
                        'template_uuid': template_uuid,
                        'message': validation_result['message'],
                        'troubleshooting': validation_result.get('troubleshooting', {})
                    })
                elif validation_result.get('warning'):
                    # Template is considered valid but with a warning
                    warnings.append({
                        'server_name': 'default',
                        'template_uuid': template_uuid,
                        'message': validation_result.get('warning'),
                        'details': validation_result.get('message', '')
                    })
        
        # Return validation result
        if invalid_templates:
            error_messages = []
            for item in invalid_templates:
                base_message = f"Server '{item['server_name']}': Template UUID '{item['template_uuid']}' is invalid - {item['message']}"
                
                # Add troubleshooting information for connection issues
                troubleshooting = item.get('troubleshooting', {})
                if troubleshooting:
                    # Add more user-friendly details for common error cases
                    error_details = troubleshooting.get('error_details', '')
                    if 'certificate verify failed' in error_details.lower():
                        base_message += "\nSSL certificate verification failed - check VSPHERE_VERIFY_SSL in your environment settings."
                    elif 'connection refused' in error_details.lower():
                        base_message += "\nConnection refused - check if the vSphere server is reachable and the port is correct."
                    elif 'unauthorized' in error_details.lower() or 'authentication required' in error_details.lower():
                        base_message += "\nAuthentication failed - check your vSphere credentials."
                    
                    # Add server information
                    if troubleshooting.get('vsphere_server'):
                        base_message += f"\nvSphere Server: {troubleshooting.get('vsphere_server')}"
                
                error_messages.append(base_message)
            
            error_message = "\n\n".join(error_messages)
            
            # Add a human-readable summary with suggestions
            summary = """
Template validation failed. This may be due to:
1. Invalid template UUID - The template may have been deleted or moved
2. vSphere connection issues - Check your network and credentials
3. Missing environment variables - Ensure VSPHERE_SERVER, VSPHERE_USER, and VSPHERE_PASSWORD are set

Please check the .env file and ensure your vSphere credentials are correct.
"""
            error_message = f"{summary}\nDetails:\n{error_message}"
            
            logger.error(f"Template validation failed: {error_message}")
            
            return {
                'success': False,
                'message': error_message
            }
        else:
            # If no errors but there are warnings, still return success but include warnings
            if warnings:
                warning_messages = []
                for warning in warnings:
                    warning_messages.append(f"Server '{warning['server_name']}': {warning['message']} - {warning['details']}")
                
                warning_message = "\n\n".join(warning_messages)
                logger.warning(f"Template validation warnings: {warning_message}")
                
                return {
                    'success': True,
                    'message': "All template UUIDs are valid, but with warnings",
                    'warnings': warning_message
                }
            else:
                logger.info("All template UUIDs are valid")
                return {
                    'success': True,
                    'message': "All template UUIDs are valid"
                }
    except Exception as e:
        logger.exception(f"Error validating template UUIDs: {str(e)}")
        return {
            'success': False,
            'message': f"Error validating template UUIDs: {str(e)}"
        }

def extract_template_uuid_from_tfvars(tfvars_path):
    """
    Extract the template UUID from a Terraform tfvars file
    
    Args:
        tfvars_path (str): Path to the tfvars file
        
    Returns:
        str: The template UUID, or None if not found
    """
    try:
        if not os.path.exists(tfvars_path):
            logger.warning(f"tfvars file not found: {tfvars_path}")
            return None
        
        with open(tfvars_path, 'r') as f:
            tfvars_content = f.read()
        
        # Look for template_uuid = "value" in the file
        import re
        template_match = re.search(r'template_uuid\s*=\s*"([^"]+)"', tfvars_content)
        if (template_match):
            return template_match.group(1)
        else:
            logger.warning(f"template_uuid not found in {tfvars_path}")
            return None
    except Exception as e:
        logger.exception(f"Error extracting template UUID from {tfvars_path}: {str(e)}")
        return None

# If run as a script, check if terraform is available
if __name__ == "__main__":
    try:
        result = run_terraform_command("terraform version", ".")
        if result['success']:
            print(f"Terraform is available: {result['stdout']}")
        else:
            print(f"Terraform not available: {result['stderr']}")
    except Exception as e:
        print(f"Error checking Terraform availability: {str(e)}")