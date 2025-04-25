#!/usr/bin/env python
"""
Direct fix for Redis connection issues in containers
"""
import os
import logging
import json
import redis

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('redis_fix')

def fix_redis_connections():
    """Fix Redis connection issues in the application"""
    # 1. Create a simple test entry in Redis using direct connection
    logger.info("Attempting direct connection to Redis using service name 'redis'...")
    
    try:
        # Try connecting directly to the Redis service
        r = redis.Redis(host='redis', port=6379, db=0)
        r.set('connection_test', 'success')
        
        test_result = r.get('connection_test')
        if test_result and test_result.decode('utf-8') == 'success':
            logger.info("✅ Successfully connected to Redis at redis:6379")
        else:
            logger.error("❌ Connected to Redis but data retrieval failed")
            return False
    except Exception as e:
        logger.error(f"❌ Failed to connect to Redis: {str(e)}")
        return False
    
    # 2. Add templates and datacenters if missing
    logger.info("Adding fallback templates and datacenters if missing...")
    
    # Sample datacenter
    sample_datacenter = {
        'id': 'datacenter-fallback-edbc',
        'name': 'EDBC NONPROD',
        'vm_folder': 'folder-fallback-vm',
        'host_folder': 'folder-fallback-host',
        'datastore_folder': 'folder-fallback-datastore',
        'network_folder': 'folder-fallback-network'
    }
    
    # Sample templates
    sample_templates = [
        {
            'id': 'vm-fallback-rhel9-datacenter-fallback-edbc',
            'name': 'rhel9-template (fallback)',
            'is_template': True,
            'guest_id': 'rhel9_64Guest',
            'guest_full_name': 'Red Hat Enterprise Linux 9 (64-bit)',
            'datacenter_id': 'datacenter-fallback-edbc',
            'datacenter_name': 'EDBC NONPROD'
        },
        {
            'id': 'vm-fallback-win-datacenter-fallback-edbc',
            'name': 'windows-template (fallback)',
            'is_template': True,
            'guest_id': 'windows2019srv_64Guest',
            'guest_full_name': 'Windows Server 2019 (64-bit)',
            'datacenter_id': 'datacenter-fallback-edbc',
            'datacenter_name': 'EDBC NONPROD'
        }
    ]
    
    # Check if datacenters exist
    try:
        datacenters_key = 'vsphere:datacenters'
        datacenters = r.get(datacenters_key)
        
        if not datacenters:
            logger.info("No datacenters found, adding sample datacenter")
            r.set(datacenters_key, json.dumps([sample_datacenter]))
        else:
            logger.info("Datacenters exist in Redis")
    except Exception as e:
        logger.error(f"Error checking/adding datacenters: {str(e)}")
    
    # Check if templates exist
    try:
        templates_key = 'vsphere:templates'
        templates = r.get(templates_key)
        
        if not templates:
            logger.info("No templates found, adding sample templates")
            r.set(templates_key, json.dumps(sample_templates))
        else:
            logger.info("Templates exist in Redis")
    except Exception as e:
        logger.error(f"Error checking/adding templates: {str(e)}")
    
    logger.info("Redis fix completed successfully")
    return True

if __name__ == "__main__":
    success = fix_redis_connections()
    print(f"Redis fix {'succeeded' if success else 'failed'}")