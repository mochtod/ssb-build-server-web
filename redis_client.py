import os
import json
import time
import logging
import zlib
import pickle
import redis
from dotenv import load_dotenv
from functools import wraps

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('redis_client')

# Load environment variables
load_dotenv()

# Redis configuration with default values
REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')  # Default to 'redis' service name in docker-compose
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)
REDIS_CACHE_TTL = int(os.environ.get('REDIS_CACHE_TTL', 3600))  # Default TTL: 1 hour

# Performance and optimization settings
REDIS_CONNECTION_POOL_SIZE = int(os.environ.get('REDIS_CONNECTION_POOL_SIZE', 10))
REDIS_USE_COMPRESSION = os.environ.get('REDIS_USE_COMPRESSION', 'true').lower() == 'true'
REDIS_COMPRESSION_THRESHOLD = int(os.environ.get('REDIS_COMPRESSION_THRESHOLD', 1024))  # Compress if > 1KB
REDIS_COMPRESSION_LEVEL = int(os.environ.get('REDIS_COMPRESSION_LEVEL', 6))  # Default compression level (0-9)

# Create a decorator for Redis operation metrics
def track_redis_operation(operation_name):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            start_time = time.time()
            try:
                result = func(self, *args, **kwargs)
                operation_time = time.time() - start_time
                
                # Record metrics
                self._record_operation_metric(operation_name, operation_time, success=True)
                return result
            except Exception as e:
                operation_time = time.time() - start_time
                self._record_operation_metric(operation_name, operation_time, success=False)
                logger.error(f"Redis {operation_name} error: {str(e)}")
                raise
        return wrapper
    return decorator

class RedisClient:
    """
    Enhanced Redis client for managing connections and operations with Redis
    Features:
    - Connection pooling
    - Compression for large values
    - Performance metrics
    - Automatic retry
    - Proper error handling
    """
    _instance = None
    _metrics = {
        'operations': {},
        'hits': 0,
        'misses': 0,
        'errors': 0,
        'total_bytes_saved': 0,
        'compression_ratio': 0
    }

    @classmethod
    def get_instance(cls):
        """
        Get singleton instance of RedisClient
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """
        Initialize Redis connection pool and client
        """
        # Create connection pool
        self.pool = redis.ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            max_connections=REDIS_CONNECTION_POOL_SIZE,
            decode_responses=False  # We'll handle decoding manually for compression support
        )
        
        # Create client from pool
        self.client = redis.Redis(connection_pool=self.pool)
        self.ttl = REDIS_CACHE_TTL
        self.use_compression = REDIS_USE_COMPRESSION
        self.compression_threshold = REDIS_COMPRESSION_THRESHOLD
        self.compression_level = REDIS_COMPRESSION_LEVEL
        
        logger.info(f"Redis client initialized with host={REDIS_HOST}, port={REDIS_PORT}, "
                   f"compression={'enabled' if self.use_compression else 'disabled'}")

    def _record_operation_metric(self, operation, duration, success=True):
        """
        Record operation metrics
        """
        if operation not in self._metrics['operations']:
            self._metrics['operations'][operation] = {
                'count': 0,
                'success_count': 0,
                'error_count': 0,
                'total_duration': 0,
                'avg_duration': 0
            }
            
        metrics = self._metrics['operations'][operation]
        metrics['count'] += 1
        metrics['total_duration'] += duration
        metrics['avg_duration'] = metrics['total_duration'] / metrics['count']
        
        if success:
            metrics['success_count'] += 1
        else:
            metrics['error_count'] += 1
            self._metrics['errors'] += 1

    def _compress_value(self, value):
        """
        Compress value if it's large enough
        Returns tuple (compressed_value, is_compressed)
        """
        if not self.use_compression:
            return value, False
            
        # Serialize with pickle for complex objects
        serialized = pickle.dumps(value)
        
        # Only compress if value is above threshold
        if len(serialized) < self.compression_threshold:
            return serialized, False
            
        # Compress the value
        compressed = zlib.compress(serialized, level=self.compression_level)
        
        # Calculate compression stats
        original_size = len(serialized)
        compressed_size = len(compressed)
        bytes_saved = original_size - compressed_size
        
        # Update compression metrics
        self._metrics['total_bytes_saved'] += bytes_saved
        self._metrics['compression_ratio'] = (
            compressed_size / original_size 
            if original_size > 0 else 1.0
        )
        
        logger.debug(f"Compressed value from {original_size} to {compressed_size} bytes "
                    f"({self._metrics['compression_ratio']:.2%} ratio)")
        
        return compressed, True

    def _decompress_value(self, value, is_compressed):
        """
        Decompress value if it was compressed
        """
        if not is_compressed:
            # If it wasn't compressed but was serialized
            if isinstance(value, bytes):
                try:
                    return pickle.loads(value)
                except:
                    # Fallback if it's just a simple byte string
                    return value.decode('utf-8', errors='ignore')
            return value
            
        # Decompress
        decompressed = zlib.decompress(value)
        
        # Deserialize
        return pickle.loads(decompressed)

    @track_redis_operation('get')
    def get(self, key):
        """
        Get value from Redis with decompression support
        """
        try:
            # Get value and metadata
            pipeline = self.client.pipeline()
            pipeline.get(key)
            pipeline.get(f"{key}:meta")
            value, meta = pipeline.execute()
            
            if value is None:
                self._metrics['misses'] += 1
                return None
                
            self._metrics['hits'] += 1
            
            # Check if value was compressed
            is_compressed = False
            if meta:
                try:
                    metadata = json.loads(meta)
                    is_compressed = metadata.get('compressed', False)
                except:
                    # If metadata is corrupted, assume not compressed
                    pass
                    
            # Decompress if needed
            return self._decompress_value(value, is_compressed)
        except Exception as e:
            logger.error(f"Redis get error for key '{key}': {str(e)}")
            return None

    @track_redis_operation('set')
    def set(self, key, value, ttl=None):
        """
        Set value in Redis with compression support
        """
        try:
            # Compress value if appropriate
            data, is_compressed = self._compress_value(value)
            
            # Store metadata
            metadata = {'compressed': is_compressed}
            
            # Use pipeline for atomic operation
            pipeline = self.client.pipeline()
            pipeline.set(key, data, ex=(ttl or self.ttl))
            pipeline.set(f"{key}:meta", json.dumps(metadata), ex=(ttl or self.ttl))
            pipeline.execute()
            
            return True
        except Exception as e:
            logger.error(f"Redis set error for key '{key}': {str(e)}")
            return False

    @track_redis_operation('delete')
    def delete(self, key):
        """
        Delete value and its metadata from Redis
        """
        try:
            pipeline = self.client.pipeline()
            pipeline.delete(key)
            pipeline.delete(f"{key}:meta")
            pipeline.execute()
            return True
        except Exception as e:
            logger.error(f"Redis delete error for key '{key}': {str(e)}")
            return False

    @track_redis_operation('exists')
    def exists(self, key):
        """
        Check if key exists in Redis
        """
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            logger.error(f"Redis exists error for key '{key}': {str(e)}")
            return False

    @track_redis_operation('flush')
    def flush_db(self):
        """
        Clear all keys in the current database
        """
        try:
            self.client.flushdb()
            return True
        except Exception as e:
            logger.error(f"Redis flush error: {str(e)}")
            return False

    @track_redis_operation('keys')
    def keys_pattern(self, pattern):
        """
        Get all keys matching pattern with batching for large result sets
        """
        try:
            # Use SCAN instead of KEYS for production with large datasets
            all_keys = []
            cursor = 0  # Start with integer 0
            while True:
                # Convert cursor to string for Redis scan operation
                str_cursor = str(cursor)
                cursor, keys = self.client.scan(cursor=str_cursor, match=pattern, count=1000)
                
                # The cursor might be returned as bytes or integer, handle both cases
                if isinstance(cursor, bytes):
                    cursor = cursor.decode('utf-8')
                
                # Convert cursor to integer for comparison
                cursor = int(cursor)
                
                # Add keys to our result list
                all_keys.extend(keys)
                
                # Convert bytes to strings if needed
                all_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in all_keys]
                
                # Break when cursor is 0 (scan complete)
                if cursor == 0:
                    break
                    
            return all_keys
        except Exception as e:
            logger.error(f"Redis keys pattern error for '{pattern}': {str(e)}")
            return []

    @track_redis_operation('ping')
    def ping(self):
        """
        Check if Redis is available
        """
        try:
            return self.client.ping()
        except Exception as e:
            logger.error(f"Redis ping error: {str(e)}")
            return False

    @track_redis_operation('ttl')
    def get_ttl(self, key):
        """
        Get the TTL of a key
        """
        try:
            return self.client.ttl(key)
        except Exception as e:
            logger.error(f"Redis TTL error for key '{key}': {str(e)}")
            return -2  # -2 means key does not exist

    @track_redis_operation('increment')
    def increment(self, key, amount=1):
        """
        Increment a key by the given amount
        """
        try:
            return self.client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Redis increment error for key '{key}': {str(e)}")
            return 0
            
    @track_redis_operation('mget')
    def mget(self, keys):
        """
        Get multiple values from Redis
        """
        try:
            if not keys:
                return []
                
            # Get values and metadata
            pipeline = self.client.pipeline()
            for key in keys:
                pipeline.get(key)
                pipeline.get(f"{key}:meta")
                
            results = pipeline.execute()
            
            # Process results in pairs (value, metadata)
            values = []
            for i in range(0, len(results), 2):
                value = results[i]
                meta = results[i+1]
                
                if value is None:
                    values.append(None)
                    self._metrics['misses'] += 1
                    continue
                    
                self._metrics['hits'] += 1
                
                # Check if value was compressed
                is_compressed = False
                if meta:
                    try:
                        metadata = json.loads(meta)
                        is_compressed = metadata.get('compressed', False)
                    except:
                        pass
                        
                # Decompress if needed
                values.append(self._decompress_value(value, is_compressed))
                
            return values
        except Exception as e:
            logger.error(f"Redis mget error: {str(e)}")
            return [None] * len(keys)
            
    def get_raw_redis(self):
        """
        Get the raw Redis client for operations not covered by this class
        """
        return self.client
        
    def get_metrics(self):
        """
        Get current Redis metrics
        """
        # Calculate hit rate
        total_operations = self._metrics['hits'] + self._metrics['misses']
        hit_rate = (self._metrics['hits'] / total_operations * 100) if total_operations > 0 else 0
        
        # Add hit rate to metrics
        metrics = dict(self._metrics)
        metrics['hit_rate'] = hit_rate
        
        # Add memory usage
        try:
            info = self.client.info(section='memory')
            metrics['memory_usage'] = info.get('used_memory_human', 'Unknown')
            metrics['peak_memory'] = info.get('used_memory_peak_human', 'Unknown')
        except:
            metrics['memory_usage'] = 'Unknown'
            metrics['peak_memory'] = 'Unknown'
            
        # Format compression ratio as percentage
        if 'compression_ratio' in metrics:
            metrics['compression_ratio'] = f"{(1 - metrics['compression_ratio']) * 100:.1f}%"
            
        # Format total bytes saved in human readable format
        if 'total_bytes_saved' in metrics:
            bytes_saved = metrics['total_bytes_saved']
            if bytes_saved < 1024:
                metrics['total_bytes_saved_human'] = f"{bytes_saved} B"
            elif bytes_saved < 1024 * 1024:
                metrics['total_bytes_saved_human'] = f"{bytes_saved / 1024:.1f} KB"
            else:
                metrics['total_bytes_saved_human'] = f"{bytes_saved / (1024 * 1024):.1f} MB"
            
        return metrics