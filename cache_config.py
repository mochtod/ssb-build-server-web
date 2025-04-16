"""
Cache Configuration Module

This module contains configuration settings for the caching system,
allowing for easy adjustment of cache behavior.
"""

# Base TTL values in seconds
CACHE_TTL = {
    # General inventory cache
    'vsphere_inventory': 7200,  # 2 hours
    
    # Resource-specific caches
    'datacenters': 86400,        # 24 hours (rarely change)
    'resource_pools': 14400,     # 4 hours
    'datastores': 7200,          # 2 hours
    'networks': 14400,           # 4 hours
    'templates': 86400,          # 24 hours (rarely change)
    
    # NetBox cache
    'netbox_ip_ranges': 7200,    # 2 hours
    
    # Cluster-specific resource caches
    'cluster_resources': 3600    # 1 hour
}

# Cache batch size for bulk operations
CACHE_BATCH_SIZE = 100

# Redis compression settings
COMPRESSION_ENABLED = True
COMPRESSION_LEVEL = 6  # 1-9, higher is more compression but slower
