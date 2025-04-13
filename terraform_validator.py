#!/usr/bin/env python3
"""
Terraform Configuration Validator

This module provides functions to validate Terraform configuration
files before submission to Atlantis for execution.
"""
import os
import json
import subprocess
import logging
import re
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TerraformValidationError(Exception):
    """Exception raised when Terraform validation fails."""
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}

def validate_terraform_files(tf_directory):
    """
    Skip local Terraform validation since terraform is only available in the Atlantis container.
    
    Args:
        tf_directory (str): Directory containing Terraform files
        
    Returns:
        bool: Always returns True to skip validation
    """
    logger.info("Skipping local Terraform validation (terraform binary is in Atlantis container)")
    return True

def check_required_provider_config(tf_directory):
    """
    Check if the required Terraform provider configuration is present.
    
    Args:
        tf_directory (str): Directory containing Terraform files
        
    Returns:
        tuple: (bool, list) - Success flag and missing elements
    """
    required_elements = [
        'terraform .*{',                              # terraform block
        'required_providers .*{',                     # required_providers block
        'vsphere .*{',                                # vsphere provider
        'source.*"hashicorp/vsphere"',                # source for vsphere
        'version',                                    # version constraint
        'required_version',                           # terraform version constraint
        'provider "vsphere"',                         # vsphere provider block
        'user',                                       # user variable
        'password',                                   # password variable
        'vsphere_server',                             # server variable
        'allow_unverified_ssl'                        # SSL verification setting
    ]
    
    missing_elements = required_elements.copy()
    provider_file_found = False
    
    # Check for providers.tf first
    provider_file_path = os.path.join(tf_directory, 'providers.tf')
    if os.path.exists(provider_file_path):
        provider_file_found = True
        with open(provider_file_path, 'r') as f:
            content = f.read()
            
            # Check each required element
            for element in required_elements[:]:
                if re.search(element, content):
                    missing_elements.remove(element)
    
    # If providers.tf doesn't exist or some elements are missing, check all .tf files
    if not provider_file_found or missing_elements:
        for filename in os.listdir(tf_directory):
            if filename.endswith('.tf'):
                file_path = os.path.join(tf_directory, filename)
                with open(file_path, 'r') as f:
                    content = f.read()
                    
                    # Check remaining missing elements
                    for element in missing_elements[:]:
                        if re.search(element, content):
                            missing_elements.remove(element)
    
    if missing_elements:
        logger.warning(f"Missing required provider configuration elements: {', '.join(missing_elements)}")
        return False, missing_elements
    
    return True, []

def check_required_fields(tf_directory):
    """
    Check if all required fields are present in the Terraform files.
    
    Args:
        tf_directory (str): Directory containing Terraform files
        
    Returns:
        tuple: (bool, list) - Success flag and missing fields
    """
    required_fields = [
        'resource_pool_id',
        'datastore_id',
        'network_id',
        'template_uuid',
        'name'  # Changed from 'vm_name' to 'name' to match actual configuration
    ]
    
    missing_fields = []
    
    # Read all .tf files
    for filename in os.listdir(tf_directory):
        if filename.endswith('.tf'):
            file_path = os.path.join(tf_directory, filename)
            with open(file_path, 'r') as f:
                content = f.read()
                
                # Check for each required field
                for field in required_fields[:]:  # Create a copy for iteration
                    if re.search(rf'{field}\s*=', content):
                        required_fields.remove(field)
    
    missing_fields = required_fields
    
    if missing_fields:
        logger.warning(f"Terraform files missing required fields: {', '.join(missing_fields)}")
        return False, missing_fields
    
    return True, []

def validate_template_compatibility(template_id, num_cpus, memory_mb, disk_size_gb, vs_resources):
    """
    Validate that the selected template is compatible with the requested specifications.
    
    Args:
        template_id (str): Template UUID
        num_cpus (int): Number of CPUs
        memory_mb (int): Memory in MB
        disk_size_gb (int): Disk size in GB
        vs_resources (dict): Dictionary of vSphere resources
        
    Returns:
        tuple: (bool, str) - Success flag and warning message if not
    """
    # Find template in resources
    template = None
    for tpl in vs_resources.get('templates', []):
        if tpl['id'] == template_id:
            template = tpl
            break
    
    if not template:
        return False, f"Template with ID {template_id} not found"
    
    warnings = []
    
    # Check CPU compatibility
    if 'num_cpus' in template:
        template_cpus = template.get('num_cpus', 0)
        if num_cpus < template_cpus:
            warnings.append(f"Requested CPUs ({num_cpus}) is less than template CPUs ({template_cpus})")
    
    # Check memory compatibility
    if 'memory_mb' in template:
        template_memory = template.get('memory_mb', 0)
        if memory_mb < template_memory:
            warnings.append(f"Requested memory ({memory_mb} MB) is less than template memory ({template_memory} MB)")
    
    # Check disk compatibility
    if 'disk_size_gb' in template:
        template_disk = template.get('disk_size_gb', 0)
        if disk_size_gb < template_disk:
            warnings.append(f"Requested disk size ({disk_size_gb} GB) is less than template disk size ({template_disk} GB)")
    
    if warnings:
        return False, "; ".join(warnings)
    
    return True, ""

def with_terraform_validation(f):
    """
    Decorator to validate Terraform files before executing a function.
    
    Usage:
        @with_terraform_validation
        def run_terraform_plan(tf_directory):
            # Function implementation
    """
    @wraps(f)
    def wrapper(tf_directory, *args, **kwargs):
        # Validate terraform files
        if not validate_terraform_files(tf_directory):
            raise TerraformValidationError(f"Terraform validation failed for directory: {tf_directory}")
        
        # Check required provider configuration
        valid_provider, missing_provider_elements = check_required_provider_config(tf_directory)
        if not valid_provider:
            raise TerraformValidationError(
                f"Terraform files missing required provider configuration: {', '.join(missing_provider_elements)}",
                {'missing_provider_elements': missing_provider_elements}
            )
        
        # Check required resource fields
        valid_fields, missing_fields = check_required_fields(tf_directory)
        if not valid_fields:
            raise TerraformValidationError(
                f"Terraform files missing required resource fields: {', '.join(missing_fields)}",
                {'missing_fields': missing_fields}
            )
        
        # Call the original function
        return f(tf_directory, *args, **kwargs)
    
    return wrapper
