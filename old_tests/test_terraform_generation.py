#!/usr/bin/env python3
"""
Test script to verify that the generated Terraform files match the expected format
for Atlantis compatibility.

This script:
1. Creates a test VM configuration
2. Generates terraform.tfvars and machine.tf files
3. Validates the generated files against the reference VM workspace files
4. Reports any discrepancies
"""
import os
import json
import logging
import argparse
import tempfile
import sys
import uuid
import datetime

# Import the functions to test
from vsphere_resource_functions import generate_variables_file, generate_terraform_config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_test_vm_config():
    """Create a test VM configuration similar to what the web app would create."""
    request_id = str(uuid.uuid4())[:8]
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    
    return {
        'request_id': request_id,
        'timestamp': timestamp,
        'server_name': 'lin2dv2-test',
        'server_prefix': 'lin2dv2',
        'app_name': 'test',
        'quantity': 1,
        'num_cpus': 2,
        'memory': 4096,
        'disk_size': 50,
        'additional_disks': [
            {'size': 100, 'type': 'thin'},
            {'size': 200, 'type': 'thick'}
        ],
        'environment': 'development',
        'start_number': 10001,
        'build_status': 'pending',
        'build_owner': 'Test User',
        'build_username': 'testuser',
        'created_at': datetime.datetime.now().isoformat(),
        'vsphere_resources': {
            'resource_pool_id': 'resgroup-1234',
            'datastore_id': 'datastore-5678',
            'network_id': 'network-9012',
            'template_uuid': 'vm-template-3456'
        }
    }

def setup_env_variables():
    """Set up environment variables for testing."""
    os.environ['VSPHERE_USER'] = 'test_user'
    os.environ['VSPHERE_PASSWORD'] = 'test_password'
    os.environ['VSPHERE_SERVER'] = 'test.vsphere.server'
    os.environ['NETBOX_TOKEN'] = 'test_netbox_token'
    os.environ['NETBOX_URL'] = 'https://test.netbox.url/api'

def generate_and_save_terraform_files(temp_dir, config):
    """Generate and save terraform files based on the config."""
    # Generate variables file
    variables_file = os.path.join(temp_dir, 'terraform.tfvars')
    generate_variables_file(variables_file, config)
    
    # Generate machine.tf
    machine_tf = generate_terraform_config(config)
    machine_tf_file = os.path.join(temp_dir, 'machine.tf')
    with open(machine_tf_file, 'w') as f:
        f.write(machine_tf)
    
    return variables_file, machine_tf_file

def run_validation(generated_tf_dir, reference_tf_dir):
    """Run the validation script to verify compatibility."""
    # Import only when needed to avoid import errors if script is missing
    try:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from validate_terraform_input_fields import main as validate_main
        
        # Set up the arguments that would be passed to the validation script
        sys.argv = [
            'validate_terraform_input_fields.py',
            '--generated-tf-dir', generated_tf_dir,
            '--reference-tf-dir', reference_tf_dir
        ]
        
        # Run the validation
        return validate_main()
    except ImportError:
        logger.error("Validation script not found. Please ensure validate_terraform_input_fields.py is available.")
        return 1
    except Exception as e:
        logger.error(f"Error running validation: {str(e)}")
        return 1

def main():
    parser = argparse.ArgumentParser(description='Test Terraform file generation for Atlantis compatibility')
    parser.add_argument('--reference-tf-dir', default='vm-workspace', 
                        help='Directory containing the reference Terraform files (default: vm-workspace)')
    args = parser.parse_args()
    
    # Set up environment variables
    setup_env_variables()
    
    # Create a test VM configuration
    logger.info("Creating test VM configuration...")
    config = create_test_vm_config()
    
    # Create a temporary directory for the generated files
    with tempfile.TemporaryDirectory() as temp_dir:
        logger.info(f"Generating Terraform files in {temp_dir}...")
        
        # Generate terraform files
        variables_file, machine_tf_file = generate_and_save_terraform_files(temp_dir, config)
        
        # Print the generated files for inspection
        logger.info(f"Generated {variables_file}:")
        with open(variables_file, 'r') as f:
            logger.info(f.read())
            
        logger.info(f"Generated {machine_tf_file}:")
        with open(machine_tf_file, 'r') as f:
            logger.info(f.read())
        
        # Run validation
        logger.info(f"Validating generated files against reference files in {args.reference_tf_dir}...")
        result = run_validation(temp_dir, args.reference_tf_dir)
        
        if result == 0:
            logger.info("✅ Validation passed! The generated Terraform files are compatible with Atlantis.")
        else:
            logger.error("❌ Validation failed. The generated Terraform files may not be compatible with Atlantis.")
        
        return result

if __name__ == "__main__":
    sys.exit(main())
