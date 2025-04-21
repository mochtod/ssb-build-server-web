import os
import json
import redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Redis configuration with default values
REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')  # Default to 'redis' service name in docker-compose
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)
REDIS_CACHE_TTL = int(os.environ.get('REDIS_CACHE_TTL', 3600))  # Default TTL: 1 hour

class RedisClient:
    """
    Redis client for managing connections and operations with Redis
    """
    _instance = None

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
        Initialize Redis connection
        """
        self.client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True  # Automatically decode responses to strings
        )
        self.ttl = REDIS_CACHE_TTL

    def get(self, key):
        """
        Get value from Redis
        """
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            print(f"Redis get error: {str(e)}")
            return None

    def set(self, key, value, ttl=None):
        """
        Set value in Redis with optional TTL
        """
        try:
            self.client.set(key, json.dumps(value), ex=(ttl or self.ttl))
            return True
        except Exception as e:
            print(f"Redis set error: {str(e)}")
            return False

    def delete(self, key):
        """
        Delete value from Redis
        """
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            print(f"Redis delete error: {str(e)}")
            return False

    def exists(self, key):
        """
        Check if key exists in Redis
        """
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            print(f"Redis exists error: {str(e)}")
            return False

    def flush_db(self):
        """
        Clear all keys in the current database
        """
        try:
            self.client.flushdb()
            return True
        except Exception as e:
            print(f"Redis flush error: {str(e)}")
            return False

    def keys_pattern(self, pattern):
        """
        Get all keys matching pattern
        """
        try:
            return self.client.keys(pattern)
        except Exception as e:
            print(f"Redis keys pattern error: {str(e)}")
            return []

    def ping(self):
        """
        Check if Redis is available
        """
        try:
            return self.client.ping()
        except Exception as e:
            print(f"Redis ping error: {str(e)}")
            return False

    def get_ttl(self, key):
        """
        Get the TTL of a key
        """
        try:
            return self.client.ttl(key)
        except Exception as e:
            print(f"Redis TTL error: {str(e)}")
            return -2  # -2 means key does not exist