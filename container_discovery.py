#!/usr/bin/env python3
"""
Container Discovery Module

This module provides functions to dynamically discover and interact with
containerized services in the SSB Build Server application.
"""
import os
import socket
import logging
import requests
import json
import time
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ContainerDiscoveryError(Exception):
    """Exception raised when container discovery fails."""
    pass

def is_running_in_container():
    """
    Check if the application is running inside a container.
    
    Returns:
        bool: True if running in a container, False otherwise
    """
    # Check for .dockerenv file
    docker_env = os.path.exists('/.dockerenv')
    
    # Check for cgroup
    try:
        with open('/proc/1/cgroup', 'r') as f:
            cgroup_content = f.read()
            cgroup = 'docker' in cgroup_content or 'kubepods' in cgroup_content
    except Exception:
        cgroup = False
    
    return docker_env or cgroup

def get_container_network():
    """
    Get the container network name.
    
    Returns:
        str: Container network name, or None if not available
    """
    # Try to get from environment variable
    network = os.environ.get('CONTAINER_NETWORK', 'app-network')
    return network

def get_atlantis_url():
    """
    Dynamically determine the Atlantis URL based on environment.
    
    Returns:
        str: The Atlantis URL
    """
    # Check if we're running in a container
    if is_running_in_container():
        # In container, use service name
        atlantis_host = os.environ.get('ATLANTIS_HOST', 'atlantis')
        atlantis_port = os.environ.get('ATLANTIS_PORT', '4141')
        return f"http://{atlantis_host}:{atlantis_port}"
    else:
        # Not in container, use environment variable or default
        return os.environ.get('ATLANTIS_URL', 'http://localhost:4141')

def get_netbox_url():
    """
    Dynamically determine the NetBox URL based on environment.
    
    Returns:
        str: The NetBox URL
    """
    # Check if we're running in a container
    if is_running_in_container():
        # In container, use service name
        netbox_host = os.environ.get('NETBOX_HOST', 'netbox')
        netbox_port = os.environ.get('NETBOX_PORT', '8000')
        return f"http://{netbox_host}:{netbox_port}"
    else:
        # Not in container, use environment variable or default
        return os.environ.get('NETBOX_URL', '')

def discover_service(service_name, default_port, default_url=None, timeout=2):
    """
    Discover a service using various methods.
    
    Args:
        service_name (str): Name of the service to discover
        default_port (int): Default port for the service
        default_url (str, optional): Default URL to use if discovery fails
        timeout (int): Connection timeout in seconds
        
    Returns:
        str: Service URL
    """
    # Check if we're in a container
    if is_running_in_container():
        # In container, try direct service name
        url = f"http://{service_name}:{default_port}"
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((service_name, default_port))
            sock.close()
            logger.info(f"Discovered {service_name} via container dns at {url}")
            return url
        except Exception as e:
            logger.warning(f"Failed to connect to {service_name} via container dns: {str(e)}")
    
    # Try environment variable
    env_var = f"{service_name.upper()}_URL"
    url = os.environ.get(env_var)
    if url:
        logger.info(f"Using {service_name} URL from environment: {url}")
        return url
    
    # Try localhost
    url = f"http://localhost:{default_port}"
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(('localhost', default_port))
        sock.close()
        logger.info(f"Discovered {service_name} on localhost at {url}")
        return url
    except Exception as e:
        logger.warning(f"Failed to connect to {service_name} on localhost: {str(e)}")
    
    # Use default URL if provided
    if default_url:
        logger.info(f"Using default URL for {service_name}: {default_url}")
        return default_url
    
    # Failed to discover service
    logger.error(f"Failed to discover {service_name} service")
    return None

def retry_with_backoff(max_attempts=3, initial_delay=1, backoff_factor=2):
    """
    Decorator to retry a function with exponential backoff.
    
    Args:
        max_attempts (int): Maximum number of attempts
        initial_delay (int): Initial delay in seconds
        backoff_factor (int): Factor to increase delay by on each retry
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:  # Last attempt
                        raise
                    
                    logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed: {str(e)}. Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= backoff_factor
        return wrapper
    return decorator

@retry_with_backoff(max_attempts=3, initial_delay=1)
def check_container_health(container_name, port, path='/healthz', timeout=5):
    """
    Check the health of a container service.
    
    Args:
        container_name (str): Name of the container service
        port (int): Port the service is running on
        path (str): Health check path
        timeout (int): Request timeout in seconds
        
    Returns:
        dict: Health check result
    """
    # First try container name
    urls = []
    if is_running_in_container():
        urls.append(f"http://{container_name}:{port}{path}")
    
    # Also try localhost
    urls.append(f"http://localhost:{port}{path}")
    
    # Try each URL
    for url in urls:
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                try:
                    # Try to parse as JSON
                    data = response.json()
                    return {
                        'healthy': True,
                        'url': url,
                        'status_code': response.status_code,
                        'data': data
                    }
                except json.JSONDecodeError:
                    # Not JSON, just return text
                    return {
                        'healthy': True,
                        'url': url,
                        'status_code': response.status_code,
                        'data': response.text
                    }
            else:
                logger.warning(f"Health check for {container_name} at {url} returned status {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Health check for {container_name} at {url} failed: {str(e)}")
    
    # If we get here, all attempts failed
    return {
        'healthy': False,
        'urls_tried': urls,
        'error': 'All health check attempts failed'
    }

def check_all_services_health():
    """
    Check the health of all services.
    
    Returns:
        dict: Health check results for all services
    """
    services = {
        'atlantis': {
            'port': 4141,
            'path': '/healthz'
        },
        'web': {
            'port': 5150,
            'path': '/healthz'
        },
        'netbox': {
            'port': 8000,
            'path': '/api/status/'
        }
    }
    
    results = {}
    for service_name, config in services.items():
        try:
            results[service_name] = check_container_health(
                service_name, 
                config['port'], 
                config['path']
            )
        except Exception as e:
            results[service_name] = {
                'healthy': False,
                'error': str(e)
            }
    
    return results
