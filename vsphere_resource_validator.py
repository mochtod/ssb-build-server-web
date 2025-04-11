#!/usr/bin/env python3
"""
VSphere Resource Validator

This module provides functions to validate vSphere resources
before they are used to generate Terraform configurations.
"""
import logging
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VSphereResourceValidationError(Exception):
    """Exception raised when vSphere resource validation fails."""
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}

def verify_vsphere_resources(vs_resources, config_data):
    """
    Verify that the vSphere resources exist in the resources list.
    
    Args:
        vs_resources (dict): Dictionary containing vSphere resources
        config_data (dict): VM configuration data
        
    Returns:
        tuple: (bool, dict) - Success flag and error messages
    """
    errors = {}
    if 'vsphere_resources' not in config_data:
        return False, {'general': 'No vSphere resources specified in configuration'}
    
    # Extract resource IDs from config
    resource_pool_id = config_data['vsphere_resources'].get('resource_pool_id', '')
    datastore_id = config_data['vsphere_resources'].get('datastore_id', '')
    network_id = config_data['vsphere_resources'].get('network_id', '')
    template_uuid = config_data['vsphere_resources'].get('template_uuid', '')
    
    # Verify resource pool exists
    if resource_pool_id:
        resource_pool_exists = any(rp['id'] == resource_pool_id for rp in vs_resources.get('resource_pools', []))
        if not resource_pool_exists:
            errors['resource_pool'] = f'Resource pool with ID {resource_pool_id} not found'
    else:
        errors['resource_pool'] = 'No resource pool ID specified'
    
    # Verify datastore exists
    if datastore_id:
        datastore_exists = any(ds['id'] == datastore_id for ds in vs_resources.get('datastores', []))
        if not datastore_exists:
            errors['datastore'] = f'Datastore with ID {datastore_id} not found'
    else:
        errors['datastore'] = 'No datastore ID specified'
    
    # Verify network exists
    if network_id:
        network_exists = any(net['id'] == network_id for net in vs_resources.get('networks', []))
        if not network_exists:
            errors['network'] = f'Network with ID {network_id} not found'
    else:
        errors['network'] = 'No network ID specified'
    
    # Verify template exists
    if template_uuid:
        template_exists = any(tpl['id'] == template_uuid for tpl in vs_resources.get('templates', []))
        if not template_exists:
            errors['template'] = f'Template with UUID {template_uuid} not found'
    else:
        errors['template'] = 'No template UUID specified'
    
    # Return validation result
    return len(errors) == 0, errors

def validate_default_pool(vs_resources, resource_pool_id):
    """
    Validate if the resource pool is the default pool.
    
    Args:
        vs_resources (dict): Dictionary containing vSphere resources
        resource_pool_id (str): Resource pool ID to validate
        
    Returns:
        tuple: (bool, str) - Is default pool flag and warning message if not
    """
    # Find resource pool in resources
    resource_pool = None
    for rp in vs_resources.get('resource_pools', []):
        if rp['id'] == resource_pool_id:
            resource_pool = rp
            break
    
    if not resource_pool:
        return False, f'Resource pool with ID {resource_pool_id} not found'
    
    # Check if this is the default pool (typically named "Resources")
    if resource_pool.get('name', '').lower() == 'resources':
        return True, ''
    
    # Not the default pool, warn the user
    return False, f'Warning: Selected resource pool "{resource_pool.get("name", "Unknown")}" is not the default pool'

def check_resource_availability(vs_resources, config_data):
    """
    Check if there are enough resources available for the requested VM.
    
    Args:
        vs_resources (dict): Dictionary containing vSphere resources
        config_data (dict): VM configuration data
        
    Returns:
        tuple: (bool, dict) - Success flag and warnings
    """
    warnings = {}
    
    # Get resource IDs from config
    if 'vsphere_resources' not in config_data:
        return False, {'general': 'No vSphere resources specified in configuration'}
    
    resource_pool_id = config_data['vsphere_resources'].get('resource_pool_id', '')
    datastore_id = config_data['vsphere_resources'].get('datastore_id', '')
    
    # Find resource pool
    resource_pool = None
    for rp in vs_resources.get('resource_pools', []):
        if rp['id'] == resource_pool_id:
            resource_pool = rp
            break
    
    # Find datastore
    datastore = None
    for ds in vs_resources.get('datastores', []):
        if ds['id'] == datastore_id:
            datastore = ds
            break
    
    # Check CPU and memory availability in resource pool
    if resource_pool and 'cpu_limit' in resource_pool and 'cpu_usage' in resource_pool:
        cpu_available = resource_pool['cpu_limit'] - resource_pool['cpu_usage']
        cpu_requested = config_data.get('num_cpus', 0)
        
        if cpu_requested > cpu_available:
            warnings['cpu'] = f'Requested {cpu_requested} CPUs but only {cpu_available} available in resource pool'
    
    if resource_pool and 'memory_limit' in resource_pool and 'memory_usage' in resource_pool:
        mem_available = (resource_pool['memory_limit'] - resource_pool['memory_usage']) / 1024  # Convert to MB
        mem_requested = config_data.get('memory', 0)
        
        if mem_requested > mem_available:
            warnings['memory'] = f'Requested {mem_requested} MB memory but only {mem_available} MB available in resource pool'
    
    # Check disk space availability in datastore
    if datastore and 'capacity' in datastore and 'free_space' in datastore:
        disk_available = datastore['free_space'] / (1024 * 1024 * 1024)  # Convert to GB
        disk_requested = config_data.get('disk_size', 0)
        
        # Add additional disks
        for disk in config_data.get('additional_disks', []):
            disk_requested += disk.get('size', 0)
        
        if disk_requested > disk_available:
            warnings['disk'] = f'Requested {disk_requested} GB disk space but only {disk_available} GB available in datastore'
    
    return len(warnings) == 0, warnings

def with_resource_validation(f):
    """
    Decorator to validate vSphere resources before executing a function.
    
    Usage:
        @with_resource_validation
        def generate_terraform_config(config_data):
            # Function implementation
    """
    @wraps(f)
    def wrapper(config_data, vs_resources=None, *args, **kwargs):
        # Skip validation if vs_resources is None
        if vs_resources is None:
            logger.warning("Skipping vSphere resource validation because vs_resources is None")
            return f(config_data, *args, **kwargs)
        
        # Validate resources
        valid, errors = verify_vsphere_resources(vs_resources, config_data)
        if not valid:
            error_msg = "; ".join(f"{k}: {v}" for k, v in errors.items())
            raise VSphereResourceValidationError(f"Resource validation failed: {error_msg}", errors)
        
        # Call the original function
        return f(config_data, *args, **kwargs)
    
    return wrapper
