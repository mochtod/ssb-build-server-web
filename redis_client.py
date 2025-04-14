#!/usr/bin/env python3
"""
Redis Client Module

This module provides a centralized Redis client that can be imported
by other modules to ensure consistent Redis access across the application.
"""
import os
import redis
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis connection settings from environment variables
REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)

# Initialize Redis client
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=False  # Keep binary responses for compatibility
    )
    logger.info(f"Redis client initialized: {REDIS_HOST}:{REDIS_PORT}")
    
    # Test connection
    redis_client.ping()
    logger.info("Redis connection test successful")
except Exception as e:
    logger.error(f"Error initializing Redis client: {str(e)}")
    # Create a dummy client that logs errors instead of failing
    class DummyRedisClient:
        def __getattr__(self, name):
            def method(*args, **kwargs):
                logger.error(f"Redis operation '{name}' failed: Redis client not initialized")
                return None
            return method
    
    redis_client = DummyRedisClient()
    logger.warning("Using dummy Redis client due to connection error")

# Export the client
__all__ = ['redis_client']