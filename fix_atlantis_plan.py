#!/usr/bin/env python3
"""
Fix for the Atlantis plan API call in the SSB Build Server Web application.

This script modifies the plan payload to include all required fields and
fixes the validation error in the API request.
"""
import sys
import json
import os
import logging
import time
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Atlantis API configuration
ATLANTIS_URL = os.environ.get("ATLANTIS_URL", "http://localhost:4141")
ATLANTIS_TOKEN = os.environ.get("ATLANTIS_TOKEN", "your-atlantis-api-secret")

def fix_atlantis_plan(payload_string):
    """
    Take a plan payload string and fix it to include required fields
    
    Args:
        payload_string (str): JSON payload string to fix
        
    Returns:
        str: Fixed JSON payload string
    """
    try:
        # Parse the payload
        payload = json.loads(payload_string)
        
        # Ensure environment field is present (critical - must match workspace)
        if 'workspace' in payload and 'environment' not in payload:
            payload['environment'] = payload['workspace']
        
        # Ensure dir field is present (required)
        if 'dir' not in payload:
            payload['dir'] = '.'
        
        # Make sure cmd field is present
        if 'cmd' not in payload:
            payload['cmd'] = 'plan'
        
        # Return the fixed payload
        return json.dumps(payload, ensure_ascii=False)
    
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in payload: {payload_string[:100]}...")
        return payload_string

def generate_fixed_plan_payload(config_data, tf_directory, tf_files):
    """Generate a properly formatted Atlantis API payload for plan operation"""
    # Get the directory name for the Terraform files
    tf_dir_name = os.path.basename(os.path.normpath(tf_directory))
    
    # Generate a unique hostname for this VM
    vm_hostname = f"{config_data['server_name']}-{config_data.get('start_number', '0')}"
    
    # Create a dictionary with all the necessary fields
    payload_dict = {
        'repo': {
            'owner': 'fake',
            'name': 'terraform-repo',
            'clone_url': 'https://github.com/fake/terraform-repo.git'
        },
        'pull_request': {
            'num': 1,
            'branch': 'main',
            'author': config_data.get('build_owner', 'Admin User')
        },
        'head_commit': 'abcd1234',
        'pull_num': 1,
        'pull_author': config_data.get('build_owner', 'Admin User'),
        'repo_rel_dir': tf_dir_name,
        'workspace': config_data.get('environment', 'development'),
        'project_name': vm_hostname,
        'plan_only': True,
        'comment': f"VM Provisioning Plan: {vm_hostname}",
        'user': config_data.get('build_owner', 'Admin User'),
        'verbose': True,
        'cmd': 'plan',             # Critical: ensure command is explicitly set to 'plan'
        'dir': '.',                # Critical: add the 'dir' field that's required
        'terraform_files': tf_files,
        'environment': config_data.get('environment', 'development')  # Critical: environment field must be present
    }
    
    # Convert to JSON string with proper formatting
    payload_string = json.dumps(payload_dict, ensure_ascii=False)
    
    return payload_string

def test_fixed_payload(tf_directory="terraform/d300b7a0_20250416152430"):
    """Test the fixed payload against Atlantis API"""
    config_data = {
        'server_name': 'lin2dv2-ssb',
        'environment': 'development',
        'build_owner': 'Admin User',
        'start_number': 10001
    }
    
    # Get all terraform files in the directory
    tf_files = {}
    for filename in os.listdir(tf_directory):
        if filename.endswith('.tf') or filename.endswith('.tfvars'):
            file_path = os.path.join(tf_directory, filename)
            with open(file_path, 'r') as f:
                tf_files[filename] = f.read()
    
    # Generate the fixed payload
    fixed_payload = generate_fixed_plan_payload(config_data, tf_directory, tf_files)
    
    logger.info(f"Generated fixed payload (first 100 chars): {fixed_payload[:100]}...")
    
    # Call Atlantis API
    headers = {
        'Content-Type': 'application/json',
        'X-Atlantis-Token': ATLANTIS_TOKEN
    }
    
    try:
        logger.info(f"Sending plan request to Atlantis with fixed payload")
        response = requests.post(
            f"{ATLANTIS_URL}/api/plan", 
            data=fixed_payload, 
            headers=headers
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to trigger Atlantis plan: HTTP {response.status_code}")
            logger.error(f"Response: {response.text}")
            return False
        else:
            plan_response = response.json()
            plan_id = plan_response.get('id', '')
            logger.info(f"Plan successful! Plan ID: {plan_id}")
            return True
    
    except Exception as e:
        logger.exception(f"Error calling Atlantis API: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # If a directory is provided as argument, test with that
        test_fixed_payload(sys.argv[1])
    else:
        # Default test
        test_fixed_payload()
