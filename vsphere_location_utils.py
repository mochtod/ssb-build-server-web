#!/usr/bin/env python3
"""
vSphere Location Utilities for SSB Build Server Web.

This module provides utilities to get the minimal required vSphere resources
needed for VM location when creating a VM with the Terraform vSphere provider.
It works with both the full and minimal resource fetching scripts.
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default paths for resource files
DEFAULT_FULL_RESOURCES_PATH = 'vsphere_resources.json'
DEFAULT_MINIMAL_RESOURCES_PATH = 'vsphere_minimal_resources.json'

def get_vm_location_resources(env_dict: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Get the minimum required vSphere resources for VM location.
    
    This function tries to get the required resources from:
    1. Provided environment dictionary
    2. Environment variables
    3. JSON resource files (minimal first, then full)
    
    Args:
        env_dict: Optional dictionary of environment variables
        
    Returns:
        Dictionary with the required resource IDs
    """
    # Initialize result with empty values
    resources = {
        'resource_pool_id': '',
        'datastore_id': '',
        'network_id': '',
        'template_uuid': ''
    }
    
    # Try to get resources from provided env_dict
    if env_dict:
        resources['resource_pool_id'] = env_dict.get('RESOURCE_POOL_ID', '')
        resources['datastore_id'] = env_dict.get('DATASTORE_ID', '')
        resources['network_id'] = env_dict.get('NETWORK_ID', '')
        resources['template_uuid'] = env_dict.get('TEMPLATE_UUID', '')
    
    # Try to get resources from environment variables if not in env_dict
    if not resources['resource_pool_id']:
        resources['resource_pool_id'] = os.environ.get('RESOURCE_POOL_ID', '')
    if not resources['datastore_id']:
        resources['datastore_id'] = os.environ.get('DATASTORE_ID', '')
    if not resources['network_id']:
        resources['network_id'] = os.environ.get('NETWORK_ID', '')
    if not resources['template_uuid']:
        resources['template_uuid'] = os.environ.get('TEMPLATE_UUID', '')
    
    # If any resource is still missing, try to get from resource files
    if (not resources['resource_pool_id'] or not resources['datastore_id'] or 
            not resources['network_id'] or not resources['template_uuid']):
        # Try minimal resources file first
        file_resources = _load_resources_from_file(DEFAULT_MINIMAL_RESOURCES_PATH)
        if not file_resources:
            # Try full resources file as fallback
            file_resources = _load_resources_from_file(DEFAULT_FULL_RESOURCES_PATH)
        
        # Update missing resources from file
        if file_resources:
            if not resources['resource_pool_id'] and 'resource_pool_id' in file_resources:
                resources['resource_pool_id'] = file_resources['resource_pool_id']
            if not resources['datastore_id'] and 'datastore_id' in file_resources:
                resources['datastore_id'] = file_resources['datastore_id']
            if not resources['network_id'] and 'network_id' in file_resources:
                resources['network_id'] = file_resources['network_id']
            if not resources['template_uuid'] and 'template_uuid' in file_resources:
                resources['template_uuid'] = file_resources['template_uuid']
    
    # Check if all required resources are available
    missing = [key for key, value in resources.items() if not value]
    if missing:
        logger.warning(f"Missing required vSphere resources: {', '.join(missing)}")
    else:
        logger.info("All required vSphere VM location resources are available")
    
    return resources

def _load_resources_from_file(file_path: str) -> Dict[str, str]:
    """
    Load vSphere resources from a JSON file.
    
    Args:
        file_path: Path to the JSON file
        
    Returns:
        Dictionary with resource IDs
    """
    resources = {}
    try:
        if Path(file_path).exists():
            with open(file_path, 'r') as f:
                data = json.load(f)
                
                # Extract resource IDs based on file format
                # For minimal resources file
                if 'ResourcePools' in data and data['ResourcePools']:
                    # Try to find a production resource pool first
                    prod_pools = [rp for rp in data['ResourcePools'] if 'prod' in rp.get('name', '').lower()]
                    if prod_pools:
                        resources['resource_pool_id'] = prod_pools[0]['id']
                    else:
                        # Use the first resource pool as fallback
                        resources['resource_pool_id'] = data['ResourcePools'][0]['id']
                
                if 'Datastores' in data and data['Datastores']:
                    resources['datastore_id'] = data['Datastores'][0]['id']
                
                if 'Networks' in data and data['Networks']:
                    # Try to find a production network first
                    prod_nets = [net for net in data['Networks'] if 'prod' in net.get('name', '').lower()]
                    if prod_nets:
                        resources['network_id'] = prod_nets[0]['id']
                    else:
                        # Use the first network as fallback
                        resources['network_id'] = data['Networks'][0]['id']
                
                if 'Templates' in data and data['Templates']:
                    # Try to find a RHEL9 template first
                    rhel9_templates = [tpl for tpl in data['Templates'] if 'rhel9' in tpl.get('name', '').lower()]
                    if rhel9_templates:
                        resources['template_uuid'] = rhel9_templates[0]['id']
                    else:
                        # Use the first template as fallback
                        resources['template_uuid'] = data['Templates'][0]['id']
                
                logger.info(f"Loaded vSphere VM location resources from {file_path}")
        else:
            logger.warning(f"Resource file {file_path} not found")
    except Exception as e:
        logger.error(f"Error loading resources from {file_path}: {str(e)}")
    
    return resources

def get_terraform_vm_location_vars(env_dict: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Get the vSphere resource variables formatted for Terraform variables.
    
    Args:
        env_dict: Optional dictionary of environment variables
        
    Returns:
        Dictionary with resource variables in Terraform format
    """
    resources = get_vm_location_resources(env_dict)
    
    # Format resources for Terraform variables
    terraform_vars = {
        'resource_pool_id': resources['resource_pool_id'],
        'datastore_id': resources['datastore_id'],
        'network_id': resources['network_id'],
        'template_uuid': resources['template_uuid']
    }
    
    return terraform_vars

def verify_vm_location_resources(resources: Dict[str, str]) -> Tuple[bool, str]:
    """
    Verify if all required vSphere resources for VM location are available.
    
    Args:
        resources: Dictionary with resource IDs
        
    Returns:
        (True/False, message)
    """
    missing = [key for key, value in resources.items() if not value]
    if missing:
        return False, f"Missing required vSphere resources: {', '.join(missing)}"
    
    return True, "All required vSphere VM location resources are available"

if __name__ == "__main__":
    """When run as a script, show current VM location resources."""
    resources = get_vm_location_resources()
    
    print("\n=== vSphere VM Location Resources ===\n")
    print(f"Resource Pool ID: {resources['resource_pool_id']}")
    print(f"Datastore ID:     {resources['datastore_id']}")
    print(f"Network ID:       {resources['network_id']}")
    print(f"Template UUID:    {resources['template_uuid']}")
    
    valid, message = verify_vm_location_resources(resources)
    if valid:
        print(f"\n✅ {message}")
    else:
        print(f"\n❌ {message}")
