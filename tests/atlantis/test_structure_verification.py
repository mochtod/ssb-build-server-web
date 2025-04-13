#!/usr/bin/env python3
"""
Test script for verifying Terraform structure and Atlantis payload generation.

This script verifies that the enhanced configuration structure and Atlantis
payload generation functions work correctly.
"""
import os
import sys
import json
import logging
import tempfile
import shutil
from pathlib import Path

# Add the root directory to the path to import modules
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_DIR)

# Import modules
from fix_atlantis_apply import generate_atlantis_payload, generate_atlantis_apply_payload_fixed, ensure_terraform_structure
from terraform.ensure_config_structure import ensure_directory_structure

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_ensure_terraform_structure():
    """
    Test that the ensure_terraform_structure function creates the required files.
    """
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Ensure the structure
        result = ensure_terraform_structure(temp_dir)
        
        logger.info(f"Structure result: {result}")
        
        # Check if the required files exist
        providers_file = os.path.join(temp_dir, 'providers.tf')
        variables_file = os.path.join(temp_dir, 'variables.tf')
        
        assert os.path.exists(providers_file), f"providers.tf doesn't exist at {providers_file}"
        assert os.path.exists(variables_file), f"variables.tf doesn't exist at {variables_file}"
        
        # Check the content of providers.tf (minimal check)
        with open(providers_file, 'r') as f:
            content = f.read()
            assert 'terraform {' in content, "providers.tf doesn't contain the terraform block"
            assert 'required_providers {' in content, "providers.tf doesn't contain the required_providers block"
            assert 'vsphere = {' in content, "providers.tf doesn't contain the vsphere provider"
            assert 'provider "vsphere"' in content, "providers.tf doesn't contain the vsphere provider block"
        
        # Check the content of variables.tf (minimal check)
        with open(variables_file, 'r') as f:
            content = f.read()
            assert 'variable "vsphere_user"' in content, "variables.tf doesn't contain the vsphere_user variable"
            assert 'variable "vsphere_password"' in content, "variables.tf doesn't contain the vsphere_password variable"
        
        logger.info("ensure_terraform_structure test passed!")

def test_generate_atlantis_payload():
    """
    Test that the generate_atlantis_payload function creates a valid payload.
    """
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a test file
        tf_content = """
resource "vsphere_virtual_machine" "test" {
  name = "test-vm"
}
"""
        with open(os.path.join(temp_dir, 'main.tf'), 'w') as f:
            f.write(tf_content)
        
        # Generate the payload
        payload = generate_atlantis_payload(
            repo="test-repo",
            workspace="development",
            dir=temp_dir,
            commit_hash="test-commit",
            comment="test plan",
            user="test-user",
            files=['main.tf']
        )
        
        # Check if the payload contains all the required fields
        required_fields = [
            'repo', 'pull_request', 'head_commit', 'pull_num', 'pull_author', 
            'repo_rel_dir', 'workspace', 'project_name', 'comment', 'user', 
            'cmd', 'dir', 'terraform_files', 'environment'
        ]
        
        for field in required_fields:
            assert field in payload, f"Payload missing required field: {field}"
        
        # Check if the payload contains the required providers.tf and variables.tf
        assert 'providers.tf' in payload['terraform_files'], "Payload missing providers.tf"
        assert 'variables.tf' in payload['terraform_files'], "Payload missing variables.tf"
        assert 'main.tf' in payload['terraform_files'], "Payload missing main.tf"
        
        # Check environment field is set correctly
        assert payload['environment'] == 'development', f"Payload has wrong environment: {payload['environment']}"
        
        # Dump the payload to a file for manual inspection
        with open(os.path.join(ROOT_DIR, 'test-payload-generated.json'), 'w') as f:
            json.dump(payload, f, indent=2)
        
        logger.info("generate_atlantis_payload test passed!")

def test_generate_atlantis_apply_payload_fixed():
    """
    Test that the generate_atlantis_apply_payload_fixed function creates a valid apply payload.
    """
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a test file
        tf_content = """
resource "vsphere_virtual_machine" "test" {
  name = "test-vm"
}
"""
        with open(os.path.join(temp_dir, 'main.tf'), 'w') as f:
            f.write(tf_content)
        
        # Create a test config
        config_data = {
            'server_name': 'test-server',
            'environment': 'development',
            'request_id': 'test-request',
            'build_owner': 'test-owner'
        }
        
        # Generate the payload
        payload_string = generate_atlantis_apply_payload_fixed(
            config_data=config_data,
            tf_directory=temp_dir,
            tf_files=['main.tf'],
            plan_id="test-plan-id"
        )
        
        # Parse the JSON string
        payload = json.loads(payload_string)
        
        # Check if the payload contains all the required fields
        required_fields = [
            'repo', 'pull_request', 'head_commit', 'pull_num', 'pull_author', 
            'repo_rel_dir', 'workspace', 'project_name', 'plan_id', 'comment', 
            'user', 'cmd', 'dir', 'terraform_files', 'environment'
        ]
        
        for field in required_fields:
            assert field in payload, f"Apply payload missing required field: {field}"
        
        # Check if the payload contains the required providers.tf and variables.tf
        assert 'providers.tf' in payload['terraform_files'], "Apply payload missing providers.tf"
        assert 'variables.tf' in payload['terraform_files'], "Apply payload missing variables.tf"
        assert 'main.tf' in payload['terraform_files'], "Apply payload missing main.tf"
        
        # Check environment field is set correctly
        assert payload['environment'] == 'development', f"Apply payload has wrong environment: {payload['environment']}"
        
        # Check command is apply
        assert payload['cmd'] == 'apply', f"Apply payload has wrong command: {payload['cmd']}"
        
        # Check dir field
        assert payload['dir'] == '.', f"Apply payload has wrong dir: {payload['dir']}"
        
        # Dump the payload to a file for manual inspection
        with open(os.path.join(ROOT_DIR, 'test-apply-payload-generated.json'), 'w') as f:
            json.dump(payload, f, indent=2)
        
        logger.info("generate_atlantis_apply_payload_fixed test passed!")

def test_with_existing_terraform_config():
    """
    Test with an existing Terraform configuration from the test_config directory.
    """
    # Path to the test_config directory
    test_config_dir = os.path.join(ROOT_DIR, 'terraform', 'test_config')
    
    # Check if the directory exists
    if not os.path.exists(test_config_dir):
        logger.error(f"Test config directory doesn't exist: {test_config_dir}")
        return
    
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Copy the test config to the temporary directory
        for filename in os.listdir(test_config_dir):
            if filename.endswith('.tf') or filename.endswith('.tfvars'):
                shutil.copy(os.path.join(test_config_dir, filename), temp_dir)
        
        # Create a test config
        config_data = {
            'server_name': 'test-server',
            'environment': 'development',
            'request_id': 'test-request',
            'build_owner': 'test-owner'
        }
        
        # Generate the plan payload
        plan_payload = generate_atlantis_payload(
            repo="test-repo",
            workspace="development",
            dir=temp_dir,
            commit_hash="test-commit",
            comment="test plan",
            user="test-user",
            files=[f for f in os.listdir(temp_dir) if f.endswith('.tf') or f.endswith('.tfvars')]
        )
        
        # Generate the apply payload
        apply_payload_string = generate_atlantis_apply_payload_fixed(
            config_data=config_data,
            tf_directory=temp_dir,
            tf_files=[f for f in os.listdir(temp_dir) if f.endswith('.tf') or f.endswith('.tfvars')],
            plan_id="test-plan-id"
        )
        
        # Parse the JSON string
        apply_payload = json.loads(apply_payload_string)
        
        # Dump the payloads to files for manual inspection
        with open(os.path.join(ROOT_DIR, 'test-plan-payload-real-config.json'), 'w') as f:
            json.dump(plan_payload, f, indent=2)
        
        with open(os.path.join(ROOT_DIR, 'test-apply-payload-real-config.json'), 'w') as f:
            json.dump(apply_payload, f, indent=2)
        
        logger.info("Test with existing Terraform config passed!")

def main():
    """Main entry point"""
    try:
        logger.info("Running ensure_terraform_structure test...")
        test_ensure_terraform_structure()
        
        logger.info("\nRunning generate_atlantis_payload test...")
        test_generate_atlantis_payload()
        
        logger.info("\nRunning generate_atlantis_apply_payload_fixed test...")
        test_generate_atlantis_apply_payload_fixed()
        
        logger.info("\nRunning test with existing Terraform config...")
        test_with_existing_terraform_config()
        
        logger.info("\nAll tests passed successfully!")
        return 0
    except Exception as e:
        logger.error(f"Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
