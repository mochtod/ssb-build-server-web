#!/usr/bin/env python3
"""
Test Script for EBDC Resource Loading.

This script tests the loading of resources specifically from the 
EBDC NONPROD and EBDC PROD datacenters, with filtering of local datastores.
"""
import os
import logging
import json
import time
import re
from pathlib import Path
from vsphere_cluster_resources import get_ebdc_resources

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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file first
env_loaded = load_env_file()
if env_loaded:
    logger.info("Environment variables loaded from .env file")
else:
    logger.warning("No .env file found or could not be loaded")

def main():
    """Main function to test EBDC resources loading."""
    logger.info("Testing EBDC Resources Loading")
    
    # Check if environment variables are set
    logger.info("Checking environment variables...")
    vsphere_server = os.environ.get('VSPHERE_SERVER')
    vsphere_user = os.environ.get('VSPHERE_USER')
    vsphere_password = os.environ.get('VSPHERE_PASSWORD')
    
    if not vsphere_server or not vsphere_user or not vsphere_password:
        logger.warning("Missing vSphere connection details in environment variables.")
        logger.warning("Continuing with default values for simulation purposes")
        # Set dummy values for testing - these won't actually connect but allow code to proceed
        os.environ['VSPHERE_SERVER'] = 'vsphere-server'
        os.environ['VSPHERE_USER'] = 'vsphere-username'
        os.environ['VSPHERE_PASSWORD'] = 'vsphere-password'
        logger.info("Set dummy vSphere environment variables for testing")
    
    # Get EBDC resources with force_refresh=True to bypass cache
    logger.info("Retrieving resources from EBDC NONPROD and EBDC PROD datacenters...")
    start_time = time.time()
    
    resources = get_ebdc_resources(force_refresh=True)
    
    elapsed_time = time.time() - start_time
    logger.info(f"Retrieved resources in {elapsed_time:.2f} seconds.")
    
    # Check if we got datacenters
    if not resources.get('clusters'):
        logger.error("No clusters found. Possible connection issues or the specified datacenters don't exist.")
        return False
    
    # Output resources information
    clusters = resources.get('clusters', [])
    clusters_by_dc = resources.get('clusters_by_datacenter', {})
    
    logger.info(f"Found {len(clusters)} clusters across {len(clusters_by_dc)} datacenters.")
    
    # Print datacenter/cluster information
    for dc_name, dc_clusters in clusters_by_dc.items():
        print(f"\nDatacenter: {dc_name} - {len(dc_clusters)} clusters")
        
        for cluster in dc_clusters:
            cluster_id = cluster['id']
            cluster_name = cluster['name']
            print(f"  Cluster: {cluster_name} (ID: {cluster_id})")
            
            # Get cluster resources
            cluster_resources = resources.get('resources', {}).get(cluster_id, {})
            
            resource_pools = cluster_resources.get('resource_pools', [])
            print(f"    Resource Pools: {len(resource_pools)}")
            
            datastores = cluster_resources.get('datastores', [])
            print(f"    Datastores: {len(datastores)} (filtered, no '_local' datastores)")
            for ds in datastores[:3]:  # Print first 3
                print(f"      - {ds['name']} (Free: {ds.get('free_gb', 'N/A')} GB)")
            if len(datastores) > 3:
                print(f"      - ... and {len(datastores) - 3} more")
            
            networks = cluster_resources.get('networks', [])
            print(f"    Networks: {len(networks)}")
            for net in networks[:3]:  # Print first 3
                print(f"      - {net['name']}")
            if len(networks) > 3:
                print(f"      - ... and {len(networks) - 3} more")
    
    # Save to file for review
    output_file = "ebdc_resources.json"
    with open(output_file, "w") as f:
        json.dump(resources, f, indent=2)
    
    logger.info(f"Resources saved to {output_file} for review")
    logger.info("Test completed successfully")
    
    return True

if __name__ == "__main__":
    main()
