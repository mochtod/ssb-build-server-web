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
        
        # Create the directory
        os.makedirs(workspace_dir, exist_ok=True)
        logger.info(f"Created workspace directory: {workspace_dir}")
        
        # Copy machine_inputs.tfvars to the workspace
        machine_inputs_src = os.path.join(VM_WORKSPACE_DIR, "machine_inputs.tfvars")
        machine_inputs_dst = os.path.join(workspace_dir, "machine_inputs.tfvars")
        shutil.copy(machine_inputs_src, machine_inputs_dst)
        logger.info(f"Copied machine_inputs.tfvars to {machine_inputs_dst}")
        
        # Copy main.tf to the workspace if it exists, or create a generic one
        main_tf_src = os.path.join(VM_WORKSPACE_DIR, "main.tf")
        main_tf_dst = os.path.join(workspace_dir, "main.tf")
        
        if os.path.exists(main_tf_src):
            shutil.copy(main_tf_src, main_tf_dst)
            logger.info(f"Copied main.tf to {main_tf_dst}")
        else:
            # Create a generic main.tf file
            generic_main_tf = """
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
            with open(main_tf_dst, 'w') as f:
                f.write(generic_main_tf)
            logger.info(f"Created generic main.tf at {main_tf_dst}")
        
        # Create variables.tf
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
        variables_tf_path = os.path.join(workspace_dir, "variables.tf")
        with open(variables_tf_path, 'w') as f:
            f.write(variables_tf)
        logger.info(f"Created variables.tf at {variables_tf_path}")
        
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
        # Prepare the workspace
        workspace_result = prepare_terraform_workspace(request_id, timestamp, config_data, tf_directory)
        
        if not workspace_result['success']:
            return {
                'status': 'error',
                'message': workspace_result['message']
            }
        
        workspace_dir = workspace_result['workspace_dir']
        workspace_id = workspace_result['workspace_id']
        
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

        # Make sure the Terraform module directory exists
        modules_dir = os.path.join(TERRAFORM_DIR, "modules")
        vsphere_vm_dir = os.path.join(modules_dir, "vsphere-vm")
        
        if not os.path.exists(vsphere_vm_dir):
            os.makedirs(vsphere_vm_dir, exist_ok=True)
            logger.info(f"Created Terraform modules directory: {vsphere_vm_dir}")
            # Here we would need to create the module files if they don't exist
            # This is just a placeholder - you would need to add the actual module files
        
        # Create a Terraform init command
        init_cmd = "terraform init"
        init_result = run_terraform_command(init_cmd, workspace_dir, env)
        
        if not init_result['success']:
            return {
                'status': 'error',
                'message': f"Terraform init failed: {init_result['stderr']}",
                'details': init_result
            }
        
        # Run Terraform plan
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
        
        # Generate a build receipt
        build_url = f"/build/{request_id}_{timestamp}"
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
            'details': apply_result
        }
        
    except Exception as e:
        logger.exception(f"Error applying Terraform plan: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error applying Terraform plan: {str(e)}"
        }

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