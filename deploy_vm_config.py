#!/usr/bin/env python
"""
VM Configuration Deployment Tool

This script copies the necessary VM configuration files from vm-workspace to a configuration-specific 
folder with the server name. It also updates the terraform.tfvars file with the correct values.

Usage:
  python deploy_vm_config.py <config_id> <timestamp> <server_name>

Example:
  python deploy_vm_config.py 8d7047e0 20250416175136 lin2dv2-ssb
"""

import os
import sys
import shutil
import json
from datetime import datetime

def ensure_dir(directory):
    """Ensure directory exists"""
    if not os.path.exists(directory):
        os.makedirs(directory)

def copy_vm_workspace(config_id, timestamp, server_name):
    """Copy VM workspace files to config folder"""
    # Define paths
    workspace_dir = os.path.join(os.getcwd(), "vm-workspace")
    config_folder = f"{config_id}_{timestamp}"
    target_dir = os.path.join(os.getcwd(), "terraform", config_folder)
    
    # Ensure target directory exists
    ensure_dir(target_dir)
    
    # List of files to copy (excluding directories)
    files_to_copy = [
        "fetch_next_ip.py",
        "data.tf",
        "providers.tf",
        "machine.tf"
    ]
    
    # Copy each file
    for file in files_to_copy:
        source = os.path.join(workspace_dir, file)
        destination = os.path.join(target_dir, file)
        if os.path.exists(source):
            shutil.copy2(source, destination)
            print(f"Copied {file} to {destination}")
    
    # Also copy the machine_inputs.tfvars content to terraform.tfvars
    source_vars = os.path.join(workspace_dir, "machine_inputs.tfvars")
    target_vars = os.path.join(target_dir, "terraform.tfvars")
    
    if os.path.exists(source_vars):
        with open(source_vars, 'r') as f:
            content = f.read()
        
        # Replace server name if needed
        content = content.replace("rhel9-vm", server_name)
        
        # Add timestamp
        now = datetime.now()
        timestamp_str = now.strftime("%Y%m%d%H%M%S")
        content = f"# Generated Terraform configuration for {server_name}\n"
        content += f"# Request ID: {config_id}\n"
        content += f"# Timestamp: {timestamp}\n\n"
        content += content
        
        # Write to target
        with open(target_vars, 'w') as f:
            f.write(content)
        
        print(f"Created terraform.tfvars with machine configuration")
    
    print(f"VM workspace files copied to {target_dir}")
    print(f"Ready to run Terraform plan via Atlantis for {server_name}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python deploy_vm_config.py <config_id> <timestamp> <server_name>")
        sys.exit(1)
    
    config_id = sys.argv[1]
    timestamp = sys.argv[2]
    server_name = sys.argv[3]
    
    copy_vm_workspace(config_id, timestamp, server_name)
