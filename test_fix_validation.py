#!/usr/bin/env python3
"""
Test script to verify that the Atlantis API payload fix works correctly.
This script:
1. Creates test configuration data
2. Generates both plan and apply payloads using the fixed functions
3. Validates that all required fields are present
4. Reports the results
"""
import os
import json
import logging
import sys
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the fixed functions
from fix_atlantis_apply import generate_atlantis_payload, generate_atlantis_apply_payload_fixed

def create_test_files():
    """Create temporary test Terraform files"""
    test_dir = os.path.join(tempfile.gettempdir(), "atlantis_test_" + os.urandom(4).hex())
    os.makedirs(test_dir, exist_ok=True)
    logger.info(f"Created test directory: {test_dir}")
    
    # Create a simple machine.tf file
    machine_tf = """
resource "vsphere_virtual_machine" "vm" {
  count = var.quantity
  name  = "${var.name}-${var.start_number + count.index}"
  resource_pool_id = var.resource_pool_id
  datastore_id     = var.datastore_id
  num_cpus         = var.num_cpus
  memory           = var.memory
  guest_id         = var.guest_id
}
"""
    
    with open(os.path.join(test_dir, "machine.tf"), "w") as f:
        f.write(machine_tf)
    
    # Create a terraform.tfvars file
    tfvars = """
name = "lin2dv2-test"
num_cpus = 2
memory = 4096
disk_size = 50
quantity = 1
"""
    
    with open(os.path.join(test_dir, "terraform.tfvars"), "w") as f:
        f.write(tfvars)
    
    return test_dir

def create_test_config():
    """Create a test VM configuration"""
    return {
        'request_id': '96529c2c',
        'timestamp': '20250412221543',
        'server_name': 'lin2dv2-fds',
        'server_prefix': 'lin2dv2',
        'app_name': 'fds',
        'quantity': 1,
        'num_cpus': 2,
        'memory': 4096,
        'disk_size': 50,
        'additional_disks': [],
        'environment': 'development',
        'start_number': 10001,
        'build_status': 'pending',
        'plan_status': 'pending',
        'approval_status': 'pending',
        'build_owner': 'Admin User',
        'build_username': 'admin'
    }

def validate_payload_fields(payload, payload_type):
    """Validate that all required fields are present in the payload"""
    # Common required fields for both plan and apply
    required_fields = [
        'repo', 'pull_request', 'head_commit', 'pull_num', 'pull_author',
        'repo_rel_dir', 'workspace', 'project_name', 'comment',
        'user', 'cmd', 'dir', 'terraform_files', 'environment'
    ]
    
    # Apply-specific required fields
    if payload_type == 'apply':
        required_fields.append('plan_id')
    
    # Convert string payload to dict if needed
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse payload JSON: {str(e)}")
            return False, [f"JSON parsing error: {str(e)}"]
    
    # Check for missing fields
    missing_fields = [field for field in required_fields if field not in payload]
    
    # Check nested objects
    if 'repo' in payload:
        repo_fields = ['owner', 'name', 'clone_url']
        missing_repo_fields = [f"repo.{field}" for field in repo_fields if field not in payload['repo']]
        missing_fields.extend(missing_repo_fields)
    
    if 'pull_request' in payload:
        pr_fields = ['num', 'branch', 'author']
        missing_pr_fields = [f"pull_request.{field}" for field in pr_fields if field not in payload['pull_request']]
        missing_fields.extend(missing_pr_fields)
    
    return len(missing_fields) == 0, missing_fields

def test_plan_payload():
    """Test the plan payload generation"""
    test_dir = create_test_files()
    try:
        # Get the list of terraform files
        tf_files = [f for f in os.listdir(test_dir) if f.endswith('.tf') or f.endswith('.tfvars')]
        
        # Generate the plan payload
        payload = generate_atlantis_payload(
            repo="build-server-repo",
            workspace="default",
            dir=test_dir,
            commit_hash="request-96529c2c",
            comment="plan",
            user="admin",
            files=tf_files
        )
        
        # Validate the payload
        valid, missing_fields = validate_payload_fields(payload, 'plan')
        
        if valid:
            logger.info("✅ Plan payload validation passed!")
            return True
        else:
            logger.error(f"❌ Plan payload validation failed! Missing fields: {', '.join(missing_fields)}")
            return False
    finally:
        # Clean up
        import shutil
        shutil.rmtree(test_dir)

def test_apply_payload():
    """Test the apply payload generation"""
    test_dir = create_test_files()
    try:
        # Get the list of terraform files
        tf_files = [f for f in os.listdir(test_dir) if f.endswith('.tf') or f.endswith('.tfvars')]
        
        # Create test config
        config = create_test_config()
        
        # Generate the apply payload
        payload_str = generate_atlantis_apply_payload_fixed(
            config_data=config,
            tf_directory=test_dir,
            tf_files=tf_files,
            plan_id="test-plan-123"
        )
        
        # Parse the JSON string
        payload = json.loads(payload_str)
        
        # Validate the payload
        valid, missing_fields = validate_payload_fields(payload, 'apply')
        
        if valid:
            logger.info("✅ Apply payload validation passed!")
            return True
        else:
            logger.error(f"❌ Apply payload validation failed! Missing fields: {', '.join(missing_fields)}")
            return False
    finally:
        # Clean up
        import shutil
        shutil.rmtree(test_dir)

def display_payload_structure(payload_type):
    """Display the structure of either plan or apply payload for reference"""
    test_dir = create_test_files()
    try:
        # Get the list of terraform files
        tf_files = [f for f in os.listdir(test_dir) if f.endswith('.tf') or f.endswith('.tfvars')]
        
        if payload_type == 'plan':
            # Generate the plan payload
            payload = generate_atlantis_payload(
                repo="build-server-repo",
                workspace="default",
                dir=test_dir,
                commit_hash="request-96529c2c",
                comment="plan",
                user="admin",
                files=tf_files
            )
            
            # Convert to string if it's a dict
            if isinstance(payload, dict):
                payload_str = json.dumps(payload, indent=2)
            else:
                payload_str = payload
                
            logger.info(f"Plan Payload Structure:\n{payload_str}")
        else:
            # Create test config
            config = create_test_config()
            
            # Generate the apply payload
            payload_str = generate_atlantis_apply_payload_fixed(
                config_data=config,
                tf_directory=test_dir,
                tf_files=tf_files,
                plan_id="test-plan-123"
            )
            
            logger.info(f"Apply Payload Structure:\n{payload_str}")
    finally:
        # Clean up
        import shutil
        shutil.rmtree(test_dir)

def main():
    """Main function"""
    logger.info("Testing Atlantis payload generation with fixed functions")
    
    # Display sample payloads for reference
    logger.info("\n*** Payload Structures (for reference) ***")
    display_payload_structure('plan')
    display_payload_structure('apply')
    
    # Test both payloads
    logger.info("\n*** Running Validation Tests ***")
    plan_result = test_plan_payload()
    apply_result = test_apply_payload()
    
    # Report results
    if plan_result and apply_result:
        logger.info("\n🎉 All tests passed! The Atlantis payload fix is working correctly.")
        return 0
    else:
        logger.error("\n❌ Some tests failed! The Atlantis payload fix is not working correctly.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
