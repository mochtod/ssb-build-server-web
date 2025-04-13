#!/usr/bin/env python3
"""
vSphere Redis Cache Module

This module provides Redis-based caching for vSphere resources to improve
performance and reduce load on the vSphere server. It implements:

1. Redis connection management
2. Resource caching for different resource types with compression
3. Cache invalidation and expiration
4. Background template loading to avoid timeouts
5. Performance measurement decorators
6. Memory-efficient storage with data pruning
7. Selective attribute caching
"""

import os
import logging
import time
import json
import hashlib
import functools
import threading
import queue
import gzip
import pickle
from datetime import datetime, timedelta

# Import Redis
try:
    import redis
except ImportError:
    logging.error("Required redis package not installed. Run: pip install redis")
    raise

# Configure logging
logger = logging.getLogger(__name__)

# Redis connection settings from environment variables
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', '')

# Cache settings
CACHE_PREFIX = 'vsphere:'
CACHE_TTL = int(os.environ.get('VSPHERE_CACHE_EXPIRY', 3600))  # 1 hour default
RESOURCE_TYPES = ['datastores', 'networks', 'resource_pools', 'templates']

# Memory optimization settings
COMPRESSION_ENABLED = os.environ.get('VSPHERE_CACHE_COMPRESSION', 'true').lower() == 'true'
COMPRESSION_LEVEL = int(os.environ.get('VSPHERE_CACHE_COMPRESSION_LEVEL', '6'))  # 1-9, higher is more compression
PRUNE_UNUSED_ATTRS = os.environ.get('VSPHERE_CACHE_PRUNE_ATTRS', 'true').lower() == 'true'

# Resource attribute maps (only these attributes will be kept if pruning is enabled)
ESSENTIAL_ATTRIBUTES = {
    'datastores': ['name', 'id', 'type', 'free_gb', 'capacity', 'free_space', 'cluster_id', 'cluster_name', 'shared_across_cluster'],
    'networks': ['name', 'id', 'type', 'cluster_id', 'cluster_name', 'is_dvs'],
    'resource_pools': ['name', 'id', 'type', 'cluster_id', 'cluster_name', 'is_primary'],
    'templates': ['name', 'id', 'type', 'cluster_id', 'cluster_name', 'is_template', 'guest_id', 'guest_fullname']
}

# Redis connection pool
_redis_pool = None
_binary_redis_pool = None  # For binary data (compressed objects)

def get_redis_connection(binary=False):
    """Get a Redis connection from the pool."""
    global _redis_pool, _binary_redis_pool
    
    # Choose the appropriate pool based on binary flag
    pool_ref = _binary_redis_pool if binary else _redis_pool
    pool_var_name = "_binary_redis_pool" if binary else "_redis_pool"
    
    if pool_ref is None:
        try:
            # Create connection pool
            pool_ref = redis.ConnectionPool(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=not binary,  # Don't decode responses for binary data
                socket_timeout=5.0,      # Timeout after 5 seconds
                socket_connect_timeout=5.0,
                health_check_interval=30,
                retry_on_timeout=True
            )
            logger.info(f"Redis connection pool created for {REDIS_HOST}:{REDIS_PORT} ({pool_var_name})")
            
            # Update the global variable
            if binary:
                _binary_redis_pool = pool_ref
            else:
                _redis_pool = pool_ref
                
        except Exception as e:
            logger.error(f"Error creating Redis connection pool: {str(e)}")
            return None
    
    try:
        # Get connection from pool
        return redis.Redis(connection_pool=pool_ref)
    except Exception as e:
        logger.error(f"Error getting Redis connection: {str(e)}")
        return None

def test_redis_connection():
    """Test the Redis connection and return status."""
    try:
        r = get_redis_connection()
        if r is None:
            return False
        
        # Ping the server to make sure it's alive
        result = r.ping()
        
        # Also test binary connection if compression is enabled
        if COMPRESSION_ENABLED:
            r_bin = get_redis_connection(binary=True)
            if r_bin is None:
                logger.warning("Binary Redis connection failed but text connection succeeded")
                # Continue anyway with only text connection
            else:
                r_bin.ping()  # Just to test it works
                
        return result
    except Exception as e:
        logger.error(f"Redis connection test failed: {str(e)}")
        return False

def get_credentials_hash(server, username, password):
    """
    Create a hash of the vSphere credentials to use as a cache key component.
    This ensures resources are not mixed between different vSphere connections.
    """
    creds = f"{server}:{username}:{password}"
    return hashlib.md5(creds.encode()).hexdigest()[:10]

def get_cache_key(resource_type, resource_id, creds_hash):
    """Generate a Redis cache key for a specific resource type and ID."""
    return f"{CACHE_PREFIX}{creds_hash}:{resource_type}:{resource_id}"

def get_compressed_cache_key(resource_type, resource_id, creds_hash):
    """Generate a compressed Redis cache key with a compression indicator."""
    return f"{CACHE_PREFIX}{creds_hash}:{resource_type}:{resource_id}:compressed"

def prune_resource_attributes(resources, resource_type):
    """Remove unnecessary attributes from resource objects to save memory."""
    if not PRUNE_UNUSED_ATTRS or resource_type not in ESSENTIAL_ATTRIBUTES:
        return resources
        
    essential_attrs = set(ESSENTIAL_ATTRIBUTES[resource_type])
    pruned_resources = []
    
    for resource in resources:
        # Only keep essential attributes
        pruned_resource = {k: v for k, v in resource.items() if k in essential_attrs}
        pruned_resources.append(pruned_resource)
    
    return pruned_resources

def cache_cluster_resources(cluster_id, resource_type, resources, creds_hash):
    """Cache resources for a specific cluster and resource type with compression support."""
    if not cluster_id or not resource_type or resources is None:
        return False
    
    # Prune attributes to save memory before caching
    pruned_resources = prune_resource_attributes(resources, resource_type) if resources else resources
    
    try:
        # Generate cache key
        cache_key = get_cache_key(resource_type, cluster_id, creds_hash)
        
        if COMPRESSION_ENABLED:
            # Use binary connection for compressed data
            r = get_redis_connection(binary=True)
            if r is None:
                return False
                
            # Use compressed cache key
            compressed_key = get_compressed_cache_key(resource_type, cluster_id, creds_hash)
            
            # Compress data
            compressed_data = gzip.compress(
                pickle.dumps(pruned_resources), 
                compresslevel=COMPRESSION_LEVEL
            )
            
            # Store with expiration
            result = r.set(compressed_key, compressed_data, ex=CACHE_TTL)
            
            if result:
                logger.debug(f"Cached {len(resources)} {resource_type} for cluster {cluster_id} (compressed)")
        else:
            # Use regular text connection for JSON
            r = get_redis_connection()
            if r is None:
                return False
                
            # Serialize resources to JSON
            json_data = json.dumps(pruned_resources)
            
            # Store with expiration
            result = r.set(cache_key, json_data, ex=CACHE_TTL)
            
            if result:
                logger.debug(f"Cached {len(resources)} {resource_type} for cluster {cluster_id}")
        
        if result:
            # Update index of cluster IDs with cached resources (use text connection)
            r_text = get_redis_connection() if COMPRESSION_ENABLED else r
            index_key = f"{CACHE_PREFIX}{creds_hash}:clusters_with_{resource_type}"
            r_text.sadd(index_key, cluster_id)
            r_text.expire(index_key, CACHE_TTL)
            
            # Update timestamp index
            ts_key = f"{CACHE_PREFIX}{creds_hash}:last_update:{resource_type}:{cluster_id}"
            r_text.set(ts_key, datetime.now().isoformat(), ex=CACHE_TTL)
        
        return result
    except Exception as e:
        logger.error(f"Error caching {resource_type} for cluster {cluster_id}: {str(e)}")
        return False

def get_cached_cluster_resources(cluster_id, resource_type, creds_hash):
    """Get cached resources for a specific cluster and resource type with compression support."""
    if not cluster_id or not resource_type:
        return None
    
    try:
        # First try to get compressed data if compression is enabled
        if COMPRESSION_ENABLED:
            # Get binary connection for compressed data
            r_bin = get_redis_connection(binary=True)
            if r_bin is not None:
                # Get compressed data
                compressed_key = get_compressed_cache_key(resource_type, cluster_id, creds_hash)
                compressed_data = r_bin.get(compressed_key)
                
                if compressed_data:
                    # Decompress and deserialize
                    resources = pickle.loads(gzip.decompress(compressed_data))
                    logger.debug(f"Compressed cache hit: {len(resources)} {resource_type} for cluster {cluster_id}")
                    return resources
        
        # Fall back to uncompressed JSON if no compressed data or compression disabled
        r = get_redis_connection()
        if r is None:
            return None
        
        # Generate cache key
        cache_key = get_cache_key(resource_type, cluster_id, creds_hash)
        
        # Get cached data
        json_data = r.get(cache_key)
        
        if json_data:
            # Deserialize and return
            resources = json.loads(json_data)
            logger.debug(f"Cache hit: {len(resources)} {resource_type} for cluster {cluster_id}")
            return resources
        else:
            logger.debug(f"Cache miss: {resource_type} for cluster {cluster_id}")
            return None
    except Exception as e:
        logger.error(f"Error retrieving cached {resource_type} for cluster {cluster_id}: {str(e)}")
        return None

def invalidate_cluster_cache(cluster_id, creds_hash=None):
    """Invalidate the cache for a specific cluster."""
    try:
        r = get_redis_connection()
        if r is None:
            return False
        
        # If compression is enabled, also get binary connection for compressed data
        r_bin = get_redis_connection(binary=True) if COMPRESSION_ENABLED else None
        
        # If no credentials hash provided, invalidate for all credentials
        if creds_hash is None:
            # Find all creds hashes with this cluster
            pattern = f"{CACHE_PREFIX}*:*:{cluster_id}*"  # Include any suffix for compressed keys
            keys = r.keys(pattern)
            
            # Delete all keys
            if keys:
                r.delete(*keys)
                logger.info(f"Invalidated all caches for cluster {cluster_id}")
            return True
        
        # Delete all resource type caches for this cluster
        deleted = 0
        for resource_type in RESOURCE_TYPES:
            # Delete uncompressed cache
            cache_key = get_cache_key(resource_type, cluster_id, creds_hash)
            if r.delete(cache_key):
                deleted += 1
            
            # Delete compressed cache if enabled
            if COMPRESSION_ENABLED and r_bin is not None:
                compressed_key = get_compressed_cache_key(resource_type, cluster_id, creds_hash)
                if r_bin.delete(compressed_key):
                    deleted += 1
                
            # Update index
            index_key = f"{CACHE_PREFIX}{creds_hash}:clusters_with_{resource_type}"
            r.srem(index_key, cluster_id)
            
            # Delete timestamp
            ts_key = f"{CACHE_PREFIX}{creds_hash}:last_update:{resource_type}:{cluster_id}"
            r.delete(ts_key)
        
        logger.info(f"Invalidated {deleted} resource caches for cluster {cluster_id}")
        return True
    except Exception as e:
        logger.error(f"Error invalidating cache for cluster {cluster_id}: {str(e)}")
        return False

def get_cache_stats(creds_hash=None):
    """Get statistics about the cached data."""
    try:
        r = get_redis_connection()
        if r is None:
            return {}
        
        stats = {
            'total_keys': 0,
            'resource_types': {},
            'memory_usage': {},
            'compression_ratio': {}
        }
        
        # Get all keys
        pattern = f"{CACHE_PREFIX}*" if creds_hash is None else f"{CACHE_PREFIX}{creds_hash}:*"
        all_keys = r.keys(pattern)
        stats['total_keys'] = len(all_keys)
        
        # Count by resource type and estimate memory usage
        for resource_type in RESOURCE_TYPES:
            # Count uncompressed keys
            type_pattern = f"{CACHE_PREFIX}*:{resource_type}:*"
            if COMPRESSION_ENABLED:
                # Exclude compressed keys
                type_pattern = f"{CACHE_PREFIX}*:{resource_type}:[^:]*$"  # Exclude keys with more segments
            type_keys = r.keys(type_pattern)
            uncompressed_count = len(type_keys)
            
            # Count compressed keys if enabled
            compressed_count = 0
            if COMPRESSION_ENABLED:
                compressed_pattern = f"{CACHE_PREFIX}*:{resource_type}:*:compressed"
                compressed_keys = r.keys(compressed_pattern)
                compressed_count = len(compressed_keys)
                
                # Sample a few keys to estimate compression ratio
                if compressed_keys and len(compressed_keys) > 0:
                    # Get size of a sample of compressed vs uncompressed
                    sample_size = min(5, len(compressed_keys))
                    compressed_sizes = []
                    uncompressed_sizes = []
                    
                    for i in range(sample_size):
                        compressed_key = compressed_keys[i]
                        # Extract the uncompressed key
                        uncompressed_key = compressed_key.rsplit(':', 1)[0]
                        
                        # Get compressed size
                        compressed_data = r.get(compressed_key)
                        if compressed_data:
                            compressed_sizes.append(len(compressed_data))
                        
                        # Get uncompressed size if available
                        uncompressed_data = r.get(uncompressed_key)
                        if uncompressed_data:
                            uncompressed_sizes.append(len(uncompressed_data))
                    
                    # Calculate average ratio if we have both sizes
                    if compressed_sizes and uncompressed_sizes:
                        avg_compressed = sum(compressed_sizes) / len(compressed_sizes)
                        avg_uncompressed = sum(uncompressed_sizes) / len(uncompressed_sizes)
                        if avg_uncompressed > 0:
                            ratio = avg_compressed / avg_uncompressed
                            stats['compression_ratio'][resource_type] = ratio
            
            # Update stats
            stats['resource_types'][resource_type] = uncompressed_count + compressed_count
            stats['memory_usage'][resource_type] = {
                'uncompressed_keys': uncompressed_count,
                'compressed_keys': compressed_count
            }
        
        # Get cluster counts
        stats['clusters'] = {}
        for resource_type in RESOURCE_TYPES:
            if creds_hash:
                index_key = f"{CACHE_PREFIX}{creds_hash}:clusters_with_{resource_type}"
                cluster_ids = r.smembers(index_key)
                stats['clusters'][resource_type] = len(cluster_ids)
            else:
                # More complex with multiple credential hashes
                cluster_pattern = f"{CACHE_PREFIX}*:{resource_type}:*"
                cluster_keys = r.keys(cluster_pattern)
                
                # Count unique clusters from keys
                unique_clusters = set()
                for key in cluster_keys:
                    parts = key.split(':')
                    if len(parts) >= 4:  # prefix:creds:type:cluster_id[:compressed]
                        cluster_id = parts[3]
                        unique_clusters.add(cluster_id)
                
                stats['clusters'][resource_type] = len(unique_clusters)
        
        # Get Redis memory stats if available
        try:
            memory_info = r.info('memory')
            stats['redis'] = {
                'used_memory': memory_info.get('used_memory_human', 'unknown'),
                'used_memory_peak': memory_info.get('used_memory_peak_human', 'unknown'),
                'total_system_memory': memory_info.get('total_system_memory_human', 'unknown'),
                'maxmemory': memory_info.get('maxmemory_human', 'unlimited'),
                'maxmemory_policy': memory_info.get('maxmemory_policy', 'unknown')
            }
        except Exception as mem_error:
            logger.debug(f"Could not get Redis memory info: {str(mem_error)}")
        
        return stats
    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
        return {}

def clear_all_cache():
    """Clear all vSphere related cache data from Redis."""
    try:
        r = get_redis_connection()
        if r is None:
            return False
        
        # Find all keys with our prefix
        pattern = f"{CACHE_PREFIX}*"
        keys = r.keys(pattern)
        
        # Delete all keys if any exist
        if keys:
            # Delete in batches to avoid blocking Redis for too long
            batch_size = 100
            for i in range(0, len(keys), batch_size):
                batch = keys[i:i+batch_size]
                r.delete(*batch)
                logger.debug(f"Deleted batch of {len(batch)} keys")
            
            logger.info(f"Cleared {len(keys)} vSphere cache entries from Redis")
            return True
        else:
            logger.info("No vSphere cache entries found to clear")
            return True
    except Exception as e:
        logger.error(f"Error clearing Redis cache: {str(e)}")
        return False

# Performance tracking decorator
def timeit(func):
    """Decorator to time function execution and log performance."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed_time = time.time() - start_time
        logger.debug(f"{func.__name__} took {elapsed_time:.2f} seconds")
        
        # Store performance metrics in Redis for monitoring
        try:
            r = get_redis_connection()
            if r:
                # Build a key based on the function name
                perf_key = f"{CACHE_PREFIX}perf:{func.__name__}"
                
                # Store as a sorted set with time as score
                r.zadd(perf_key, {datetime.now().isoformat(): elapsed_time})
                
                # Keep only the last 100 measurements
                r.zremrangebyrank(perf_key, 0, -101)
                
                # Set expiration
                r.expire(perf_key, 86400)  # 24 hours
        except Exception:
            # Don't let Redis errors affect the function execution
            pass
            
        return result
    return wrapper

# Background Template Loader
class TemplateLoader:
    """Handles loading VM templates in the background to avoid timeouts."""
    
    def __init__(self):
        """Initialize the template loader."""
        self.queue = queue.Queue()
        self.worker = None
        self.lock = threading.RLock()
        self.running = True
        
        # Start worker thread
        self.worker = threading.Thread(target=self._worker_thread, daemon=True)
        self.worker.start()
        
        logger.info("Template loader initialized")
    
    def start_loading_templates(self, cluster_id, cluster_obj, instance, creds_hash):
        """Queue a template loading task for a cluster."""
        self.queue.put((cluster_id, cluster_obj, instance, creds_hash))
        logger.debug(f"Queued template loading for cluster {cluster_id}")
    
    def _worker_thread(self):
        """Worker thread that processes template loading tasks."""
        while self.running:
            try:
                # Get a task from the queue with a timeout
                task = self.queue.get(timeout=1.0)
                
                # Process the task
                cluster_id, cluster_obj, instance, creds_hash = task
                
                try:
                    logger.info(f"Background loading templates for cluster {cluster_id}")
                    start_time = time.time()
                    
                    # Get templates
                    templates = instance.get_templates_by_cluster(cluster_obj)
                    
                    # Cache the templates
                    cache_cluster_resources(cluster_id, 'templates', templates, creds_hash)
                    
                    elapsed_time = time.time() - start_time
                    logger.info(f"Background loaded {len(templates)} templates for cluster {cluster_id} in {elapsed_time:.2f}s")
                    
                    # Disconnect from vSphere when done with this task
                    instance.disconnect()
                    
                except Exception as e:
                    logger.error(f"Error in background template loading for cluster {cluster_id}: {str(e)}")
                    # Still try to disconnect
                    try:
                        instance.disconnect()
                    except Exception:
                        pass
                
                # Mark task as done
                self.queue.task_done()
                
            except queue.Empty:
                # No tasks, continue waiting
                continue
            except Exception as e:
                logger.exception(f"Unexpected error in template loader worker: {str(e)}")
    
    def shutdown(self):
        """Shutdown the template loader."""
        self.running = False
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2.0)
            logger.info("Template loader shut down")

# Create template loader singleton
template_loader = TemplateLoader()

# Register shutdown handler
import atexit
def shutdown():
    """Shutdown the module cleanly."""
    # Shutdown template loader
    template_loader.shutdown()
    
    # Close Redis connection pool
    global _redis_pool
    if _redis_pool:
        _redis_pool.disconnect()
        _redis_pool = None

atexit.register(shutdown)

# Initialize Redis connection on module import
if not test_redis_connection():
    logger.warning("Redis connection failed during module initialization. "
                  "Will retry during operations.")
else:
    logger.info("Redis connection successful during module initialization.")
