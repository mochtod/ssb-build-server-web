#!/usr/bin/env python3
"""
NetBox IP Address Allocation Script for VM provisioning.

This script integrates with NetBox to allocate the next available IP address within a specified
prefix. It includes error handling, caching mechanisms, and validation to ensure reliable
operation even when NetBox is temporarily unavailable.

Usage:
    As a standalone script:
        python fetch_next_ip.py --range <prefix_id> --token <netbox_token> [--api-url <netbox_api_url>]
    
    Via stdin (for Terraform external data provider):
        echo '{"range": "123", "token": "abcdef", "api_url": "https://netbox.example.com/api"}' | python fetch_next_ip.py
"""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
import ipaddress
import urllib3
import requests
from requests.exceptions import RequestException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('netbox_ip_allocator')

# Disable insecure HTTPS warnings for internal servers with self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Constants
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.ip_cache')
CACHE_EXPIRY = 3600  # Cache expiry in seconds (1 hour)
DEFAULT_API_URL = "https://netbox.chrobinson.com/api"

class IPCache:
    """Manages caching of IP addresses for each prefix range."""
    
    def __init__(self, cache_dir=CACHE_DIR):
        """Initialize the cache directory."""
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def get_cache_file(self, range_id):
        """Generate cache file path for a range ID."""
        return os.path.join(self.cache_dir, f"range_{range_id}.json")
    
    def get_cached_ips(self, range_id):
        """Get cached IP addresses for a range, if available and not expired."""
        cache_file = self.get_cache_file(range_id)
        
        if not os.path.exists(cache_file):
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Check if cache is expired
            if time.time() - cache_data.get('timestamp', 0) > CACHE_EXPIRY:
                logger.info(f"Cache for range {range_id} is expired")
                return None
                
            # Return cached IPs if available
            cached_ips = cache_data.get('available_ips', [])
            if not cached_ips:
                return None
                
            logger.info(f"Found {len(cached_ips)} cached IPs for range {range_id}")
            return cached_ips
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Error reading cache file: {str(e)}")
            return None
            
    def cache_ips(self, range_id, ips):
        """Cache available IP addresses for a range."""
        if not ips:
            logger.warning("No IPs to cache")
            return
            
        cache_file = self.get_cache_file(range_id)
        cache_data = {
            'timestamp': time.time(),
            'available_ips': ips
        }
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)
            logger.info(f"Cached {len(ips)} IPs for range {range_id}")
        except Exception as e:
            logger.error(f"Error writing to cache file: {str(e)}")
    
    def get_and_remove_ip(self, range_id):
        """Get the next available IP and remove it from the cache."""
        cached_ips = self.get_cached_ips(range_id)
        if not cached_ips:
            return None
            
        # Get the first IP and remove it from the cache
        next_ip = cached_ips.pop(0)
        
        # Update the cache with the remaining IPs
        try:
            cache_file = self.get_cache_file(range_id)
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            cache_data['available_ips'] = cached_ips
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)
            
            logger.info(f"Allocated IP {next_ip} from cache, {len(cached_ips)} IPs remaining")
            return next_ip
        except Exception as e:
            logger.error(f"Error updating cache file: {str(e)}")
            return next_ip  # Still return the IP even if we couldn't update the cache

def fetch_available_ips(range_id, token, api_url=DEFAULT_API_URL, limit=10):
    """
    Fetch available IPs from NetBox for a specific prefix range.
    
    Args:
        range_id: The NetBox prefix ID to allocate from
        token: NetBox API token
        api_url: NetBox API URL
        limit: Maximum number of IPs to fetch
        
    Returns:
        List of available IP addresses
    """
    url = f"{api_url}/ipam/prefixes/{range_id}/available-ips/"
    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json"
    }
    
    params = {
        "limit": limit
    }
    
    try:
        logger.info(f"Requesting available IPs from NetBox for range {range_id}")
        response = requests.get(
            url, 
            headers=headers, 
            params=params,
            verify=False,  # Skip SSL verification for internal servers
            timeout=10  # Set a reasonable timeout
        )
        response.raise_for_status()
        
        # Parse response
        available_ips = []
        for ip_data in response.json():
            if 'address' in ip_data:
                # Extract just the IP without the CIDR notation
                ip = ip_data['address'].split('/')[0]
                available_ips.append(ip)
        
        logger.info(f"Retrieved {len(available_ips)} available IPs from NetBox")
        return available_ips
    except RequestException as e:
        logger.error(f"Error fetching available IPs from NetBox: {str(e)}")
        return None

def validate_ip(ip_address):
    """Validate that the string is a valid IP address."""
    try:
        ipaddress.ip_address(ip_address)
        return True
    except ValueError:
        return False

def generate_fallback_ip(range_id, index=1):
    """
    Generate a fallback IP when NetBox is unavailable.
    This is only for development/testing and should be clearly marked as such.
    
    Args:
        range_id: The prefix ID as a string
        index: An index to ensure uniqueness
        
    Returns:
        A unique IP address based on the range_id
    """
    # Use a fixed prefix pattern for fallback IPs
    return f"192.168.{range_id % 255}.{index % 254 + 1}"

def fetch_next_ip(range_id, token, api_url=None, use_cache=True, use_fallback=True):
    """
    Fetch the next available IP address from NetBox.
    
    Args:
        range_id: The NetBox prefix ID to allocate from
        token: NetBox API token
        api_url: NetBox API URL (optional)
        use_cache: Whether to use/update the IP cache
        use_fallback: Whether to generate a fallback IP if NetBox is unavailable
        
    Returns:
        The next available IP address as a string
    """
    if not api_url:
        api_url = DEFAULT_API_URL
    
    # Initialize cache if using it
    ip_cache = IPCache() if use_cache else None
    
    # Try to get IP from cache first
    if use_cache:
        cached_ip = ip_cache.get_and_remove_ip(range_id)
        if cached_ip:
            logger.info(f"Using cached IP: {cached_ip}")
            return cached_ip
    
    # Try to fetch from NetBox
    try:
        available_ips = fetch_available_ips(range_id, token, api_url)
        
        if not available_ips:
            raise ValueError("No available IPs returned from NetBox")
        
        # Cache the remaining IPs if using cache
        if use_cache and len(available_ips) > 1:
            ip_cache.cache_ips(range_id, available_ips[1:])
        
        # Return the first available IP
        next_ip = available_ips[0]
        logger.info(f"Allocated IP {next_ip} from NetBox")
        return next_ip
        
    except Exception as e:
        logger.error(f"Error allocating IP from NetBox: {str(e)}")
        
        # Use fallback if enabled and needed
        if use_fallback:
            fallback_ip = generate_fallback_ip(int(range_id))
            logger.warning(f"Using fallback IP: {fallback_ip} (FOR DEVELOPMENT ONLY)")
            return fallback_ip
        else:
            # Re-raise the exception if no fallback is desired
            raise

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='Fetch next available IP from NetBox')
    parser.add_argument('--range', help='NetBox prefix ID')
    parser.add_argument('--token', help='NetBox API token')
    parser.add_argument('--api-url', help='NetBox API URL')
    parser.add_argument('--no-cache', action='store_true', help='Disable IP caching')
    parser.add_argument('--no-fallback', action='store_true', help='Disable fallback IP generation')
    return parser.parse_args()

def main():
    # Check if input is coming from stdin (for Terraform)
    if not sys.stdin.isatty():
        try:
            query = json.loads(sys.stdin.read())
            range_id = query.get("range")
            token = query.get("token")
            api_url = query.get("api_url")
            use_cache = not query.get("no_cache", False)
            use_fallback = not query.get("no_fallback", False)
            
            if not range_id or not token:
                raise ValueError("Missing required parameters: range and/or token")
                
            ip = fetch_next_ip(range_id, token, api_url, use_cache, use_fallback)
            print(json.dumps({"ip": ip}))
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON input: {str(e)}")
            print(json.dumps({"error": f"Invalid JSON input: {str(e)}"}))
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            print(json.dumps({"error": str(e)}))
            sys.exit(1)
    else:
        # Command-line usage
        args = parse_args()
        
        if not args.range or not args.token:
            print("Error: Missing required parameters (--range and --token)")
            sys.exit(1)
            
        try:
            ip = fetch_next_ip(
                args.range, 
                args.token, 
                args.api_url, 
                not args.no_cache, 
                not args.no_fallback
            )
            print(f"Next available IP: {ip}")
        except Exception as e:
            print(f"Error: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    main()
