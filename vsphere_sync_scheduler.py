import os
import time
import logging
import schedule
from vsphere_redis_cache import sync_vsphere_to_redis, VSphereRedisCache

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('vsphere_sync_scheduler')

# Sync interval in minutes (configurable via environment variable)
SYNC_INTERVAL_MINUTES = int(os.environ.get('VSPHERE_SYNC_INTERVAL_MINUTES', 15))

def run_sync():
    """Run vSphere to Redis synchronization"""
    logger.info(f"Starting scheduled vSphere to Redis sync...")
    try:
        success = sync_vsphere_to_redis()
        if success:
            logger.info("Scheduled vSphere sync completed successfully")
        else:
            logger.error("Scheduled vSphere sync failed")
    except Exception as e:
        logger.error(f"Error in scheduled vSphere sync: {str(e)}")

def get_cache_status():
    """Get the current cache status"""
    try:
        cache = VSphereRedisCache()
        status = cache.get_cache_status()
        return status
    except Exception as e:
        logger.error(f"Error getting cache status: {str(e)}")
        return None

def clear_cache():
    """Clear the vSphere cache"""
    try:
        cache = VSphereRedisCache()
        success = cache.clear_cache()
        if success:
            logger.info("vSphere cache cleared successfully")
        else:
            logger.error("Failed to clear vSphere cache")
        return success
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        return False

def main():
    """Run the scheduler"""
    logger.info(f"Starting vSphere sync scheduler. Sync interval: {SYNC_INTERVAL_MINUTES} minutes")
    
    # Run initial sync on startup
    run_sync()
    
    # Schedule regular syncs
    schedule.every(SYNC_INTERVAL_MINUTES).minutes.do(run_sync)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
    except Exception as e:
        logger.error(f"Scheduler error: {str(e)}")

if __name__ == "__main__":
    main()