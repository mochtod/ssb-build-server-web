#!/usr/bin/env python3
"""
vSphere Background Refresh Module

This module provides functionality to refresh vSphere resources in the background
without blocking the UI. It prioritizes Redis cache for immediate responses and
updates the cache with fresh data asynchronously.
"""

import os
import logging
import threading
import json
from datetime import datetime
import time

# Import vSphere modules
import vsphere_redis_cache
import vsphere_cluster_resources
from pyVmomi import vim

# Configure logging
logger = logging.getLogger(__name__)

def refresh_cluster_resources_background(cluster_id, cluster_name=None):
    """
    Refreshes cluster resources in the background and updates Redis cache.
    This never blocks the UI.
    
    Args:
        cluster_id (str): The ID of the cluster to refresh
        cluster_name (str, optional): The name of the cluster for logging
    """
    try:
        logger.info(f"Background refresh started for cluster: {cluster_name or cluster_id}")
        
        # Get a connection
        start_time = time.time()
        instance = vsphere_cluster_resources.get_instance()
        if not instance.connect():
            logger.error(f"Failed to connect to vSphere during background refresh for cluster {cluster_id}")
            return
        
        try:
            # Find the cluster object
            cluster_obj = None
            container = instance.content.viewManager.CreateContainerView(
                instance.content.rootFolder, [vim.ClusterComputeResource], True)
            
            for cluster in container.view:
                if str(cluster._moId) == cluster_id:
                    cluster_obj = cluster
                    break
            
            container.Destroy()
            
            if not cluster_obj:
                logger.warning(f"Could not find cluster object for ID {cluster_id}")
                return
                
            # Generate credentials hash for Redis cache
            creds_hash = vsphere_redis_cache.get_credentials_hash(
                os.environ.get('VSPHERE_SERVER'), 
                os.environ.get('VSPHERE_USER'),
                os.environ.get('VSPHERE_PASSWORD')
            )
            
            # Get and cache each resource type separately
            logger.info(f"Refreshing datastores for cluster: {cluster_name or cluster_id}")
            datastores = instance.get_datastores_by_cluster(cluster_obj)
            vsphere_redis_cache.cache_cluster_resources(cluster_id, 'datastores', datastores, creds_hash)
            
            logger.info(f"Refreshing networks for cluster: {cluster_name or cluster_id}")
            networks = instance.get_networks_by_cluster(cluster_obj)
            vsphere_redis_cache.cache_cluster_resources(cluster_id, 'networks', networks, creds_hash)
            
            logger.info(f"Refreshing resource pools for cluster: {cluster_name or cluster_id}")
            resource_pools = instance.get_resource_pools_by_cluster(cluster_obj)
            vsphere_redis_cache.cache_cluster_resources(cluster_id, 'resource_pools', resource_pools, creds_hash)
            
            # Templates are slow to load - use the template loader
            logger.info(f"Starting template refresh for cluster: {cluster_name or cluster_id}")
            vsphere_redis_cache.template_loader.start_loading_templates(
                cluster_id, cluster_obj, instance, creds_hash
            )
            
            elapsed_time = time.time() - start_time
            logger.info(f"Background refresh completed for cluster: {cluster_name or cluster_id} in {elapsed_time:.2f}s")
            
        finally:
            # Don't disconnect yet - template loader will do that
            pass
    except Exception as e:
        logger.exception(f"Error in background refresh for cluster {cluster_id}: {str(e)}")

def refresh_datacenter_clusters_background(datacenter_name):
    """
    Refreshes all clusters for a datacenter in the background and updates Redis cache.
    
    Args:
        datacenter_name (str): The name of the datacenter to refresh
    """
    try:
        logger.info(f"Background refresh started for datacenter: {datacenter_name}")
        
        # Connect to vSphere
        instance = vsphere_cluster_resources.get_instance()
        if not instance.connect():
            logger.error(f"Failed to connect to vSphere during background refresh for datacenter {datacenter_name}")
            return
        
        try:
            # Find the datacenter object
            datacenter = None
            for dc in instance.get_datacenter_list():
                if dc.name == datacenter_name:
                    datacenter = dc
                    break
            
            if not datacenter:
                logger.warning(f"Could not find datacenter with name {datacenter_name}")
                return
            
            # Get clusters for this datacenter
            clusters = instance.get_clusters(datacenter)
            
            # Generate credentials hash for Redis cache
            creds_hash = vsphere_redis_cache.get_credentials_hash(
                os.environ.get('VSPHERE_SERVER'), 
                os.environ.get('VSPHERE_USER'),
                os.environ.get('VSPHERE_PASSWORD')
            )
            
            # Cache the clusters list
            # Build a cache key for this datacenter's clusters
            dc_clusters_key = f"vsphere:{creds_hash}:datacenter:{datacenter_name}:clusters"
            r = vsphere_redis_cache.get_redis_connection()
            if r:
                try:
                    r.set(dc_clusters_key, json.dumps(clusters), ex=vsphere_redis_cache.CACHE_TTL)
                    logger.info(f"Cached {len(clusters)} clusters for datacenter {datacenter_name}")
                except Exception as cache_error:
                    logger.warning(f"Error caching clusters: {str(cache_error)}")
            
            logger.info(f"Background refresh completed for datacenter: {datacenter_name} with {len(clusters)} clusters")
            
        finally:
            # Disconnect when done
            instance.disconnect()
    except Exception as e:
        logger.exception(f"Error in background refresh for datacenter {datacenter_name}: {str(e)}")

def refresh_all_datacenters_background():
    """
    Refreshes all datacenters list in the background and updates Redis cache.
    """
    try:
        logger.info("Background refresh started for all datacenters")
        
        # Connect to vSphere
        instance = vsphere_cluster_resources.get_instance()
        if not instance.connect():
            logger.error("Failed to connect to vSphere during background refresh for datacenters")
            return
        
        try:
            # Get all datacenters
            datacenters = instance.get_datacenter_list()
            
            # Generate credentials hash for Redis cache
            creds_hash = vsphere_redis_cache.get_credentials_hash(
                os.environ.get('VSPHERE_SERVER'), 
                os.environ.get('VSPHERE_USER'),
                os.environ.get('VSPHERE_PASSWORD')
            )
            
            # Prepare simplified datacenter list for caching
            simplified_dcs = []
            for dc in datacenters:
                simplified_dcs.append({
                    'name': dc.name,
                    'id': str(getattr(dc, '_moId', dc.name)),
                })
            
            # Cache the datacenters list
            datacenters_key = f"vsphere:{creds_hash}:datacenters"
            r = vsphere_redis_cache.get_redis_connection()
            if r:
                try:
                    r.set(datacenters_key, json.dumps(simplified_dcs), ex=vsphere_redis_cache.CACHE_TTL)
                    logger.info(f"Cached {len(simplified_dcs)} datacenters")
                except Exception as cache_error:
                    logger.warning(f"Error caching datacenters: {str(cache_error)}")
            
            logger.info(f"Background refresh completed for datacenters with {len(datacenters)} entries")
            
        finally:
            # Disconnect when done
            instance.disconnect()
    except Exception as e:
        logger.exception(f"Error in background refresh for datacenters: {str(e)}")

def start_refresh_thread(func, *args, **kwargs):
    """
    Helper function to start a background refresh thread.
    
    Args:
        func: The refresh function to call
        args: Positional arguments for the function
        kwargs: Keyword arguments for the function
        
    Returns:
        threading.Thread: The started thread object
    """
    thread = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread
