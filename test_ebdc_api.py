#!/usr/bin/env python3
"""
Test Script for EBDC Resources API Endpoint.

This script tests the API endpoint we added to app.py for retrieving
resources specifically from EBDC NONPROD and EBDC PROD datacenters.
"""
import os
import json
import requests
import time
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_env_file(env_file='.env'):
    """Load environment variables from .env file."""
    if not os.path.isfile(env_file):
        return False
    
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            # Parse key-value pairs
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Remove quotes if present
                if value and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                
                # Set environment variable if not already set
                if key and key not in os.environ:
                    os.environ[key] = value
    
    return True

def start_flask_app():
    """Start the Flask app in a separate process."""
    import subprocess
    import time
    import sys
    
    logger.info("Starting Flask app for testing...")
    
    # Set local environment variables to fix path issues
    env = os.environ.copy()
    env['CONFIG_DIR'] = './configs'  # Local path
    env['TERRAFORM_DIR'] = './terraform'  # Local path
    env['USERS_FILE'] = './users.json'  # Local path instead of /app/users.json
    
    # Start the Flask app
    process = subprocess.Popen(
        [sys.executable, "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )
    
    # Wait for the app to start
    time.sleep(2)
    
    # Check if the app started successfully
    if process.poll() is not None:
        logger.error("Flask app failed to start!")
        stdout, stderr = process.communicate()
        logger.error(f"STDOUT: {stdout.decode('utf-8')}")
        logger.error(f"STDERR: {stderr.decode('utf-8')}")
        return None
    
    logger.info("Flask app started successfully")
    return process

def test_ebdc_resources_api():
    """Test the EBDC resources API endpoint."""
    logger.info("Testing EBDC resources API endpoint...")
    
    try:
        # Make a request to the API endpoint
        start_time = time.time()
        response = requests.get("http://localhost:5150/api/vsphere/ebdc_resources")
        
        # Check if the request was successful
        if response.status_code != 200:
            logger.error(f"API request failed with status code {response.status_code}")
            logger.error(f"Response: {response.text}")
            return False
        
        # Parse the response
        data = response.json()
        elapsed_time = time.time() - start_time
        logger.info(f"API request completed in {elapsed_time:.2f} seconds")
        
        # Check if the response contains the expected data
        if 'datacenters' not in data:
            logger.error("Response does not contain 'datacenters' field")
            logger.error(f"Response: {data}")
            return False
        
        # Log some information about the response
        datacenters = data['datacenters']
        logger.info(f"Found {len(datacenters)} datacenters in the API response")
        
        # Print datacenter/cluster information
        for dc in datacenters:
            dc_name = dc['name']
            clusters = dc['clusters']
            print(f"\nDatacenter: {dc_name} - {len(clusters)} clusters")
            
            for cluster in clusters:
                cluster_id = cluster['id']
                cluster_name = cluster['name']
                print(f"  Cluster: {cluster_name} (ID: {cluster_id})")
                
                # Log datacenter resource information
                resource_pools = cluster.get('resource_pools', [])
                print(f"    Resource Pools: {len(resource_pools)}")
                
                datastores = cluster.get('datastores', [])
                print(f"    Datastores: {len(datastores)} (filtered, no '_local' datastores)")
                for ds in datastores[:3]:  # Print first 3
                    print(f"      - {ds['name']} (Free: {ds.get('free_gb', 'N/A')} GB)")
                if len(datastores) > 3:
                    print(f"      - ... and {len(datastores) - 3} more")
                
                networks = cluster.get('networks', [])
                print(f"    Networks: {len(networks)}")
                for net in networks[:3]:  # Print first 3
                    print(f"      - {net['name']}")
                if len(networks) > 3:
                    print(f"      - ... and {len(networks) - 3} more")
        
        # Save the response to a file for review
        output_file = "ebdc_api_response.json"
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"API response saved to {output_file} for review")
        logger.info("API test completed successfully")
        
        return True
    
    except Exception as e:
        logger.exception(f"Error testing API: {str(e)}")
        return False

def main():
    """Main function to test EBDC resources API endpoint."""
    # Load environment variables from .env file
    env_loaded = load_env_file()
    if env_loaded:
        logger.info("Environment variables loaded from .env file")
    else:
        logger.warning("No .env file found or could not be loaded")
    
    # Check if we should start the Flask app
    start_app = os.environ.get('START_FLASK_APP', 'false').lower() in ('true', 'yes', '1')
    flask_process = None
    
    try:
        if start_app:
            flask_process = start_flask_app()
            if not flask_process:
                logger.error("Failed to start Flask app, cannot test API")
                return False
        
        # Test the API endpoint
        success = test_ebdc_resources_api()
        
        return success
    
    finally:
        # Terminate the Flask app if we started it
        if flask_process:
            logger.info("Terminating Flask app...")
            flask_process.terminate()
            flask_process.wait()
            logger.info("Flask app terminated")

if __name__ == "__main__":
    # Set START_FLASK_APP=true to start the Flask app for testing
    os.environ['START_FLASK_APP'] = 'true'
    
    main()
