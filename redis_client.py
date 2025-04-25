import os
import json
import time
import logging
import zlib
import pickle
import redis
from dotenv import load_dotenv
from functools import wraps
import socket

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('redis_client')

# Load environment variables
load_dotenv()

# Redis configuration with better defaults and connection options
REDIS_HOSTS = [
    os.environ.get('REDIS_HOST', 'redis'),  # First try using the service name in Docker
    'localhost',                            # Then try localhost
    '127.0.0.1'                             # Finally try explicit IP
]
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))

# Handle empty string password properly
password = os.environ.get('REDIS_PASSWORD', None)
REDIS_PASSWORD = password if password and password.strip() else None

REDIS_CACHE_TTL = int(os.environ.get('REDIS_CACHE_TTL', 3600))  # Default TTL: 1 hour
REDIS_CONNECT_TIMEOUT = int(os.environ.get('REDIS_CONNECT_TIMEOUT', 5))  # 5 second connection timeout

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
    Redis Client Singleton for consistent Redis connections across the application
    Uses a connection pool to efficiently manage connections
    """
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """
        Get the singleton instance of RedisClient
        """
        if cls._instance is None:
            cls._instance = RedisClient()
        return cls._instance
    
    def __init__(self):
        """
        Initialize Redis connection with automatic reconnection
        """
        # Only initialize once (singleton pattern)
        if RedisClient._instance is not None:
            return
            
        # Configure from environment
        self.host = os.environ.get('REDIS_HOST', 'redis')  # Use 'redis' as default for docker-compose
        self.port = int(os.environ.get('REDIS_PORT', 6379))
        
        # Handle empty string password properly
        password = os.environ.get('REDIS_PASSWORD', None)
        self.password = password if password and password.strip() else None
        
        self.db = int(os.environ.get('REDIS_DB', 0))
        self.use_compression = os.environ.get('REDIS_USE_COMPRESSION', 'false').lower() == 'true'
        self.max_retries = int(os.environ.get('REDIS_MAX_RETRIES', 3))
        self.retry_delay = int(os.environ.get('REDIS_RETRY_DELAY', 1))  # seconds
        self.socket_timeout = int(os.environ.get('REDIS_SOCKET_TIMEOUT', 5))  # seconds
        
        # Maximum size for non-compressed storage (1MB default)
        self.max_size_without_compression = int(os.environ.get('REDIS_MAX_SIZE_WITHOUT_COMPRESSION', 1024 * 1024))
        
        # Configure connection pool size
        self.pool_size = int(os.environ.get('REDIS_CONNECTION_POOL_SIZE', 10))
        
        # Initialize connection
        self._redis = None
        self._connect()
        
        logger.info(f"Redis client initialized with host: {self.host}, port: {self.port}, compression: {self.use_compression}")
    
    def _connect(self):
        """
        Connect to Redis with retry logic and connection pooling
        """
        # Try multiple Redis hosts in order
        for current_host in REDIS_HOSTS:
            logger.info(f"Attempting to connect to Redis at {current_host}:{self.port}")
            
            for attempt in range(1, self.max_retries + 1):
                try:
                    # Create connection pool for better performance with concurrent operations
                    pool_args = {
                        "host": current_host,
                        "port": self.port,
                        "db": self.db,
                        "socket_timeout": self.socket_timeout,
                        "socket_keepalive": True,
                        "max_connections": self.pool_size,
                        "retry_on_timeout": True,
                        "health_check_interval": 30
                    }
                    
                    # Only include password if it's actually provided and not empty
                    if self.password and self.password.strip():
                        pool_args["password"] = self.password
                    
                    # Create the connection pool
                    pool = redis.ConnectionPool(**pool_args)
                    self._redis = redis.Redis(connection_pool=pool)
                    
                    # Test connection with ping
                    self._redis.ping()
                    logger.info(f"Successfully connected to Redis at {current_host}:{self.port}")
                    self.host = current_host  # Update the host to the one that worked
                    return True
                
                except redis.exceptions.AuthenticationError as e:
                    logger.error(f"Redis authentication error for {current_host}:{self.port}: {str(e)}")
                    # No point retrying the same host with the same credentials
                    break  # Try next host
                    
                except redis.exceptions.ConnectionError as e:
                    if attempt < self.max_retries:
                        logger.warning(f"Redis connection attempt {attempt}/{self.max_retries} to {current_host}:{self.port} failed: {str(e)}. Retrying in {self.retry_delay} seconds...")
                        time.sleep(self.retry_delay)
                    else:
                        logger.error(f"Failed to connect to Redis at {current_host}:{self.port} after {self.max_retries} attempts: {str(e)}")
                        # Try next host rather than failing immediately
                        break
                        
                except Exception as e:
                    # Handle "DENIED" errors in a more robust way
                    error_str = str(e).upper()
                    if "DENIED" in error_str or "AUTHENTICATION" in error_str:
                        logger.error(f"Redis authentication denied for {current_host}:{self.port}")
                        break  # Try next host
                    
                    # Log the full error for debugging
                    logger.error(f"Unexpected error connecting to Redis at {current_host}:{self.port}: {str(e)}", exc_info=True)
                    
                    if attempt < self.max_retries:
                        logger.warning(f"Retrying in {self.retry_delay} seconds (attempt {attempt}/{self.max_retries})...")
                        time.sleep(self.retry_delay)
                    else:
                        break  # Try next host
        
        # If we reach here, all hosts failed
        logger.error(f"Failed to connect to any Redis server after trying {', '.join(REDIS_HOSTS)}")
        self._redis = None
        return False
    
    def get_raw_redis(self):
        """
        Get the raw Redis client for direct access
        """
        if self._redis is None:
            self._connect()  # Try to reconnect
        return self._redis
    
    def _ensure_connection(self):
        """
        Ensure Redis connection is available
        """
        if self._redis is None:
            return self._connect()
        
        # Check if connection is still working
        try:
            self._redis.ping()
            return True
        except:
            # Try to reconnect
            return self._connect()
    
    @track_redis_operation('set')
    def set(self, key, value, expiration=None):
        """
        Set a value in Redis with automatic compression for large values
        """
        try:
            if not self._ensure_connection():
                logger.error(f"Redis connection unavailable for setting key: {key}")
                return False
                
            # Convert to JSON if not a string
            if not isinstance(value, str):
                value = json.dumps(value)
                
            # Check size and compress if needed
            if self.use_compression and len(value) > self.max_size_without_compression:
                compressed_value = zlib.compress(value.encode())
                # Store with compression flag
                self._redis.set(f"{key}:compressed", 1)
                self._redis.set(key, compressed_value, ex=expiration)
                logger.debug(f"Stored compressed value for key: {key}, original size: {len(value)}, compressed size: {len(compressed_value)}")
            else:
                # Store without compression
                if self._redis.exists(f"{key}:compressed"):
                    self._redis.delete(f"{key}:compressed")
                self._redis.set(key, value, ex=expiration)
                
            return True
        except Exception as e:
            logger.error(f"Redis set error for key '{key}': {str(e)}")
            return False
    
    @track_redis_operation('get')
    def get(self, key):
        """
        Get a value from Redis with automatic decompression
        """
        try:
            if not self._ensure_connection():
                logger.error(f"Redis connection unavailable for getting key: {key}")
                return None
                
            # Check if value exists
            if not self._redis.exists(key):
                return None
                
            # Check if value is compressed
            is_compressed = self._redis.exists(f"{key}:compressed")
            
            # Get raw value
            value = self._redis.get(key)
            
            if value is None:
                return None
                
            # Handle compressed values
            if is_compressed:
                try:
                    value = zlib.decompress(value)
                    value = value.decode()
                except Exception as decompress_err:
                    logger.error(f"Error decompressing value for key '{key}': {str(decompress_err)}")
                    return None
            else:
                # Decode bytes to string if not compressed
                value = value.decode() if isinstance(value, bytes) else value
            
            # Try to parse as JSON
            try:
                return json.loads(value)
            except:
                # Return as is if not JSON
                return value
        except Exception as e:
            logger.error(f"Redis get error for key '{key}': {str(e)}")
            return None
    
    @track_redis_operation('delete')
    def delete(self, key):
        """
        Delete a key from Redis
        """
        try:
            if not self._ensure_connection():
                logger.error(f"Redis connection unavailable for deleting key: {key}")
                return False
                
            # Delete both the key and its compression flag if exists
            self._redis.delete(key)
            self._redis.delete(f"{key}:compressed")
            return True
        except Exception as e:
            logger.error(f"Redis delete error for key '{key}': {str(e)}")
            return False
    
    @track_redis_operation('exists')
    def exists(self, key):
        """
        Check if a key exists in Redis
        """
        try:
            if not self._ensure_connection():
                logger.error(f"Redis connection unavailable for checking key: {key}")
                return False
                
            return bool(self._redis.exists(key))
        except Exception as e:
            logger.error(f"Redis exists error for key '{key}': {str(e)}")
            return False
    
    @track_redis_operation('ping')
    def ping(self):
        """
        Ping Redis to test connection
        """
        try:
            if not self._ensure_connection():
                return False
                
            return bool(self._redis.ping())
        except Exception as e:
            logger.error(f"Redis ping error: {str(e)}")
            return False
    
    @track_redis_operation('ttl')
    def get_ttl(self, key):
        """
        Get TTL (time to live) for a key
        """
        try:
            if not self._ensure_connection():
                logger.error(f"Redis connection unavailable for getting TTL of key: {key}")
                return None
                
            return self._redis.ttl(key)
        except Exception as e:
            logger.error(f"Redis get_ttl error for key '{key}': {str(e)}")
            return None
    
    @track_redis_operation('increment')
    def increment(self, key):
        """
        Increment an integer value in Redis
        """
        try:
            if not self._ensure_connection():
                logger.error(f"Redis connection unavailable for incrementing key: {key}")
                return None
                
            return self._redis.incr(key)
        except Exception as e:
            logger.error(f"Redis increment error for key '{key}': {str(e)}")
            return None
    
    @track_redis_operation('keys')
    def keys_pattern(self, pattern):
        """
        Get all keys matching a pattern
        """
        try:
            if not self._ensure_connection():
                logger.error(f"Redis connection unavailable for getting keys with pattern: {pattern}")
                return []
                
            keys = self._redis.keys(pattern)
            return [k.decode() if isinstance(k, bytes) else k for k in keys]
        except Exception as e:
            logger.error(f"Redis keys_pattern error for pattern '{pattern}': {str(e)}")
            return []
    
    def get_info(self):
        """
        Get Redis server info
        """
        try:
            if not self._ensure_connection():
                logger.error("Redis connection unavailable for getting server info")
                return {}
                
            info = self._redis.info()
            return info
        except Exception as e:
            logger.error(f"Redis get_info error: {str(e)}")
            return {}

    # Performance monitoring metrics
    def _record_operation_metric(self, operation_name, operation_time, success=True):
        """
        Record metrics for Redis operations
        """
        try:
            # Store success/failure metrics
            metric_key = f"redis:metrics:{operation_name}"
            success_key = f"{metric_key}:success" if success else f"{metric_key}:failure"
            
            # Increment operation count
            self._redis.incr(success_key) if self._redis else None
            
            # Track timing in a list with max 100 entries (for average calculation)
            timing_key = f"{metric_key}:timing"
            
            if self._redis:
                # Add timing to a list
                self._redis.lpush(timing_key, operation_time)
                # Keep list at a reasonable size
                self._redis.ltrim(timing_key, 0, 99)
        except Exception as e:
            # Just log error but don't fail the calling operation
            logger.debug(f"Error recording metrics for {operation_name}: {str(e)}")
            pass