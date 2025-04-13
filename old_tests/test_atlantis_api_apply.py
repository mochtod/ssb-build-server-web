#!/usr/bin/env python3
"""
Test script for the Atlantis apply API.

This script tests the Atlantis apply API with a properly formatted payload
to verify that the fix for the missing 'dir' field works correctly.
"""
import os
import json
import requests
import argparse
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Test Atlantis API apply endpoint')
    parser.add_argument('--atlantis-url', 
                        default=os.environ.get('ATLANTIS_URL', 'http://localhost:4141'),
                        help='Atlantis server URL')
    parser.add_argument('--token', 
                        default=os.environ.get('ATLANTIS_TOKEN', ''),
                        help='Atlantis API token')
    parser.add_argument('--plan-id',
                        default=f"test-{uuid.uuid4().hex[:8]}",
                        help='Plan ID to use for apply (default: auto-generated)')
    return parser.parse_args()

def generate_test_payload(plan_id):
    """Generate a test payload for the apply API"""
    payload = {
        'repo': {
            'owner': 'fake',
            'name': 'terraform-repo',
            'clone_url': 'https://github.com/fake/terraform-repo.git'
        },
        'pull_request': {
            'num': 1,
            'branch': 'main',
            'author': 'Test User'
        },
        'head_commit': 'abcd1234',
        'pull_num': 1,
        'pull_author': 'Test User',
        'repo_rel_dir': 'test-dir',
        'workspace': 'development',
        'project_name': 'test-project',
        'plan_id': plan_id,
        'comment': 'Testing Atlantis apply API',
        'user': 'Test User',
        'verbose': True,
        'cmd': 'apply',
        'dir': '.',  # Critical: Include the 'dir' field
        'terraform_files': {
            'main.tf': 'output "test" { value = "Hello, World!" }'
        }
    }
    return payload

def test_apply_api(atlantis_url, token, plan_id):
    """Test the Atlantis apply API"""
    api_url = f"{atlantis_url}/api/apply"
    
    # Generate payload
    payload = generate_test_payload(plan_id)
    payload_json = json.dumps(payload)
    
    # Set up headers
    headers = {
        'Content-Type': 'application/json',
        'X-Atlantis-Token': token
    }
    
    logger.info(f"Testing Atlantis apply API at: {api_url}")
    logger.info(f"Using plan ID: {plan_id}")
    logger.info(f"Payload preview: {payload_json[:100]}...")
    
    try:
        # Make API request
        response = requests.post(api_url, data=payload_json, headers=headers)
        
        # Log response information
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response body: {response.text}")
        
        # Check if request was successful
        if response.status_code == 200:
            logger.info("API request was successful!")
            try:
                # Parse response JSON
                response_data = response.json()
                logger.info(f"Apply ID: {response_data.get('apply_id', 'N/A')}")
                return True
            except json.JSONDecodeError:
                logger.error("Failed to parse response JSON")
                return False
        else:
            logger.error("API request failed")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to Atlantis API: {str(e)}")
        return False

def main():
    args = parse_args()
    
    # Validate token
    if not args.token:
        logger.error("No Atlantis token provided")
        logger.error("Please provide a token with --token or set the ATLANTIS_TOKEN environment variable")
        return False
    
    # Test API
    success = test_apply_api(args.atlantis_url, args.token, args.plan_id)
    
    if success:
        logger.info("Atlantis apply API test PASSED")
        return 0
    else:
        logger.error("Atlantis apply API test FAILED")
        return 1

if __name__ == "__main__":
    exit(main())
