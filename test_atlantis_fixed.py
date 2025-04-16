#!/usr/bin/env python3
"""
Test script to verify the fixed Atlantis API integration.
"""
import os
import json
import requests
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get Atlantis configuration from environment
ATLANTIS_URL = os.environ.get("ATLANTIS_URL", "http://localhost:4141")
ATLANTIS_TOKEN = os.environ.get("ATLANTIS_TOKEN", "your-atlantis-api-secret")

def test_atlantis_plan_api():
    """Test the Atlantis plan API with our fixed payload structure"""
    
    # Simulate a basic configuration and terraform files
    config_data = {
        'server_name': 'lin2dv2-test',
        'build_owner': 'Test User',
        'environment': 'development',
        'start_number': 10001
    }
    
    tf_directory = "test_" + uuid.uuid4().hex[:8]
    
    # Create a simplified terraform files dictionary
    tf_files = {
        'main.tf': """
resource "null_resource" "test" {
  provisioner "local-exec" {
    command = "echo Hello, Atlantis!"
  }
}
""",
        'variables.tf': """
variable "test_var" {
  description = "A test variable"
  default = "test"
}
"""
    }
    
    # Generate the payload with our updated structure
    payload_dict = {
        'repo': {
            'owner': 'fake',
            'name': 'terraform-repo',
            'clone_url': 'https://github.com/fake/terraform-repo.git'
        },
        'pull_request': {
            'num': 1,
            'branch': 'main',
            'author': config_data['build_owner']
        },
        'head_commit': 'abcd1234',
        'pull_num': 1,
        'pull_author': config_data['build_owner'],
        'repo_rel_dir': tf_directory,
        'workspace': config_data['environment'],
        'project_name': f"{config_data['server_name']}-{config_data['start_number']}",
        'comment': f"VM Provisioning Plan: {config_data['server_name']}-{config_data['start_number']}",
        'user': config_data['build_owner'],
        'verbose': True,
        'cmd': 'plan',
        'dir': '.',
        'terraform_files': tf_files,
        'environment': config_data['environment'],
        # Added fields that were missing before
        'atlantis_workflow': 'custom',
        'autoplan': False,
        'parallel_plan': False,
        'parallel_apply': False,
        'terraform_version': '',
        'log_level': 'info'
    }
    
    # Convert to JSON string
    payload_string = json.dumps(payload_dict, ensure_ascii=False)
    
    # Set up headers
    headers = {
        'Content-Type': 'application/json',
        'X-Atlantis-Token': ATLANTIS_TOKEN
    }
    
    logger.info(f"Testing Atlantis plan API with payload: {payload_string[:100]}...")
    
    try:
        # Call Atlantis API
        response = requests.post(f"{ATLANTIS_URL}/api/plan", data=payload_string, headers=headers)
        
        # Check the response
        if response.status_code == 200:
            plan_response = response.json()
            plan_id = plan_response.get('plan_id')
            
            if plan_id:
                logger.info(f"Success! Plan API call returned plan_id: {plan_id}")
                return True, plan_id
            else:
                logger.error(f"Plan API call succeeded but no plan_id returned. Response: {plan_response}")
                return False, None
        else:
            logger.error(f"Plan API call failed with status code {response.status_code}. Response: {response.text}")
            return False, None
    
    except Exception as e:
        logger.error(f"Error calling Atlantis API: {str(e)}")
        return False, None

if __name__ == "__main__":
    logger.info("Testing Atlantis API integration with fixed payload...")
    success, plan_id = test_atlantis_plan_api()
    
    if success:
        logger.info(f"Test successful! Plan ID: {plan_id}")
        logger.info(f"Plan URL: {ATLANTIS_URL}/plan/{plan_id}")
    else:
        logger.error("Test failed. Please check the logs for details.")
