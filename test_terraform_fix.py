#!/usr/bin/env python3
"""
Test script to verify that the Terraform validation fix works correctly.
This script:
1. Creates a test directory with simple Terraform files
2. Validates the files using the modified terraform_validator module
3. Reports the results
"""
import os
import shutil
import tempfile
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the modules we want to test
from terraform_validator import validate_terraform_files, check_required_fields
from vsphere_resource_functions import generate_terraform_config, generate_variables_file

def create_test_directory():
    """Create a temporary directory for testing"""
    test_dir = os.path.join(tempfile.gettempdir(), "terraform_test_" + os.urandom(4).hex())
    os.makedirs(test_dir, exist_ok=True)
    logger.info(f"Created test directory: {test_dir}")
    return test_dir

def clean_up(test_dir):
    """Clean up the test directory"""
    try:
        shutil.rmtree(test_dir)
        logger.info(f"Cleaned up test directory: {test_dir}")
    except Exception as e:
        logger.warning(f"Failed to clean up test directory: {str(e)}")

def create_test_config(test_dir):
    """Create test Terraform configuration files"""
    # Create a sample VM configuration
    config = {
        'request_id': 'test-123',
        'timestamp': '20250412141500',
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
        'vsphere_resources': {
            'resource_pool_id': 'resource-pool-123',
            'datastore_id': 'datastore-123',
            'network_id': 'network-123',
            'template_uuid': 'template-123'
        }
    }
    
    # Generate Terraform files
    tf_config = generate_terraform_config(config)
    logger.info("Generated Terraform configuration")
    
    # Write the files
    with open(os.path.join(test_dir, "machine.tf"), "w") as f:
        f.write(tf_config)
    
    # Generate variables file
    variables_file = os.path.join(test_dir, "terraform.tfvars")
    generate_variables_file(variables_file, config)
    logger.info("Generated Terraform variables file")
    
    return config

def test_validation(test_dir):
    """Test the Terraform validation"""
    # Test the validator
    logger.info("Testing terraform_validator.validate_terraform_files()...")
    validation_result = validate_terraform_files(test_dir)
    
    if validation_result:
        logger.info("✅ Terraform validation passed successfully!")
    else:
        logger.error("❌ Terraform validation failed!")
        return False
    
    # Test required fields check
    logger.info("Testing terraform_validator.check_required_fields()...")
    fields_valid, missing_fields = check_required_fields(test_dir)
    
    if fields_valid:
        logger.info("✅ Required fields check passed successfully!")
    else:
        logger.error(f"❌ Required fields check failed! Missing fields: {', '.join(missing_fields)}")
        return False
    
    return True

def main():
    """Main function"""
    logger.info("Starting Terraform validation fix test")
    
    # Create test directory
    test_dir = create_test_directory()
    
    try:
        # Create test configuration
        create_test_config(test_dir)
        
        # Test validation
        success = test_validation(test_dir)
        
        # Report results
        if success:
            logger.info("🎉 All tests passed! The Terraform validation fix is working correctly.")
            return 0
        else:
            logger.error("❌ Tests failed! The Terraform validation fix is not working correctly.")
            return 1
    
    finally:
        # Clean up
        clean_up(test_dir)

if __name__ == "__main__":
    sys.exit(main())
