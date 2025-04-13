#!/usr/bin/env python3
"""
End-to-end test for the SSB Build Server Web application.
This script tests the complete workflow from VM configuration to VM creation,
including Atlantis plan, approval, and apply operations.
"""
import os
import sys
import json
import time
import requests
import argparse
from datetime import datetime

# Test configuration
TEST_CONFIG = {
    'server_prefix': 'lin2dv2',
    'app_name': 'test',
    'quantity': 1,
    'num_cpus': 2,
    'memory': 4096,
    'disk_size': 50,
    'additional_disks': [],
    'username': 'admin',
    'password': 'admin123'
}

def log(message):
    """Log a message with timestamp"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def test_environment_vars():
    """Test that all required environment variables are set"""
    log("Testing environment variables...")
    required_vars = [
        'VSPHERE_USER', 'VSPHERE_PASSWORD', 'VSPHERE_SERVER',
        'RESOURCE_POOL_ID', 'DEV_RESOURCE_POOL_ID', 'DATASTORE_ID',
        'NETWORK_ID_PROD', 'NETWORK_ID_DEV', 'TEMPLATE_UUID'
    ]
    
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        log(f"WARNING: Missing environment variables: {', '.join(missing_vars)}")
        log("VM provisioning will fall back to simulation mode")
    else:
        log("All required environment variables are set")
    
    return len(missing_vars) == 0

def simulate_workflow(base_url, config, session):
    """Simulate the complete workflow"""
    log(f"Starting workflow simulation with server name: {config['server_prefix']}-{config['app_name']}")
    
    # Submit VM configuration
    log("Submitting VM configuration...")
    response = session.post(f"{base_url}/submit", data=config)
    if response.status_code != 200:
        log(f"Failed to submit VM configuration: {response.status_code}")
        return False
    
    # Extract the request_id and timestamp from the redirect URL
    redirect_url = response.url
    parts = redirect_url.split('/')[-1].split('_')
    if len(parts) != 2:
        log(f"Failed to extract request_id and timestamp from URL: {redirect_url}")
        return False
    
    request_id, timestamp = parts
    log(f"VM configuration created with request_id: {request_id}, timestamp: {timestamp}")
    
    # Run Terraform plan
    log("Running Terraform plan...")
    response = session.post(f"{base_url}/plan/{request_id}_{timestamp}")
    if response.status_code != 200:
        log(f"Failed to run Terraform plan: {response.status_code}")
        return False
    
    log("Terraform plan completed successfully")
    
    # Approve the plan (as admin)
    log("Approving Terraform plan...")
    approve_data = {
        'approval_notes': 'Approved by automated test'
    }
    response = session.post(f"{base_url}/approve/{request_id}_{timestamp}", data=approve_data)
    if response.status_code != 200:
        log(f"Failed to approve Terraform plan: {response.status_code}")
        return False
    
    log("Terraform plan approved successfully")
    
    # Build the VM
    log("Building VM...")
    response = session.post(f"{base_url}/build/{request_id}_{timestamp}")
    if response.status_code != 200:
        log(f"Failed to build VM: {response.status_code}")
        return False
    
    log("VM build submitted successfully")
    
    # Verify the build result
    response = session.get(f"{base_url}/build_receipt/{request_id}_{timestamp}")
    if response.status_code != 200:
        log(f"Failed to get build receipt: {response.status_code}")
        return False
    
    log("Test completed successfully")
    return True

def verify_fallback_mechanism(config_dir, request_id, timestamp):
    """Verify that the fallback mechanism is working properly"""
    config_file = os.path.join(config_dir, f"{request_id}_{timestamp}.json")
    if not os.path.exists(config_file):
        log(f"Config file not found: {config_file}")
        return False
    
    with open(config_file, 'r') as f:
        config_data = json.load(f)
    
    # Check if build status is 'submitted'
    if config_data.get('build_status') != 'submitted':
        log(f"Build status is not 'submitted': {config_data.get('build_status')}")
        return False
    
    # Check if a build receipt was generated
    if not config_data.get('build_receipt'):
        log("No build receipt was generated")
        return False
    
    log("Fallback mechanism verified successfully")
    return True

def main():
    parser = argparse.ArgumentParser(description='Run end-to-end tests for the SSB Build Server Web application')
    parser.add_argument('--base-url', default='http://localhost:5150', help='Base URL of the application')
    parser.add_argument('--config-dir', default='configs', help='Directory for configuration files')
    args = parser.parse_args()
    
    log("Starting end-to-end tests...")
    
    # Check environment variables
    env_vars_set = test_environment_vars()
    
    # Start a session for the tests
    session = requests.Session()
    
    # Login as admin
    login_data = {
        'username': TEST_CONFIG['username'],
        'password': TEST_CONFIG['password']
    }
    log(f"Logging in as {login_data['username']}...")
    response = session.post(f"{args.base_url}/login", data=login_data)
    if response.status_code != 200:
        log(f"Failed to login: {response.status_code}")
        sys.exit(1)
    
    log("Login successful")
    
    # Simulate the workflow
    if simulate_workflow(args.base_url, TEST_CONFIG, session):
        log("End-to-end tests completed successfully")
        sys.exit(0)
    else:
        log("End-to-end tests failed")
        sys.exit(1)

if __name__ == '__main__':
    main()
