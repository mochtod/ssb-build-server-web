#!/usr/bin/env python3
"""
Enhanced Redis Cache for vSphere Synchronization

This module implements incremental synchronization for vSphere resources,
ensuring that only delta changes are processed after initial caching.
"""

import os
import json
import time
import logging
import redis
import hashlib
import datetime
from typing import Dict, List, Any, Optional, Set, Tuple

# Configure logging
logger = logging.getLogger(__name__)

# Redis connection parameters - get from environment or use defaults
REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)

# Cache configuration
DEFAULT_TTL = int(os.environ.get('VSPHERE_CACHE_TTL', 7200))  # Default 2 hours
DELTA_SYNC_ENABLED = os.environ.get('VSPHERE_DELTA_SYNC', 'true').lower() == 'true'
ENABLE_PERSISTENT_STORAGE = os.environ.get('REDIS_PERSISTENCE', 'true').lower() == 'true'

# Redis client singleton
_redis_client = None

def get_redis_client() -> Optional[redis.Redis]:
    """
    Get a Redis client connection, creating it if necessary.
    Returns None if connection fails.
    """
    global _redis_client
    
    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )
            # Test connection
            _redis_client.ping()
            logger.info(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
            
            # Configure persistence if enabled
            if ENABLE_PERSISTENT_STORAGE:
                try:
                    # Check current persistence configuration
                    config_get = _redis_client.config_get('save')
                    if 'save' in config_get and not config_get['save']:
                        # Enable RDB persistence with reasonable defaults if not set
                        _redis_client.config_set('save', '900 1 300 10 60 10000')
                        logger.info("Enabled Redis persistence configuration")
                    else:
                        logger.info(f"Redis persistence already configured: {config_get}")
                except redis.RedisError as config_err:
                    logger.warning(f"Could not configure Redis persistence: {config_err}")
                    
        except redis.RedisError as e:
            logger.error(f"Failed to connect to Redis at {REDIS_HOST}:{REDIS_PORT}: {e}")
            _redis_client = None
    
    return _redis_client

def generate_resource_key(resource_type: str) -> str:
    """Generate a Redis key for a specific resource type."""
    return f"vsphere_{resource_type}"

def generate_delta_key(resource_type: str) -> str:
    """Generate a Redis key for delta tracking of a specific resource type."""
    return f"vsphere_delta_{resource_type}"

def get_cached_resource(resource_type: str) -> List[Dict[str, Any]]:
    """
    Get a resource from Redis cache.
    Returns an empty list if not found or error occurs.
    """
    r = get_redis_client()
    if not r:
        return []
    
    try:
        cache_key = generate_resource_key(resource_type)
        cached_data = r.get(cache_key)
        
        if cached_data:
            return json.loads(cached_data)
    except redis.RedisError as e:
        logger.error(f"Redis error getting cached {resource_type}: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for cached {resource_type}: {e}")
    
    return []

def cache_resource(resource_type: str, resources: List[Dict[str, Any]], ttl: int = DEFAULT_TTL) -> bool:
    """
    Cache a resource in Redis.
    Returns True if successful, False otherwise.
    """
    r = get_redis_client()
    if not r:
        return False
    
    try:
        cache_key = generate_resource_key(resource_type)
        r.setex(cache_key, ttl, json.dumps(resources))
        logger.info(f"Cached {len(resources)} {resource_type} with TTL {ttl}s")
        return True
    except redis.RedisError as e:
        logger.error(f"Redis error caching {resource_type}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error caching {resource_type}: {e}")
    
    return False

def cache_delta_metadata(resource_type: str, 
                          added: Set[str], 
                          removed: Set[str], 
                          updated: Set[str]) -> bool:
    """
    Cache metadata about the delta changes for a resource type.
    This is useful for tracking what changed during a sync.
    """
    r = get_redis_client()
    if not r:
        return False
    
    try:
        delta_key = generate_delta_key(resource_type)
        delta_data = {
            'timestamp': datetime.datetime.now().isoformat(),
            'added': list(added),
            'removed': list(removed),
            'updated': list(updated),
            'added_count': len(added),
            'removed_count': len(removed),
            'updated_count': len(updated),
            'total_changes': len(added) + len(removed) + len(updated)
        }
        
        r.set(delta_key, json.dumps(delta_data))
        logger.info(f"Cached delta metadata for {resource_type}: " 
                    f"+{len(added)}, -{len(removed)}, Δ{len(updated)}")
        return True
    except redis.RedisError as e:
        logger.error(f"Redis error caching delta metadata for {resource_type}: {e}")
    
    return False

def get_delta_metadata(resource_type: str) -> Dict[str, Any]:
    """
    Get metadata about the most recent delta changes for a resource type.
    """
    r = get_redis_client()
    if not r:
        return {}
    
    try:
        delta_key = generate_delta_key(resource_type)
        delta_data = r.get(delta_key)
        
        if delta_data:
            return json.loads(delta_data)
    except redis.RedisError as e:
        logger.error(f"Redis error getting delta metadata for {resource_type}: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for delta metadata for {resource_type}: {e}")
    
    return {}

def calculate_delta_changes(existing_resources: List[Dict[str, Any]], 
                           new_resources: List[Dict[str, Any]], 
                           id_key: str = 'id',
                           name_key: str = 'name',
                           check_updates: bool = True) -> Tuple[List[Dict[str, Any]], Set[str], Set[str], Set[str]]:
    """
    Calculate delta changes between existing resources and new resources.
    
    Args:
        existing_resources: List of existing resource dictionaries
        new_resources: List of new resource dictionaries
        id_key: The key to use as unique identifier (defaults to 'id')
        name_key: Fallback key to use if id_key is not present (defaults to 'name')
        check_updates: Whether to check for updates to existing resources
        
    Returns:
        Tuple containing:
        - merged_resources: List of resources with updates applied
        - added_ids: Set of IDs for resources that were added
        - removed_ids: Set of IDs for resources that were removed
        - updated_ids: Set of IDs for resources that were updated
    """
    # Create maps to track existing and new resources by ID
    existing_by_id = {}
    for res in existing_resources:
        # Use id_key if present, otherwise fall back to name_key
        res_id = res.get(id_key, res.get(name_key, str(res)))
        existing_by_id[res_id] = res
    
    new_by_id = {}
    for res in new_resources:
        res_id = res.get(id_key, res.get(name_key, str(res)))
        new_by_id[res_id] = res
    
    # Find added, removed, and common resources
    existing_ids = set(existing_by_id.keys())
    new_ids = set(new_by_id.keys())
    
    added_ids = new_ids - existing_ids
    removed_ids = existing_ids - new_ids
    common_ids = existing_ids & new_ids
    
    # Check for updates to common resources if requested
    updated_ids = set()
    if check_updates:
        for res_id in common_ids:
            existing_res = existing_by_id[res_id]
            new_res = new_by_id[res_id]
            
            # Compare resource properties, excluding metadata
            for key, value in new_res.items():
                if key not in ['last_update', 'cached_at', 'metadata'] and \
                   key in existing_res and existing_res[key] != value:
                    updated_ids.add(res_id)
                    break
    
    # Create merged resources list
    merged_resources = []
    
    # Include all new resources
    for res_id in new_ids:
        merged_resources.append(new_by_id[res_id])
    
    # Include existing resources that weren't removed
    for res_id in existing_ids - removed_ids - new_ids:
        merged_resources.append(existing_by_id[res_id])
    
    return merged_resources, added_ids, removed_ids, updated_ids

def update_vsphere_resources(inventory_data: Dict[str, Any], 
                            resource_types: List[str] = None) -> Dict[str, Dict[str, int]]:
    """
    Update the Redis cache with vSphere resources, calculating and applying delta changes.
    
    Args:
        inventory_data: Dictionary containing vSphere resources
        resource_types: List of resource types to update (defaults to standard types)
        
    Returns:
        Dictionary with change counts for each resource type
    """
    if resource_types is None:
        resource_types = ['datacenters', 'resource_pools', 'datastores', 'templates', 'networks']
    
    changes = {}
    
    for resource_type in resource_types:
        if resource_type not in inventory_data:
            logger.warning(f"Resource type {resource_type} not found in inventory data")
            continue
        
        # Get new resources for this type
        new_resources = inventory_data[resource_type]
        
        # Handle different resource formats (list of strings vs list of dicts)
        if new_resources and isinstance(new_resources[0], str):
            # Convert string list to list of dicts
            new_resources = [{'name': r, 'id': r} for r in new_resources]
        
        # Get existing resources from cache
        existing_resources = get_cached_resource(resource_type)
        
        # If no existing resources, just cache the new ones
        if not existing_resources:
            cache_resource(resource_type, new_resources)
            changes[resource_type] = {
                'added': len(new_resources),
                'removed': 0,
                'updated': 0,
                'total': len(new_resources)
            }
            continue
        
        # Calculate delta changes
        merged_resources, added_ids, removed_ids, updated_ids = calculate_delta_changes(
            existing_resources, new_resources
        )
        
        # Cache delta metadata
        cache_delta_metadata(resource_type, added_ids, removed_ids, updated_ids)
        
        # Cache the merged resources
        cache_resource(resource_type, merged_resources)
        
        # Record change counts
        changes[resource_type] = {
            'added': len(added_ids),
            'removed': len(removed_ids),
            'updated': len(updated_ids),
            'total': len(merged_resources)
        }
        
        # Log changes
        if added_ids or removed_ids or updated_ids:
            logger.info(f"Changes in {resource_type}: +{len(added_ids)}, -"
                        f"{len(removed_ids)}, Δ{len(updated_ids)}")
    
    return changes

def get_vsphere_resources_from_cache() -> Dict[str, Any]:
    """
    Get all vSphere resources from Redis cache.
    
    Returns:
        Dictionary containing all vSphere resources
    """
    resource_types = ['datacenters', 'resource_pools', 'datastores', 'templates', 'networks']
    result = {}
    
    for resource_type in resource_types:
        result[resource_type] = get_cached_resource(resource_type)
    
    # Add cache metadata
    result['cached_at'] = datetime.datetime.now().isoformat()
    result['from_cache'] = True
    
    return result

def get_sync_status() -> Dict[str, Any]:
    """
    Get the current vSphere sync status from Redis.
    
    Returns:
        Dictionary containing sync status information
    """
    r = get_redis_client()
    if not r:
        return {
            'status': 'unknown',
            'message': 'Redis connection not available',
            'progress': 0
        }
    
    try:
        status_key = 'vsphere_sync_status'
        status_data = r.get(status_key)
        
        if status_data:
            return json.loads(status_data)
    except redis.RedisError as e:
        logger.error(f"Redis error getting sync status: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for sync status: {e}")
    
    # Default status if not found
    return {
        'status': 'unknown',
        'message': 'No sync status found',
        'progress': 0
    }

def update_sync_status(status: Dict[str, Any], ttl: int = 300) -> bool:
    """
    Update the vSphere sync status in Redis.
    
    Args:
        status: Dictionary containing sync status information
        ttl: Time-to-live in seconds for the status
        
    Returns:
        True if successful, False otherwise
    """
    r = get_redis_client()
    if not r:
        return False
    
    try:
        status_key = 'vsphere_sync_status'
        
        # Add timestamp if not present
        if 'timestamp' not in status:
            status['timestamp'] = datetime.datetime.now().isoformat()
        
        r.setex(status_key, ttl, json.dumps(status))
        return True
    except redis.RedisError as e:
        logger.error(f"Redis error updating sync status: {e}")
    
    return False

# Additional utility functions for advanced use cases

def clear_vsphere_cache() -> bool:
    """
    Clear all vSphere resources from Redis cache.
    
    Returns:
        True if successful, False otherwise
    """
    r = get_redis_client()
    if not r:
        return False
    
    try:
        # Get all keys matching vsphere_*
        vsphere_keys = r.keys('vsphere_*')
        
        if vsphere_keys:
            r.delete(*vsphere_keys)
            logger.info(f"Cleared {len(vsphere_keys)} vSphere cache keys")
        else:
            logger.info("No vSphere cache keys found to clear")
        
        return True
    except redis.RedisError as e:
        logger.error(f"Redis error clearing vSphere cache: {e}")
    
    return False

def get_cache_stats() -> Dict[str, Any]:
    """
    Get statistics about the vSphere cache.
    
    Returns:
        Dictionary containing cache statistics
    """
    r = get_redis_client()
    if not r:
        return {}
    
    stats = {
        'timestamp': datetime.datetime.now().isoformat(),
        'resources': {}
    }
    
    try:
        # Get stats for each resource type
        resource_types = ['datacenters', 'resource_pools', 'datastores', 'templates', 'networks']
        for resource_type in resource_types:
            cache_key = generate_resource_key(resource_type)
            delta_key = generate_delta_key(resource_type)
            
            resources = get_cached_resource(resource_type)
            delta_metadata = get_delta_metadata(resource_type)
            
            # Get TTL for the cache key
            ttl = r.ttl(cache_key)
            
            stats['resources'][resource_type] = {
                'count': len(resources),
                'ttl': ttl,
                'last_delta': delta_metadata.get('timestamp', 'never'),
                'delta_changes': delta_metadata.get('total_changes', 0)
            }
        
        # Get overall Redis stats
        info = r.info()
        stats['redis'] = {
            'used_memory_human': info.get('used_memory_human', 'unknown'),
            'connected_clients': info.get('connected_clients', 0),
            'uptime_in_seconds': info.get('uptime_in_seconds', 0)
        }
    except redis.RedisError as e:
        logger.error(f"Redis error getting cache stats: {e}")
    
    return stats

if __name__ == "__main__":
    # Setup logging for standalone testing
    logging.basicConfig(level=logging.INFO, 
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Test Redis connection
    redis_client = get_redis_client()
    if redis_client:
        print("Successfully connected to Redis")
        
        # Test caching a resource
        test_resources = [
            {'id': '1', 'name': 'Resource 1'},
            {'id': '2', 'name': 'Resource 2'},
            {'id': '3', 'name': 'Resource 3'}
        ]
        
        if cache_resource('test', test_resources):
            print("Successfully cached test resources")
            
            # Test retrieving a resource
            cached_resources = get_cached_resource('test')
            print(f"Retrieved {len(cached_resources)} cached test resources")
            
            # Test clearing the cache
            if clear_vsphere_cache():
                print("Successfully cleared vSphere cache")
    else:
        print("Failed to connect to Redis")
