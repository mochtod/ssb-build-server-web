#!/usr/bin/env python3
"""
NetBox API integration for the SSB Build Server application.
These functions provide connectivity and API operations for NetBox.
"""
import os
import requests
import logging
import json
from functools import wraps

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NetBoxConnectionError(Exception):
    """Exception raised when connection to NetBox fails."""
    pass

class NetBoxApiError(Exception):
    """Base exception for NetBox API errors."""
    pass

class NetBoxAuthError(NetBoxApiError):
    """Exception raised when authentication to NetBox fails."""
    pass

def retry(max_retries=3, delay=2, backoff=2, exceptions=(Exception,)):
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
            import time
            mtries, mdelay = max_retries, delay
            while mtries > 0:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    logger.warning(f"NetBox API request failed, retrying in {mdelay}s: {str(e)}")
                    
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

def get_netbox_url():
    """
    Get the NetBox URL from environment or default.
    
    Returns:
        str: NetBox API URL
    """
    url = os.environ.get('NETBOX_URL', '')
    
    # Normalize URL to remove trailing slash if present
    if url and url.endswith('/'):
        url = url[:-1]
    
    # Ensure URL points to API endpoint
    if url and not url.endswith('/api'):
        api_url = f"{url}/api"
    else:
        api_url = url
        
    return api_url

def get_netbox_headers():
    """
    Get the HTTP headers for NetBox API requests.
    
    Returns:
        dict: HTTP headers
    """
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    token = os.environ.get('NETBOX_TOKEN', '')
    if token:
        headers['Authorization'] = f'Token {token}'
    
    return headers

def test_netbox_connection(url=None, token=None, timeout=10, verify_ssl=None):
    """
    Test connection to NetBox API
    
    Args:
        url (str, optional): NetBox API URL, uses env var if None
        token (str, optional): NetBox API token, uses env var if None
        timeout (int): Connection timeout in seconds
        verify_ssl (bool, optional): Whether to verify SSL certificates,
                                     defaults to env var NETBOX_VERIFY_SSL if set,
                                     otherwise False for https URLs
        
    Returns:
        dict: Connection test result containing:
            - success (bool): True if connection successful, False otherwise
            - message (str): Description of the result or error message
            - details (dict): Additional details about the connection (when successful)
    """
    # Get URL and token from env vars if not provided
    url = url or get_netbox_url()
    token = token or os.environ.get('NETBOX_TOKEN', '')
    
    if not url:
        return {
            'success': False,
            'message': 'NetBox URL is not configured',
            'details': {}
        }
    
    # Determine if we should verify SSL certificates
    if verify_ssl is None:
        verify_ssl_str = os.environ.get('NETBOX_VERIFY_SSL', '').lower()
        if verify_ssl_str in ('true', 'yes', '1'):
            verify_ssl = True
        elif verify_ssl_str in ('false', 'no', '0'):
            verify_ssl = False
        else:
            # Default: Don't verify for https URLs (likely self-signed certs in internal environments)
            verify_ssl = not url.startswith('https://')
    
    logger.info(f"Testing NetBox connection to {url} (verify_ssl={verify_ssl})")
    
    try:
        # Prepare headers
        headers = {
            'Accept': 'application/json'
        }
        
        if token:
            headers['Authorization'] = f'Token {token}'
        
        # Make status request with SSL verification option
        response = requests.get(f"{url}/status/", headers=headers, timeout=timeout, verify=verify_ssl)
        
        if response.status_code == 200:
            # Try to parse response data
            try:
                data = response.json()
                version = data.get('netbox-version', 'unknown')
                return {
                    'success': True,
                    'message': f'NetBox connection successful (version {version})',
                    'details': {
                        'url': url,
                        'version': version,
                        'django_version': data.get('django-version', 'unknown'),
                        'python_version': data.get('python-version', 'unknown')
                    }
                }
            except ValueError:
                # Return success even if JSON parsing fails
                return {
                    'success': True,
                    'message': 'NetBox connection successful (non-JSON response)',
                    'details': {
                        'url': url
                    }
                }
        elif response.status_code == 401 or response.status_code == 403:
            return {
                'success': False,
                'message': 'NetBox authentication failed. Please check your API token.',
                'details': {
                    'url': url,
                    'status_code': response.status_code
                }
            }
        else:
            return {
                'success': False,
                'message': f'NetBox API returned status code {response.status_code}',
                'details': {
                    'url': url,
                    'status_code': response.status_code
                }
            }
    except requests.exceptions.ConnectionError:
        return {
            'success': False,
            'message': f'Could not connect to NetBox API: {url}',
            'details': {}
        }
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'message': f'Connection to NetBox API timed out after {timeout}s',
            'details': {}
        }
    except Exception as e:
        logger.exception(f"Error connecting to NetBox API: {str(e)}")
        return {
            'success': False,
            'message': f'Error connecting to NetBox API: {str(e)}',
            'details': {}
        }

@retry(max_retries=3, delay=2)
def get_next_available_ip(prefix, exclude_ips=None, verify_ssl=None):
    """
    Get the next available IP address from a NetBox prefix.
    
    Args:
        prefix (str): CIDR notation of the prefix (e.g. "10.0.0.0/24")
        exclude_ips (list, optional): List of IPs to exclude from consideration
        verify_ssl (bool, optional): Whether to verify SSL certificates
        
    Returns:
        dict: Result containing:
            - success (bool): True if successful, False otherwise
            - message (str): Status message
            - ip (str, optional): The next available IP address (when successful)
    """
    url = get_netbox_url()
    
    if not url:
        return {
            'success': False,
            'message': 'NetBox URL is not configured'
        }
    
    # Determine if we should verify SSL certificates
    if verify_ssl is None:
        verify_ssl_str = os.environ.get('NETBOX_VERIFY_SSL', '').lower()
        if verify_ssl_str in ('true', 'yes', '1'):
            verify_ssl = True
        elif verify_ssl_str in ('false', 'no', '0'):
            verify_ssl = False
        else:
            # Default: Don't verify for https URLs (likely self-signed certs in internal environments)
            verify_ssl = not url.startswith('https://')
    
    try:
        # Get available IPs from NetBox
        response = requests.get(
            f"{url}/ipam/prefixes/?prefix={prefix}&limit=1",
            headers=get_netbox_headers(),
            timeout=10,
            verify=verify_ssl
        )
        
        if response.status_code != 200:
            return {
                'success': False,
                'message': f'Failed to get prefix from NetBox: HTTP {response.status_code}'
            }
        
        data = response.json()
        
        if not data.get('results'):
            return {
                'success': False,
                'message': f'Prefix {prefix} not found in NetBox'
            }
        
        # Get prefix ID
        prefix_id = data['results'][0]['id']
        
        # Get available IP address
        response = requests.post(
            f"{url}/ipam/prefixes/{prefix_id}/available-ips/",
            headers=get_netbox_headers(),
            json={'limit': 1},
            timeout=10,
            verify=verify_ssl
        )
        
        if response.status_code != 201:
            return {
                'success': False,
                'message': f'Failed to get available IP: HTTP {response.status_code}'
            }
        
        data = response.json()
        
        if not data:
            return {
                'success': False,
                'message': f'No available IPs in prefix {prefix}'
            }
        
        # Extract IP address (remove CIDR notation)
        ip_address = data[0]['address'].split('/')[0]
        
        # Check if IP is in exclude list
        if exclude_ips and ip_address in exclude_ips:
            # Delete this IP and try again
            ip_id = data[0]['id']
            delete_response = requests.delete(
                f"{url}/ipam/ip-addresses/{ip_id}/",
                headers=get_netbox_headers(),
                timeout=10,
                verify=verify_ssl
            )
            
            if delete_response.status_code not in [204, 200]:
                logger.warning(f"Failed to delete excluded IP: HTTP {delete_response.status_code}")
            
            # Recursively get another IP
            return get_next_available_ip(prefix, exclude_ips)
        
        return {
            'success': True,
            'message': f'Successfully allocated IP from {prefix}',
            'ip': ip_address
        }
        
    except Exception as e:
        logger.exception(f"Error getting available IP from NetBox: {str(e)}")
        return {
            'success': False,
            'message': f'Error getting available IP: {str(e)}'
        }

def create_ip_reservation(ip_address, description, status="reserved", verify_ssl=None):
    """
    Create an IP address reservation in NetBox.
    
    Args:
        ip_address (str): IP address to reserve
        description (str): Description for the reservation
        status (str): Status for the IP (active, reserved, deprecated, etc.)
        verify_ssl (bool, optional): Whether to verify SSL certificates
        
    Returns:
        dict: Result containing success status and message
    """
    url = get_netbox_url()
    
    if not url:
        return {
            'success': False,
            'message': 'NetBox URL is not configured'
        }
    
    # Determine if we should verify SSL certificates
    if verify_ssl is None:
        verify_ssl_str = os.environ.get('NETBOX_VERIFY_SSL', '').lower()
        if verify_ssl_str in ('true', 'yes', '1'):
            verify_ssl = True
        elif verify_ssl_str in ('false', 'no', '0'):
            verify_ssl = False
        else:
            # Default: Don't verify for https URLs (likely self-signed certs in internal environments)
            verify_ssl = not url.startswith('https://')
    
    try:
        # Prepare payload
        payload = {
            'address': ip_address,
            'status': status,
            'description': description
        }
        
        # Create IP reservation
        response = requests.post(
            f"{url}/ipam/ip-addresses/",
            headers=get_netbox_headers(),
            json=payload,
            timeout=10,
            verify=verify_ssl
        )
        
        if response.status_code in [201, 200]:
            data = response.json()
            return {
                'success': True,
                'message': f'Successfully reserved IP {ip_address} in NetBox',
                'details': {
                    'id': data.get('id'),
                    'address': data.get('address')
                }
            }
        else:
            return {
                'success': False,
                'message': f'Failed to reserve IP in NetBox: HTTP {response.status_code}'
            }
    
    except Exception as e:
        logger.exception(f"Error reserving IP in NetBox: {str(e)}")
        return {
            'success': False,
            'message': f'Error reserving IP: {str(e)}'
        }
