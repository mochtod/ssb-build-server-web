#!/usr/bin/env python
"""
Quick test for Redis connection
"""
from redis_client import RedisClient
import os

print("=== Redis Connection Test ===")
print(f"REDIS_HOST environment variable: {os.environ.get('REDIS_HOST', 'not set')}")
print(f"REDIS_PORT environment variable: {os.environ.get('REDIS_PORT', 'not set')}")

# Initialize client
client = RedisClient.get_instance()

# Test connection
connected = client.ping()
print(f"Redis connection test: {'SUCCESS' if connected else 'FAILED'}")

# Get connection details
status = client.get_connection_status()
print(f"Connection status: {status}")

# Try a simple set operation
if connected:
    set_result = client.set('test_key', 'test_value')
    print(f"Set test key: {'SUCCESS' if set_result else 'FAILED'}")
    
    get_result = client.get('test_key')
    print(f"Get test key: {'SUCCESS' if get_result == 'test_value' else 'FAILED'}, value: {get_result}")