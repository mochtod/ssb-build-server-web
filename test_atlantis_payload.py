#!/usr/bin/env python3
"""
Test script for Atlantis API payload generation.

This script tests the updated payload generation functions to ensure they correctly
format Terraform files for the Atlantis API.
"""
import os
import json
import tempfile
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the modules we want to test
from fix_atlantis_apply import generate_atlantis_payload, generate_atlantis_apply_payload_fixed

def create_test_terraform_files():
    """Create temporary test Terraform files"""
    # Create a temporary directory
    test_dir = os.path.join(tempfile.gettempdir(), "atlantis_test_" + os.urandom(4).hex())
    os.makedirs(test_dir, exist_ok=True)
    logger.info(f"Created test directory: {test_dir}")
    
    # Create a sample main.tf file
    main_tf_content = """
resource "vsphere_virtual_machine" "vm" {
  name = "test-vm"
  resource_pool_id = var.resource_pool_id
  datastore_id = var.datastore_id
  num_cpus = 2
  memory = 4096
  guest_id = "rhel9_64Guest"
  
  network_interface {
    network_id = var.network_id
  }
  
  disk {
    label = "disk0"
    size = 50
  }
}
"""
    
    with open(os.path.join(test_dir, "main.tf"), "w") as f:
        f.write(main_tf_content)
    
    # Create a sample terraform.tfvars file
    tfvars_content = """
resource_pool_id = "resource-pool-123"
datastore_id = "datastore-123"
network_id = "network-123"
"""
    
    with open(os.path.join(test_dir, "terraform.tfvars"), "w") as f:
        f.write(tfvars_content)
    
    return test_dir

def test_generate_atlantis_payload():
    """Test the generate_atlantis_payload function"""
    test_dir = create_test_terraform_files()
    
    try:
        logger.info("Testing generate_atlantis_payload function...")
        
        # Get list of files
        tf_files = [f for f in os.listdir(test_dir) if f.endswith('.tf') or f.endswith('.tfvars')]
        logger.info(f"Test files: {tf_files}")
        
        # Generate the payload for plan operation
        payload = generate_atlantis_payload(
            repo="test-repo",
            workspace="default",
            dir=test_dir,
            commit_hash="test-commit",
            comment="Test plan",
            user="test-user",
            files=tf_files
        )
        
        # Verify the payload structure
        assert 'terraform_files' in payload, "Missing terraform_files key in payload"
        assert isinstance(payload['terraform_files'], dict), "terraform_files should be a dictionary"
        
        # Verify file contents are included
        for filename in tf_files:
            assert filename in payload['terraform_files'], f"Missing {filename} in terraform_files"
            file_content = payload['terraform_files'][filename]
            assert isinstance(file_content, str), f"Content of {filename} should be a string"
            assert len(file_content) > 0, f"Content of {filename} is empty"
        
        logger.info("✅ generate_atlantis_payload test passed!")
        
        # Print the payload structure
        logger.info("Payload structure:")
        for key, value in payload.items():
            if key != 'terraform_files':
                logger.info(f"  {key}: {value}")
            else:
                logger.info(f"  {key}: Dictionary with {len(value)} files")
                for filename in value:
                    content_preview = value[filename][:50] + "..." if len(value[filename]) > 50 else value[filename]
                    logger.info(f"    - {filename}: {content_preview}")
        
        return True
    except AssertionError as e:
        logger.error(f"Test failed: {str(e)}")
        return False
    finally:
        # Clean up
        try:
            import shutil
            shutil.rmtree(test_dir)
            logger.info(f"Cleaned up test directory: {test_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up test directory: {str(e)}")

def test_generate_atlantis_apply_payload():
    """Test the generate_atlantis_apply_payload_fixed function"""
    test_dir = create_test_terraform_files()
    
    try:
        logger.info("Testing generate_atlantis_apply_payload_fixed function...")
        
        # Get list of files
        tf_files = [f for f in os.listdir(test_dir) if f.endswith('.tf') or f.endswith('.tfvars')]
        logger.info(f"Test files: {tf_files}")
        
        # Create test config data
        config_data = {
            'server_name': 'test-server',
            'environment': 'development',
            'build_owner': 'test-owner'
        }
        
        # Generate the payload for apply operation
        payload_json = generate_atlantis_apply_payload_fixed(
            config_data=config_data,
            tf_directory=test_dir,
            tf_files=tf_files,
            plan_id="test-plan-id"
        )
        
        # Parse the JSON string
        payload = json.loads(payload_json)
        
        # Verify the payload structure
        assert 'terraform_files' in payload, "Missing terraform_files key in payload"
        assert isinstance(payload['terraform_files'], dict), "terraform_files should be a dictionary"
        
        # Verify file contents are included
        for filename in tf_files:
            assert filename in payload['terraform_files'], f"Missing {filename} in terraform_files"
            file_content = payload['terraform_files'][filename]
            assert isinstance(file_content, str), f"Content of {filename} should be a string"
            assert len(file_content) > 0, f"Content of {filename} is empty"
        
        logger.info("✅ generate_atlantis_apply_payload_fixed test passed!")
        
        # Print the payload structure
        logger.info("Payload structure:")
        for key, value in payload.items():
            if key != 'terraform_files':
                logger.info(f"  {key}: {value}")
            else:
                logger.info(f"  {key}: Dictionary with {len(value)} files")
                for filename in value:
                    content_preview = value[filename][:50] + "..." if len(value[filename]) > 50 else value[filename]
                    logger.info(f"    - {filename}: {content_preview}")
        
        return True
    except AssertionError as e:
        logger.error(f"Test failed: {str(e)}")
        return False
    finally:
        # Clean up
        try:
            import shutil
            shutil.rmtree(test_dir)
            logger.info(f"Cleaned up test directory: {test_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up test directory: {str(e)}")

def main():
    """Main function"""
    logger.info("Starting Atlantis payload format test")
    
    # Test both functions
    plan_test_result = test_generate_atlantis_payload()
    apply_test_result = test_generate_atlantis_apply_payload()
    
    # Report results
    if plan_test_result and apply_test_result:
        logger.info("🎉 All tests passed! The Atlantis payload formatting fix is working correctly.")
        return 0
    else:
        logger.error("❌ Some tests failed! The Atlantis payload formatting fix is not working correctly.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
