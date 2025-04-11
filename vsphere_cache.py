#!/usr/bin/env python3
"""
VSphere Resource Caching Module for SSB Build Server Web.

This module provides enhanced caching for VMware vSphere resources with
intelligent cache invalidation, resource-specific timeouts, and retry logic.
It helps reduce API calls to vSphere while ensuring data freshness.

The module caches various resource types:
- Resource pools
- Datastores
- Networks
- VM templates

Each resource type can have different cache expiry times based on how frequently
they typically change in a vSphere environment.
"""
import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple

# Import the config module
try:
    from config import config
except ImportError:
    # Fallback to environment variables if config module is not available
    import os
    class SimpleConfig:
        def get(self, key, default=None):
            return os.environ.get(key, default)
        def get_int(self, key, default=None):
            try:
                value = os.environ.get(key)
                return int(value) if value is not None else default
            except (ValueError, TypeError):
                return default
        def get_bool(self, key, default=None):
            value = os.environ.get(key)
            if value is None:
                return default
            return value.lower() in ('true', 'yes', 'y', '1')
    config = SimpleConfig()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('vsphere_cache')

# Cache file location
CACHE_DIR = Path(config.get('VSPHERE_CACHE_DIR', '.vsphere_cache'))

# Default cache expiry times in seconds
DEFAULT_CACHE_EXPIRY = config.get_int('VSPHERE_CACHE_EXPIRY', 3600)  # 1 hour

# Resource-specific cache expiry times
RESOURCE_CACHE_EXPIRY = {
    'resource_pools': config.get_int('VSPHERE_RESOURCE_POOL_CACHE_EXPIRY', DEFAULT_CACHE_EXPIRY),
    'datastores': config.get_int('VSPHERE_DATASTORE_CACHE_EXPIRY', DEFAULT_CACHE_EXPIRY),
    'networks': config.get_int('VSPHERE_NETWORK_CACHE_EXPIRY', DEFAULT_CACHE_EXPIRY),
    'templates': config.get_int('VSPHERE_TEMPLATE_CACHE_EXPIRY', DEFAULT_CACHE_EXPIRY * 3)  # Templates change less frequently
}

# Cache lock for thread safety
cache_lock = threading.RLock()

class VSphereCache:
    """
    Enhanced caching mechanism for vSphere resources.
    """
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the cache.
        
        Args:
            cache_dir: Directory to store cache files (default: .vsphere_cache)
        """
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache
        self.memory_cache = {}
        
        # Initialize cache
        self._load_cache()
        
        logger.info(f"VSphere cache initialized (dir: {self.cache_dir})")
    
    def _get_cache_file(self, resource_type: str) -> Path:
        """Get the cache file path for a specific resource type."""
        return self.cache_dir / f"{resource_type}.json"
    
    def _load_cache(self):
        """Load all cache files into memory."""
        with cache_lock:
            for resource_type in RESOURCE_CACHE_EXPIRY.keys():
                cache_file = self._get_cache_file(resource_type)
                if cache_file.exists():
                    try:
                        with open(cache_file, 'r') as f:
                            cache_data = json.load(f)
                            self.memory_cache[resource_type] = cache_data
                            logger.debug(f"Loaded {resource_type} cache from {cache_file}")
                    except (json.JSONDecodeError, IOError) as e:
                        logger.warning(f"Error reading cache file {cache_file}: {str(e)}")
                        # Initialize empty cache
                        self.memory_cache[resource_type] = {
                            'timestamp': 0,
                            'items': []
                        }
                else:
                    # Initialize empty cache
                    self.memory_cache[resource_type] = {
                        'timestamp': 0,
                        'items': []
                    }
    
    def is_cache_valid(self, resource_type: str) -> bool:
        """
        Check if the cache for a specific resource type is valid.
        
        Args:
            resource_type: Type of vSphere resource
            
        Returns:
            True if the cache is valid, False otherwise
        """
        if resource_type not in self.memory_cache:
            return False
        
        cache_data = self.memory_cache[resource_type]
        timestamp = cache_data.get('timestamp', 0)
        expiry = RESOURCE_CACHE_EXPIRY.get(resource_type, DEFAULT_CACHE_EXPIRY)
        
        # Check if cache is expired
        return (time.time() - timestamp) < expiry
    
    def get_cached_resources(self, resource_type: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached resources of a specific type.
        
        Args:
            resource_type: Type of vSphere resource
            
        Returns:
            List of resources or None if cache is invalid
        """
        with cache_lock:
            if not self.is_cache_valid(resource_type):
                return None
            
            return self.memory_cache[resource_type].get('items', [])
    
    def update_cache(self, resource_type: str, resources: List[Dict[str, Any]]):
        """
        Update the cache for a specific resource type.
        
        Args:
            resource_type: Type of vSphere resource
            resources: List of resources to cache
        """
        with cache_lock:
            # Update memory cache
            self.memory_cache[resource_type] = {
                'timestamp': time.time(),
                'items': resources
            }
            
            # Write to cache file
            cache_file = self._get_cache_file(resource_type)
            try:
                with open(cache_file, 'w') as f:
                    json.dump(self.memory_cache[resource_type], f, indent=2)
                logger.info(f"Updated {resource_type} cache with {len(resources)} items")
            except IOError as e:
                logger.warning(f"Error writing cache to {cache_file}: {str(e)}")
    
    def invalidate_cache(self, resource_type: Optional[str] = None):
        """
        Invalidate cache for a specific resource type or all resources.
        
        Args:
            resource_type: Type of vSphere resource or None to invalidate all
        """
        with cache_lock:
            if resource_type is None:
                # Invalidate all caches
                for rt in list(self.memory_cache.keys()):
                    self._invalidate_single_cache(rt)
            else:
                # Invalidate specific cache
                self._invalidate_single_cache(resource_type)
    
    def _invalidate_single_cache(self, resource_type: str):
        """Invalidate a single resource type cache."""
        if resource_type in self.memory_cache:
            # Just set the timestamp to 0 to invalidate
            self.memory_cache[resource_type]['timestamp'] = 0
            
            # Update the cache file
            cache_file = self._get_cache_file(resource_type)
            try:
                with open(cache_file, 'w') as f:
                    json.dump(self.memory_cache[resource_type], f, indent=2)
                logger.info(f"Invalidated {resource_type} cache")
            except IOError as e:
                logger.warning(f"Error writing cache to {cache_file}: {str(e)}")
    
    def clear_cache(self, resource_type: Optional[str] = None):
        """
        Clear cache for a specific resource type or all resources.
        
        Args:
            resource_type: Type of vSphere resource or None to clear all
        """
        with cache_lock:
            if resource_type is None:
                # Clear all caches
                for rt in list(self.memory_cache.keys()):
                    self._clear_single_cache(rt)
            else:
                # Clear specific cache
                self._clear_single_cache(resource_type)
    
    def _clear_single_cache(self, resource_type: str):
        """Clear a single resource type cache."""
        if resource_type in self.memory_cache:
            # Reset the cache
            self.memory_cache[resource_type] = {
                'timestamp': 0,
                'items': []
            }
            
            # Remove the cache file
            cache_file = self._get_cache_file(resource_type)
            try:
                if cache_file.exists():
                    cache_file.unlink()
                logger.info(f"Cleared {resource_type} cache")
            except IOError as e:
                logger.warning(f"Error removing cache file {cache_file}: {str(e)}")
    
    def get_cache_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about the cache.
        
        Returns:
            Dictionary with cache information for each resource type
        """
        info = {}
        with cache_lock:
            for resource_type in RESOURCE_CACHE_EXPIRY.keys():
                if resource_type in self.memory_cache:
                    cache_data = self.memory_cache[resource_type]
                    timestamp = cache_data.get('timestamp', 0)
                    items = cache_data.get('items', [])
                    
                    if timestamp > 0:
                        # Format timestamp as readable date/time
                        cache_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                        expiry = RESOURCE_CACHE_EXPIRY.get(resource_type, DEFAULT_CACHE_EXPIRY)
                        expires_at = datetime.fromtimestamp(timestamp + expiry).strftime('%Y-%m-%d %H:%M:%S')
                        valid = self.is_cache_valid(resource_type)
                    else:
                        cache_time = "Never"
                        expires_at = "N/A"
                        valid = False
                    
                    info[resource_type] = {
                        'cached_at': cache_time,
                        'expires_at': expires_at,
                        'valid': valid,
                        'item_count': len(items),
                        'size_bytes': len(json.dumps(items))
                    }
                else:
                    info[resource_type] = {
                        'cached_at': "Never",
                        'expires_at': "N/A",
                        'valid': False,
                        'item_count': 0,
                        'size_bytes': 0
                    }
        
        return info
    
    def get_resource(self, resource_type: str, resource_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific resource by ID from the cache.
        
        Args:
            resource_type: Type of vSphere resource
            resource_id: ID of the resource to retrieve
            
        Returns:
            The resource or None if not found
        """
        resources = self.get_cached_resources(resource_type)
        if not resources:
            return None
        
        # Find the resource with the matching ID
        for resource in resources:
            if resource.get('id') == resource_id:
                return resource
        
        return None
    
    def get_resources_by_name(self, resource_type: str, name_pattern: str) -> List[Dict[str, Any]]:
        """
        Get resources that match a name pattern from the cache.
        
        Args:
            resource_type: Type of vSphere resource
            name_pattern: String pattern to match in resource names
            
        Returns:
            List of matching resources
        """
        resources = self.get_cached_resources(resource_type)
        if not resources:
            return []
        
        # Find resources with names containing the pattern
        return [r for r in resources if name_pattern.lower() in r.get('name', '').lower()]
    
    def get_preferred_resources(self, resource_type: str) -> List[Dict[str, Any]]:
        """
        Get preferred resources from the cache.
        
        Args:
            resource_type: Type of vSphere resource
            
        Returns:
            List of preferred resources
        """
        resources = self.get_cached_resources(resource_type)
        if not resources:
            return []
        
        # Find resources marked as preferred
        return [r for r in resources if r.get('is_preferred', False)]

# Global cache instance
vsphere_cache = VSphereCache()

def cached_resource_fetcher(resource_type: str):
    """
    Decorator for resource fetching functions to add caching.
    
    Args:
        resource_type: Type of vSphere resource
        
    Returns:
        Decorated function
    """
    def decorator(fetch_func):
        def wrapper(*args, use_cache=True, force_refresh=False, **kwargs):
            # Check if we should use the cache
            if use_cache and not force_refresh:
                cached_resources = vsphere_cache.get_cached_resources(resource_type)
                if cached_resources is not None:
                    logger.info(f"Using cached {resource_type} ({len(cached_resources)} items)")
                    return cached_resources
            
            # Cache miss or forced refresh, call the original function
            logger.info(f"Fetching {resource_type} from vSphere")
            try:
                resources = fetch_func(*args, **kwargs)
                
                # Update the cache
                if resources is not None and use_cache:
                    vsphere_cache.update_cache(resource_type, resources)
                
                return resources
            except Exception as e:
                logger.error(f"Error fetching {resource_type}: {str(e)}")
                
                # Try to use expired cache in case of failure
                if use_cache:
                    cache_file = vsphere_cache._get_cache_file(resource_type)
                    if cache_file.exists():
                        try:
                            with open(cache_file, 'r') as f:
                                cache_data = json.load(f)
                                resources = cache_data.get('items', [])
                                logger.warning(f"Using expired cache for {resource_type} due to fetch error")
                                return resources
                        except Exception as cache_error:
                            logger.error(f"Error reading expired cache: {str(cache_error)}")
                
                # Re-raise the original exception
                raise
        
        return wrapper
    
    return decorator

if __name__ == "__main__":
    """When run as a script, show cache information."""
    import argparse
    parser = argparse.ArgumentParser(description='vSphere Resource Cache')
    parser.add_argument('--clear', action='store_true', help='Clear all caches')
    parser.add_argument('--invalidate', action='store_true', help='Invalidate all caches')
    parser.add_argument('--type', choices=list(RESOURCE_CACHE_EXPIRY.keys()), help='Specific resource type to operate on')
    args = parser.parse_args()
    
    if args.clear:
        if args.type:
            vsphere_cache.clear_cache(args.type)
            print(f"Cleared {args.type} cache")
        else:
            vsphere_cache.clear_cache()
            print("Cleared all caches")
    elif args.invalidate:
        if args.type:
            vsphere_cache.invalidate_cache(args.type)
            print(f"Invalidated {args.type} cache")
        else:
            vsphere_cache.invalidate_cache()
            print("Invalidated all caches")
    else:
        # Print cache information
        cache_info = vsphere_cache.get_cache_info()
        print("\nvSphere Resource Cache Information:")
        print("=" * 50)
        for resource_type, info in cache_info.items():
            status = "VALID" if info['valid'] else "INVALID"
            print(f"\n{resource_type.upper()} Cache ({status}):")
            print(f"  Last Updated: {info['cached_at']}")
            print(f"  Expires At:   {info['expires_at']}")
            print(f"  Items:        {info['item_count']}")
            print(f"  Size:         {info['size_bytes'] / 1024:.2f} KB")
