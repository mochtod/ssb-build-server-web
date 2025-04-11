#!/usr/bin/env python3
"""
Direct Terraform execution module for SSB Build Server Web.

This module provides a fallback execution path for Terraform operations when the
Atlantis API is unavailable or returns errors. All Terraform operations are executed
within the Atlantis container, with dynamic container discovery to avoid hardcoded
container names.

The module includes functions for:
- Dynamically discovering the running Atlantis container
- Running terraform init inside the container
- Running terraform apply inside the container
- Generating build receipts for the user interface
"""
import os
import subprocess
import json
import logging
import tempfile
import time
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_base_url(atlantis_url):
    """Convert container hostname URLs to localhost for browser access"""
    parsed = urlparse(atlantis_url)
    
    # If hostname is 'atlantis', replace with 'localhost' for user browser access
    if parsed.hostname == 'atlantis':
        return f"http://localhost:{parsed.port}"
    
    return atlantis_url

def get_atlantis_container():
    """
    Dynamically discover the Atlantis container name/ID.
    
    Returns:
        str or None: Container name if found, None otherwise
    """
    try:
        # Get the container ID dynamically
        container_result = subprocess.run(
            ["docker", "ps", "--filter", "name=atlantis", "--format", "{{.Names}}"],
            capture_output=True,
            text=True
        )
        
        # Get the first container that contains 'atlantis' in the name
        atlantis_containers = container_result.stdout.strip().split('\n')
        if not atlantis_containers or not atlantis_containers[0]:
            logger.error("No running Atlantis container found")
            return None
            
        atlantis_container = atlantis_containers[0]
        logger.info(f"Using Atlantis container: {atlantis_container}")
        return atlantis_container
        
    except Exception as e:
        logger.exception(f"Error finding Atlantis container: {str(e)}")
        return None

def run_terraform_init(tf_directory):
    """Run terraform init in the specified directory using the Atlantis container"""
    logger.info(f"Running terraform init in {tf_directory}")
    try:
        # Get absolute path of terraform directory
        abs_path = os.path.abspath(tf_directory)
        
        # Get the Atlantis container
        atlantis_container = get_atlantis_container()
        if not atlantis_container:
            return False
        
        # Run terraform init in the Atlantis container
        result = subprocess.run(
            ["docker", "exec", atlantis_container, "terraform", "init"],
            cwd=tf_directory,
            capture_output=True,
            text=True,
            check=True
        )
            
        logger.info(f"Terraform init completed successfully: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Terraform init failed: {e.stderr}")
        return False

def run_terraform_apply(tf_directory):
    """Run terraform apply -auto-approve in the specified directory using the Atlantis container"""
    logger.info(f"Running terraform apply in {tf_directory}")
    try:
        # Create a temporary file for the apply output
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.log') as tmp:
            apply_log_file = tmp.name
        
        # Get the Atlantis container
        atlantis_container = get_atlantis_container()
        if not atlantis_container:
            return {
                'success': False,
                'error': "No running Atlantis container found"
            }
        
        # Run terraform apply using the Atlantis container
        abs_path = os.path.abspath(tf_directory)
        result = subprocess.run(
            ["docker", "exec", atlantis_container, "terraform", "apply", "-auto-approve"],
            cwd=tf_directory,
            capture_output=True,
            text=True
        )
        
        # Save the output to the log file
        with open(apply_log_file, 'w') as f:
            f.write(result.stdout)
            if result.stderr:
                f.write("\n\nSTDERR:\n")
                f.write(result.stderr)
        
        success = result.returncode == 0
        
        if success:
            logger.info(f"Terraform apply completed successfully")
            logger.info(f"Apply log saved to {apply_log_file}")
        else:
            logger.error(f"Terraform apply failed with code {result.returncode}")
            logger.error(f"Error details saved to {apply_log_file}")
        
        return {
            'success': success,
            'log_file': apply_log_file,
            'output': result.stdout,
            'error': result.stderr if not success else None
        }
    except Exception as e:
        logger.exception(f"Error running terraform apply: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def direct_terraform_apply(config_data, tf_directory):
    """
    Execute terraform apply directly when Atlantis API is unavailable.
    
    Args:
        config_data (dict): The VM configuration data
        tf_directory (str): Path to the directory containing Terraform files
        
    Returns:
        dict: Result of the operation with status and details
    """
    logger.info(f"Starting direct Terraform apply for {config_data['server_name']}")
    
    # Get base URL with localhost instead of container name
    atlantis_url = os.environ.get('ATLANTIS_URL', 'http://atlantis:4141')
    browser_url = get_base_url(atlantis_url)
    
    # Generate a unique ID for this operation
    import uuid
    operation_id = f"direct-{uuid.uuid4().hex[:8]}"
    
    # Initialize Terraform
    init_success = run_terraform_init(tf_directory)
    if not init_success:
        return {
            'status': 'error',
            'message': 'Terraform initialization failed',
            'build_url': f"{browser_url}/apply/{operation_id}"
        }
    
    # Run Terraform apply
    apply_result = run_terraform_apply(tf_directory)
    
    if apply_result.get('success', False):
        # Generate a receipt with the correct URL that works from a browser
        build_url = f"{browser_url}/apply/{operation_id}"
        
        # Extract VM IPs if available (for display in receipt)
        vm_ips = []
        try:
            output_lines = apply_result.get('output', '').splitlines()
            for line in output_lines:
                if "vm_ips" in line and "=" in line:
                    ips_part = line.split("=", 1)[1].strip()
                    vm_ips = json.loads(ips_part)
        except:
            logger.exception("Error extracting VM IPs from Terraform output")
        
        # Generate build receipt
        text_receipt = f"""
VM BUILD RECEIPT
---------------
Request ID: {config_data['request_id']}
Server Name: {config_data['server_name']}
Quantity: {config_data['quantity']}
Operation ID: {operation_id}
Workspace: {config_data['environment']}
Approved By: {config_data.get('approved_by', 'Unknown')}

VM Information:
{f"- IPs: {', '.join(vm_ips)}" if vm_ips else "- IP information not available"}

Status: Successfully provisioned via direct Terraform execution
Execution Time: {time.strftime("%Y-%m-%d %H:%M:%S")}

Build Status URL: {build_url}
Atlantis Plan: {browser_url}/plan/{config_data.get('plan_id', 'unknown')} 

NEXT STEPS:
1. VM has been provisioned in vSphere
2. Check vSphere console for VM status
3. VM will be automatically registered with Ansible
(Direct Terraform execution mode)
        """
        
        return {
            'status': 'success',
            'build_url': build_url,
            'build_receipt': text_receipt,
            'details': {
                'apply_id': operation_id,
                'workspace': config_data['environment'],
                'vm_ips': vm_ips,
                'instructions': "Your VM has been provisioned directly using Terraform."
            }
        }
    else:
        # Create receipt with error details
        error_message = apply_result.get('error', 'Unknown error during Terraform apply')
        build_url = f"{browser_url}/apply/{operation_id}"
        
        text_receipt = f"""
VM BUILD RECEIPT - FAILED
------------------------
Request ID: {config_data['request_id']}
Server Name: {config_data['server_name']}
Operation ID: {operation_id}
Workspace: {config_data['environment']}

Status: Failed to provision VM
Error: {error_message[:200]}{'...' if len(error_message) > 200 else ''}

Build Status URL: {build_url}
Atlantis Plan: {browser_url}/plan/{config_data.get('plan_id', 'unknown')}

NEXT STEPS:
1. Check the error message
2. Verify vSphere credentials and connection
3. Contact infrastructure team for assistance
(Direct Terraform execution mode)
        """
        
        return {
            'status': 'error',
            'message': error_message,
            'build_url': build_url,
            'build_receipt': text_receipt
        }

if __name__ == "__main__":
    # Example of how to use this module directly for testing
    import sys
    if len(sys.argv) != 2:
        print("Usage: python apply_terraform.py <terraform_directory>")
        sys.exit(1)
    
    test_config = {
        'request_id': 'test-123',
        'server_name': 'lin2dv2-test',
        'quantity': 1,
        'environment': 'development',
        'approved_by': 'Test Admin'
    }
    
    result = direct_terraform_apply(test_config, sys.argv[1])
    print(json.dumps(result, indent=2))
