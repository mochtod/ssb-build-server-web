#!/usr/bin/env python3
"""
End-to-end test for the Terraform/Atlantis integration fix.

This script tests the whole workflow from creating a test configuration,
generating Terraform files, validating them, and making Atlantis API calls.
"""
import os
import json
import logging
import sys
import uuid
import shutil
import datetime
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the modules we need to test
from vsphere_resource_functions import generate_terraform_config, generate_variables_file
from terraform_validator import validate_terraform_files
from atlantis_api import run_atlantis_plan, AtlantisApiError

def create_test_config_data():
    """Create a test VM configuration for the workflow"""
    request_id = str(uuid.uuid4())[:8]
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    
    config_data = {
        'request_id': request_id,
        'timestamp': timestamp,
        'server_name': 'lin2dv2-test',
        'server_prefix': 'lin2dv2',
        'app_name': 'test',
        'quantity': 1,
        'num_cpus': 2,
        'memory': 4096,
        'disk_size': 50,
        'additional_disks': [],
        'environment': 'development',
        'start_number': 10001,
        'build_owner': 'Test User',
        'build_username': 'admin',
        'vsphere_resources': {
            'resource_pool_id': 'resgroup-123',
            'datastore_id': 'datastore-123',
            'network_id': 'network-123',
            'template_uuid': 'template-123'
        }
    }
    
    logger.info(f"Created test configuration with request_id {request_id}")
    return config_data

def create_terraform_files(config_data):
    """Generate Terraform files from the test configuration"""
    # Create a temporary directory for the Terraform files
    tf_directory = os.path.join(tempfile.gettempdir(), f"terraform_test_{config_data['request_id']}")
    os.makedirs(tf_directory, exist_ok=True)
    logger.info(f"Created test directory: {tf_directory}")
    
    try:
        # Generate the Terraform configuration
        tf_config = generate_terraform_config(config_data)
        machine_tf_file = os.path.join(tf_directory, "machine.tf")
        with open(machine_tf_file, 'w') as f:
            f.write(tf_config)
        logger.info(f"Generated machine.tf file")
        
        # Generate the variables file
        variables_file = os.path.join(tf_directory, "terraform.tfvars")
        generate_variables_file(variables_file, config_data)
        logger.info(f"Generated terraform.tfvars file")
        
        return tf_directory
    
    except Exception as e:
        logger.error(f"Error generating Terraform files: {str(e)}")
        shutil.rmtree(tf_directory)
        raise

def validate_files(tf_directory):
    """Validate the generated Terraform files"""
    logger.info(f"Validating Terraform files in {tf_directory}")
    
    result = validate_terraform_files(tf_directory)
    if result:
        logger.info("✅ Terraform validation passed successfully")
    else:
        logger.error("❌ Terraform validation failed")
        return False
    
    return True

def test_atlantis_plan(config_data, tf_directory):
    """Test the Atlantis plan API call with our configuration"""
    logger.info("Testing Atlantis plan API call")
    
    try:
        # This will trigger the fixed Atlantis API payload generation
        plan_result = run_atlantis_plan(config_data, tf_directory)
        
        logger.info(f"Atlantis plan API response: {json.dumps(plan_result, indent=2)}")
        
        # Check if the API call was successful
        if plan_result.get('status') == 'success':
            logger.info("✅ Atlantis plan API call succeeded")
            logger.info(f"Plan ID: {plan_result.get('plan_id', 'unknown')}")
            return True
        else:
            logger.error(f"❌ Atlantis plan API call failed: {plan_result.get('message', 'unknown error')}")
            return False
    
    except AtlantisApiError as e:
        logger.error(f"❌ Atlantis API error: {str(e)}")
        return False
    
    except Exception as e:
        logger.error(f"❌ Unexpected error during Atlantis plan: {str(e)}")
        return False

def clean_up(tf_directory):
    """Clean up the test directory"""
    try:
        shutil.rmtree(tf_directory)
        logger.info(f"Cleaned up test directory: {tf_directory}")
    except Exception as e:
        logger.warning(f"Failed to clean up test directory: {str(e)}")

def main():
    """Main function to run the end-to-end test"""
    logger.info("Starting end-to-end test for Terraform/Atlantis integration fix")
    
    # Generate a test configuration
    config_data = create_test_config_data()
    
    # Track if any step fails
    any_failures = False
    tf_directory = None
    
    try:
        # Generate Terraform files
        tf_directory = create_terraform_files(config_data)
        
        # Validate the files
        if not validate_files(tf_directory):
            any_failures = True
        
        # Test the Atlantis API integration
        # Skip this part since we're testing locally without a real Atlantis instance
        # For a test with a real Atlantis instance, uncomment the following:
        # if not test_atlantis_plan(config_data, tf_directory):
        #     any_failures = True
        
        # Report test results
        if any_failures:
            logger.error("❌ End-to-end test failed. See errors above.")
            return 1
        else:
            logger.info("🎉 All tested components are working correctly!")
            return 0
    
    except Exception as e:
        logger.exception(f"Uncaught error during end-to-end test: {str(e)}")
        return 1
    
    finally:
        # Clean up
        if tf_directory:
            clean_up(tf_directory)

if __name__ == "__main__":
    sys.exit(main())
