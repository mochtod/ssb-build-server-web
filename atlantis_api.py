#!/usr/bin/env python3
"""
Atlantis API integration with robust error handling and retry logic.

This module provides functions to interact with the Atlantis API for
Terraform plan and apply operations, with built-in error handling,
retry logic, and health checks.
"""
import os
import json
import time
import logging
import requests
import subprocess
from functools import wraps
from requests.exceptions import RequestException, Timeout, ConnectionError

# Import the payload generation from fix_atlantis_apply.py
from fix_atlantis_apply import generate_atlantis_payload, generate_atlantis_apply_payload_fixed

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AtlantisApiError(Exception):
    """Base exception for Atlantis API errors."""
    pass

class AtlantisConnectionError(AtlantisApiError):
    """Exception raised when connection to Atlantis fails."""
    pass

class AtlantisTimeoutError(AtlantisApiError):
    """Exception raised when Atlantis request times out."""
    pass

class AtlantisResponseError(AtlantisApiError):
    """Exception raised when Atlantis returns an error response."""
    def __init__(self, status_code, response_text):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(f"Atlantis API returned status code {status_code}: {response_text}")

def retry(max_retries=3, delay=2, backoff=2, exceptions=(RequestException,)):
    """
    Retry decorator with exponential backoff.
    
    Args:
        max_retries (int): Maximum number of retries
        delay (int): Initial delay in seconds
        backoff (int): Backoff multiplier (e.g. 2 means delay doubles each retry)
        exceptions (tuple): Exceptions to catch and retry
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            mtries, mdelay = max_retries, delay
            while mtries > 0:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    logger.warning(f"Atlantis API request failed, retrying in {mdelay}s: {str(e)}")
                    
                    # If this was the last attempt, reraise
                    mtries -= 1
                    if mtries == 0:
                        raise
                    
                    # Wait for mdelay seconds
                    time.sleep(mdelay)
                    
                    # Increase delay for next retry
                    mdelay *= backoff
            return func(*args, **kwargs)
        return wrapper
    return decorator

def get_atlantis_url():
    """
    Dynamically determine the Atlantis URL based on environment.
    
    Returns:
        str: The Atlantis URL
    """
    # Check if we're running in a container
    if os.path.exists('/.dockerenv'):
        # In container, use service name
        atlantis_host = os.environ.get('ATLANTIS_HOST', 'atlantis')
        atlantis_port = os.environ.get('ATLANTIS_PORT', '4141')
        return f"http://{atlantis_host}:{atlantis_port}"
    else:
        # Not in container, use environment variable or default
        return os.environ.get('ATLANTIS_URL', 'http://localhost:4141')

def check_atlantis_health(verify_ssl=None):
    """
    Check if Atlantis is healthy.
    
    Args:
        verify_ssl (bool, optional): Whether to verify SSL certificates
                                    Defaults to None, which uses environment settings
    
    Returns:
        bool: True if Atlantis is healthy, False otherwise
    """
    # Use the more comprehensive test_atlantis_connection function
    result = test_atlantis_connection(timeout=5, verify_ssl=verify_ssl)
    
    # Return just the success status
    return result.get('success', False)

def test_atlantis_connection(url=None, token=None, timeout=10, verify_ssl=None):
    """
    Test connection to Atlantis server with full diagnostics
    
    Args:
        url (str, optional): Atlantis server URL, uses env var if None
        token (str, optional): Atlantis API token, uses env var if None
        timeout (int): Connection timeout in seconds
        verify_ssl (bool, optional): Whether to verify SSL certificates, 
                                    defaults to env var ATLANTIS_VERIFY_SSL if set,
                                    otherwise False for https URLs
        
    Returns:
        dict: Connection test result containing success status and message
    """
    # Get URL and token from env vars if not provided
    url = url or get_atlantis_url()
    token = token or os.environ.get('ATLANTIS_TOKEN', '')
    
    if not url:
        return {
            'success': False,
            'message': 'Atlantis URL is not configured'
        }
    
    # Determine if we should verify SSL certificates
    if verify_ssl is None:
        verify_ssl_str = os.environ.get('ATLANTIS_VERIFY_SSL', '').lower()
        if verify_ssl_str in ('true', 'yes', '1'):
            verify_ssl = True
        elif verify_ssl_str in ('false', 'no', '0'):
            verify_ssl = False
        else:
            # Default: Don't verify for https URLs (likely self-signed certs in internal environments)
            verify_ssl = not url.startswith('https://')
    
    logger.info(f"Testing Atlantis connection to {url} (verify_ssl={verify_ssl})")
    
    try:
        # Prepare headers
        headers = {}
        if token:
            headers['X-Atlantis-Token'] = token
        
        # Make health check request with SSL verification option
        response = requests.get(f"{url}/healthz", headers=headers, timeout=timeout, verify=verify_ssl)
        
        if response.status_code == 200:
            return {
                'success': True,
                'message': 'Atlantis connection successful',
                'details': {
                    'url': url,
                    'status_code': response.status_code,
                    'verify_ssl': verify_ssl
                }
            }
        else:
            return {
                'success': False,
                'message': f'Atlantis health check failed: HTTP {response.status_code}',
                'details': {
                    'url': url,
                    'status_code': response.status_code,
                    'verify_ssl': verify_ssl
                }
            }
    except requests.exceptions.SSLError as e:
        logger.warning(f"SSL certificate verification failed: {str(e)}")
        # If we were verifying SSL and it failed, suggest trying with verification disabled
        if verify_ssl:
            return {
                'success': False,
                'message': f'SSL certificate verification failed. Try setting ATLANTIS_VERIFY_SSL=false',
                'details': {
                    'error_type': 'ssl_error',
                    'verify_ssl': verify_ssl,
                    'error': str(e)
                }
            }
        else:
            return {
                'success': False,
                'message': f'SSL certificate verification failed even with verification disabled',
                'details': {
                    'error_type': 'ssl_error',
                    'verify_ssl': verify_ssl,
                    'error': str(e)
                }
            }
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Connection error to Atlantis server: {str(e)}")
        return {
            'success': False,
            'message': f'Could not connect to Atlantis server: {url}',
            'details': {
                'error_type': 'connection_error',
                'verify_ssl': verify_ssl,
                'error': str(e)
            }
        }
    except requests.exceptions.Timeout as e:
        logger.warning(f"Timeout connecting to Atlantis server: {str(e)}")
        return {
            'success': False,
            'message': f'Connection to Atlantis server timed out after {timeout}s',
            'details': {
                'error_type': 'timeout',
                'verify_ssl': verify_ssl,
                'error': str(e)
            }
        }
    except Exception as e:
        logger.error(f"Error in Atlantis connection test: {str(e)}")
        return {
            'success': False,
            'message': f'Error connecting to Atlantis: {str(e)}',
            'details': {
                'error_type': 'other',
                'verify_ssl': verify_ssl,
                'error': str(e)
            }
        }

def get_atlantis_headers():
    """
    Get the HTTP headers for Atlantis API requests.
    
    Returns:
        dict: HTTP headers
    """
    headers = {
        'Content-Type': 'application/json'
    }
    
    atlantis_token = os.environ.get('ATLANTIS_TOKEN', '')
    if atlantis_token:
        headers['X-Atlantis-Token'] = atlantis_token
    
    return headers

def parse_terraform_plan_error(error_log):
    """
    Parse Terraform plan error logs to extract useful information.
    
    Args:
        error_log (str): The terraform plan error log
        
    Returns:
        dict: Parsed error details with missing resources
    """
    parsed_error = {
        'missing_resources': [],
        'error_type': 'unknown',
        'summary': 'Unknown Terraform error'
    }
    
    # Common error patterns
    # Pattern 1: Missing required provider parameters
    if "Missing required provider parameters" in error_log:
        parsed_error['error_type'] = 'missing_provider_params'
        
        # Extract missing parameters
        missing_params = []
        
        # Look for lines like: "The provider vsphere requires the following input values:"
        import re
        provider_match = re.search(r"The provider (\w+) requires the following input values:", error_log)
        if provider_match:
            provider = provider_match.group(1)
            parsed_error['provider'] = provider
            
            # Find required parameters
            param_pattern = re.compile(r"- (\w+) \(required\)")
            param_matches = param_pattern.findall(error_log)
            if param_matches:
                missing_params = param_matches
                parsed_error['missing_resources'] = missing_params
                
                # Create a readable summary
                parsed_error['summary'] = f"Missing required {provider} provider parameters: {', '.join(missing_params)}"
    
    # Pattern 2: Invalid reference to non-existent resource
    elif "Invalid reference to non-existent resource" in error_log or "No such resource exists" in error_log:
        parsed_error['error_type'] = 'missing_resource_reference'
        
        # Try to extract the resource name
        resource_match = re.search(r"resource \"([^\"]+)\"", error_log)
        if resource_match:
            resource_name = resource_match.group(1)
            parsed_error['missing_resources'].append(resource_name)
            parsed_error['summary'] = f"Reference to non-existent resource: {resource_name}"
    
    # Pattern 3: Missing required field
    elif "Missing required argument" in error_log:
        parsed_error['error_type'] = 'missing_required_field'
        
        # Extract the field name
        field_match = re.search(r"Missing required argument: The argument \"([^\"]+)\" is required", error_log)
        if field_match:
            field_name = field_match.group(1)
            parsed_error['missing_resources'].append(field_name)
            parsed_error['summary'] = f"Missing required field: {field_name}"
    
    # Pattern 4: Authentication errors
    elif "InvalidLogin" in error_log or "authentication failed" in error_log:
        parsed_error['error_type'] = 'authentication_error'
        parsed_error['summary'] = "Authentication failed - check your credentials"
    
    # If we couldn't match a specific pattern, provide a generic summary
    if parsed_error['error_type'] == 'unknown':
        # Try to find the most relevant error message line
        error_lines = error_log.split('\n')
        for line in error_lines:
            if 'Error:' in line:
                # Clean up the line
                cleaned_line = line.replace('Error:', '').strip()
                if len(cleaned_line) > 10:  # Make sure it's not just a short fragment
                    parsed_error['summary'] = cleaned_line
                    break
    
    return parsed_error

@retry(max_retries=3, delay=2, backoff=2, 
       exceptions=(ConnectionError, Timeout, AtlantisConnectionError, AtlantisTimeoutError))
def run_atlantis_plan(config_data, tf_directory):
    """
    Run Terraform plan via Atlantis API with retry logic.
    
    Args:
        config_data (dict): VM configuration data
        tf_directory (str): Directory containing Terraform files
        
    Returns:
        dict: Result of the plan operation
        
    Raises:
        AtlantisApiError: If the Atlantis API request fails
    """
    try:
        # Check Atlantis health before making the request
        if not check_atlantis_health():
            raise AtlantisConnectionError("Atlantis is not healthy")
        
        # Get plan metadata
        server_name = config_data.get('server_name', 'unknown')
        request_id = config_data.get('request_id', 'unknown')
        
        # Get all terraform files in the directory
        tf_files = [f for f in os.listdir(tf_directory) if f.endswith('.tf') or f.endswith('.tfvars')]
        
        # Generate the payload for Atlantis API
        payload = generate_atlantis_payload(
            repo="build-server-repo",
            workspace="default",
            dir=tf_directory,
            commit_hash=f"request-{request_id}",
            comment="plan",
            user=config_data.get('build_username', 'system'),
            files=tf_files
        )
        
        # Call Atlantis API
        atlantis_url = get_atlantis_url()
        if not atlantis_url:
            raise AtlantisConnectionError("Atlantis URL is not configured")
        
        # Get request timeout
        timeout = int(os.environ.get('TIMEOUT', 120))
        
        # Determine if we should verify SSL certificates
        verify_ssl_str = os.environ.get('ATLANTIS_VERIFY_SSL', '').lower()
        if verify_ssl_str in ('true', 'yes', '1'):
            verify_ssl = True
        elif verify_ssl_str in ('false', 'no', '0'):
            verify_ssl = False
        else:
            # Default: Don't verify for https URLs (likely self-signed certs in internal environments)
            verify_ssl = not atlantis_url.startswith('https://')
        
        # Make the request to Atlantis
        response = requests.post(
            f"{atlantis_url}/api/plan",
            json=payload,
            headers=get_atlantis_headers(),
            timeout=timeout,
            verify=verify_ssl
        )
        
        # Check response
        if response.status_code == 200:
            response_data = response.json()
            plan_id = response_data.get('id', '')
            plan_log = response_data.get('log', '')
            
            # Check if plan has errors (Atlantis returns 200 but plan can still fail)
            if "Plan failed" in plan_log or "Error:" in plan_log:
                logger.warning("Terraform plan completed with errors")
                
                # Parse the error to provide more useful information
                error_details = parse_terraform_plan_error(plan_log)
                
                return {
                    'status': 'error',
                    'plan_id': plan_id,
                    'atlantis_url': f"{atlantis_url}/plan/{plan_id}",
                    'plan_log': plan_log,
                    'error_summary': error_details['summary'],
                    'error_details': error_details
                }
            
            logger.info(f"Atlantis plan successful: plan_id={plan_id}")
            
            return {
                'status': 'success',
                'plan_id': plan_id,
                'atlantis_url': f"{atlantis_url}/plan/{plan_id}",
                'plan_log': plan_log
            }
        else:
            logger.error(f"Atlantis plan failed: HTTP {response.status_code}")
            
            # Try to parse the error response
            error_text = response.text
            error_details = parse_terraform_plan_error(error_text)
            
            # Raise a more informative error
            raise AtlantisResponseError(
                response.status_code, 
                f"Plan failed: {error_details['summary']}"
            )
    
    except Timeout:
        logger.error(f"Timeout waiting for Atlantis plan: threshold={os.environ.get('TIMEOUT', 120)}s")
        raise AtlantisTimeoutError(f"Timeout waiting for Atlantis plan response after {os.environ.get('TIMEOUT', 120)} seconds")
        
    except ConnectionError as e:
        logger.error(f"Connection error to Atlantis: {str(e)}")
        raise AtlantisConnectionError(f"Failed to connect to Atlantis: {str(e)}")
        
    except Exception as e:
        logger.exception(f"Error running Atlantis plan: {str(e)}")
        raise AtlantisApiError(f"Error running Atlantis plan: {str(e)}")

@retry(max_retries=3, delay=2, backoff=2, 
       exceptions=(ConnectionError, Timeout, AtlantisConnectionError, AtlantisTimeoutError))
def run_atlantis_apply(config_data, tf_directory):
    """
    Apply Terraform plan via Atlantis API with retry logic.
    
    Args:
        config_data (dict): VM configuration data
        tf_directory (str): Directory containing Terraform files
        
    Returns:
        dict: Result of the apply operation
        
    Raises:
        AtlantisApiError: If the Atlantis API request fails
    """
    try:
        # Check Atlantis health before making the request
        if not check_atlantis_health():
            raise AtlantisConnectionError("Atlantis is not healthy")
        
        # Get the plan ID from the config
        plan_id = config_data.get('plan_id')
        if not plan_id:
            raise AtlantisApiError("No plan ID found in configuration")
        
        # Get all terraform files in the directory
        tf_files = [f for f in os.listdir(tf_directory) if f.endswith('.tf') or f.endswith('.tfvars')]
        
        # Generate the payload for apply
        payload = json.loads(generate_atlantis_apply_payload_fixed(config_data, tf_directory, tf_files, plan_id))
        
        # Call Atlantis API
        atlantis_url = get_atlantis_url()
        if not atlantis_url:
            raise AtlantisConnectionError("Atlantis URL is not configured")
        
        # Get request timeout - apply typically takes longer than plan
        timeout = int(os.environ.get('TIMEOUT', 300))
        
        # Determine if we should verify SSL certificates
        verify_ssl_str = os.environ.get('ATLANTIS_VERIFY_SSL', '').lower()
        if verify_ssl_str in ('true', 'yes', '1'):
            verify_ssl = True
        elif verify_ssl_str in ('false', 'no', '0'):
            verify_ssl = False
        else:
            # Default: Don't verify for https URLs (likely self-signed certs in internal environments)
            verify_ssl = not atlantis_url.startswith('https://')
        
        # Make the request to Atlantis
        response = requests.post(
            f"{atlantis_url}/api/apply",
            json=payload,
            headers=get_atlantis_headers(),
            timeout=timeout,
            verify=verify_ssl
        )
        
        # Check response
        if response.status_code == 200:
            response_data = response.json()
            apply_id = response_data.get('id', '')
            
            logger.info(f"Atlantis apply successful: apply_id={apply_id}")
            
            return {
                'status': 'success',
                'apply_id': apply_id,
                'build_log': response_data.get('log', '')
            }
        else:
            logger.error(f"Atlantis apply failed: HTTP {response.status_code}")
            raise AtlantisResponseError(response.status_code, response.text)
    
    except Timeout:
        logger.error(f"Timeout waiting for Atlantis apply: threshold={os.environ.get('TIMEOUT', 300)}s")
        raise AtlantisTimeoutError(f"Timeout waiting for Atlantis apply response after {os.environ.get('TIMEOUT', 300)} seconds")
        
    except ConnectionError as e:
        logger.error(f"Connection error to Atlantis: {str(e)}")
        raise AtlantisConnectionError(f"Failed to connect to Atlantis: {str(e)}")
        
    except Exception as e:
        logger.exception(f"Error applying Terraform plan: {str(e)}")
        raise AtlantisApiError(f"Error applying Terraform plan: {str(e)}")

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
