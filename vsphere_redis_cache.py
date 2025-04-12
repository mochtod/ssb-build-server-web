#!/usr/bin/env python3
"""
vSphere Redis Cache Module

This module provides Redis-based caching for vSphere resources to improve
performance and reduce load on the vSphere server. It implements:

1. Redis connection management
2. Resource caching for different resource types
3. Cache invalidation and expiration
4. Background template loading to avoid timeouts
5. Performance measurement decorators
"""

import os
import logging
import time
import json
import hashlib
import functools
import threading
import queue
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

# Redis connection pool
_redis_pool = None

def get_redis_connection():
    """Get a Redis connection from the pool."""
    global _redis_pool
    
    if _redis_pool is None:
        try:
            # Create connection pool
            _redis_pool = redis.ConnectionPool(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,  # Automatically decode responses to Python objects
                socket_timeout=5.0,      # Timeout after 5 seconds
                socket_connect_timeout=5.0,
                health_check_interval=30,
                retry_on_timeout=True
            )
            logger.info(f"Redis connection pool created for {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            logger.error(f"Error creating Redis connection pool: {str(e)}")
            return None
    
    try:
        # Get connection from pool
        return redis.Redis(connection_pool=_redis_pool)
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

def cache_cluster_resources(cluster_id, resource_type, resources, creds_hash):
    """Cache resources for a specific cluster and resource type."""
    if not cluster_id or not resource_type or resources is None:
        return False
    
    try:
        r = get_redis_connection()
        if r is None:
            return False
        
        # Generate cache key
        cache_key = get_cache_key(resource_type, cluster_id, creds_hash)
        
        # Serialize resources to JSON
        json_data = json.dumps(resources)
        
        # Store with expiration
        result = r.set(cache_key, json_data, ex=CACHE_TTL)
        
        if result:
            logger.debug(f"Cached {len(resources)} {resource_type} for cluster {cluster_id}")
            
            # Update index of cluster IDs with cached resources
            index_key = f"{CACHE_PREFIX}{creds_hash}:clusters_with_{resource_type}"
            r.sadd(index_key, cluster_id)
            r.expire(index_key, CACHE_TTL)
            
            # Update timestamp index
            ts_key = f"{CACHE_PREFIX}{creds_hash}:last_update:{resource_type}:{cluster_id}"
            r.set(ts_key, datetime.now().isoformat(), ex=CACHE_TTL)
        
        return result
    except Exception as e:
        logger.error(f"Error caching {resource_type} for cluster {cluster_id}: {str(e)}")
        return False

def get_cached_cluster_resources(cluster_id, resource_type, creds_hash):
    """Get cached resources for a specific cluster and resource type."""
    if not cluster_id or not resource_type:
        return None
    
    try:
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
        
        # If no credentials hash provided, invalidate for all credentials
        if creds_hash is None:
            # Find all creds hashes with this cluster
            pattern = f"{CACHE_PREFIX}*:*:{cluster_id}"
            keys = r.keys(pattern)
            
            # Delete all keys
            if keys:
                r.delete(*keys)
                logger.info(f"Invalidated all caches for cluster {cluster_id}")
            return True
        
        # Delete all resource type caches for this cluster
        deleted = 0
        for resource_type in RESOURCE_TYPES:
            cache_key = get_cache_key(resource_type, cluster_id, creds_hash)
            if r.delete(cache_key):
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
            'resource_types': {}
        }
        
        # Get all keys
        pattern = f"{CACHE_PREFIX}*" if creds_hash is None else f"{CACHE_PREFIX}{creds_hash}:*"
        all_keys = r.keys(pattern)
        stats['total_keys'] = len(all_keys)
        
        # Count by resource type
        for resource_type in RESOURCE_TYPES:
            type_pattern = f"{CACHE_PREFIX}*:{resource_type}:*"
            type_keys = r.keys(type_pattern)
            stats['resource_types'][resource_type] = len(type_keys)
        
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
                stats['clusters'][resource_type] = len(cluster_keys)
        
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
            r.delete(*keys)
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
