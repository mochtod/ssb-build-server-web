#!/usr/bin/env python3
"""
Hierarchical vSphere Resource Loader

This module implements a hierarchical loading strategy for vSphere resources.
It follows the natural VMware hierarchy:
1. vCenter Servers
2. DataCenters
3. Clusters
4. Resource Pools, Networks, Datastores, Templates

All operations are performed asynchronously in background threads to 
avoid blocking the user interface.
"""
import os
import ssl
import json
import time
import logging
import threading
import queue
from datetime import datetime, timedelta
from threading import Lock, Thread

# Import the pyVmomi module
try:
    from pyVmomi import vim
except ImportError:
    logging.error("Required pyVmomi package not installed. Run: pip install pyVmomi")

# Import the existing loaders
import vsphere_optimized_loader
import vsphere_cluster_resources

# Import the Redis cache module
import vsphere_redis_cache

# Configure logging
logger = logging.getLogger(__name__)

# Cache settings
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.vsphere_cache')
HIERARCHY_CACHE_FILE = os.path.join(CACHE_DIR, 'vsphere_hierarchy.json')
CACHE_TTL = 86400  # 24 hours in seconds for base data
RESOURCE_CACHE_TTL = 3600  # 1 hour for resources (more volatile)
CACHE_LOCK = Lock()  # Lock for thread-safety

class ResourceFetchEvent:
    """Event object for resource fetch operations."""
    
    def __init__(self, event_type, data=None):
        self.event_type = event_type
        self.data = data or {}
        self.timestamp = datetime.now().isoformat()

class VSphereHierarchicalLoader:
    """
    Hierarchical loader for vSphere resources using background threads.
    
    This class implements a staged loading approach:
    1. Datacenter list (fast)
    2. Clusters per datacenter (medium)
    3. Resources per cluster (slow, on-demand)
    
    All operations are performed in background threads to avoid blocking the UI.
    """
    
    def __init__(self, 
                server=None, 
                username=None, 
                password=None, 
                timeout=None,
                datacenters_filter=None,
                auto_sync=True,
                sync_interval=1800):  # 30 minutes default
        """Initialize the hierarchical loader."""
        self.server = server or os.environ.get('VSPHERE_SERVER')
        self.username = username or os.environ.get('VSPHERE_USER')
        self.password = password or os.environ.get('VSPHERE_PASSWORD')
        self.timeout = timeout or int(os.environ.get('VSPHERE_TIMEOUT', '30'))
        self.datacenters_filter = datacenters_filter or self._get_datacenter_filter()
        self.auto_sync = auto_sync
        self.sync_interval = sync_interval
        
        # Resource state
        self.datacenters = []
        self.clusters_by_dc = {}
        self.resources_by_cluster = {}
        
        # Status tracking
        self.status = {
            'loading_datacenters': False,
            'loading_clusters': False,
            'loading_resources': set(),  # Set of cluster IDs currently loading
            'last_update': None,
            'error': None,
            'loaded_datacenters': False,
            'loaded_clusters_for': set(),  # Set of datacenter names
            'loaded_resources_for': set(),  # Set of cluster IDs
            'is_syncing': False,
            'last_sync': None
        }
        
        # Thread management
        self.lock = threading.RLock()
        self.worker_threads = []
        self.shutdown_event = threading.Event()
        
        # Event queue for callbacks
        self.event_queue = queue.Queue()
        self.event_listeners = []
        
        # Start event processor thread
        self.event_thread = Thread(target=self._process_events, daemon=True)
        self.event_thread.start()
        
        # Start background sync thread if auto_sync enabled
        if self.auto_sync:
            self.sync_thread = Thread(target=self._background_sync_worker, daemon=True)
            self.sync_thread.start()
            self.worker_threads.append(self.sync_thread)
        
        # Ensure cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)
        
        # Try to load from cache initially
        self._load_from_cache()
    
    def _get_datacenter_filter(self):
        """Get datacenter filter from environment."""
        dc_filter = os.environ.get('VSPHERE_DATACENTERS', '')
        if dc_filter:
            return [dc.strip() for dc in dc_filter.split(',') if dc.strip()]
        return None
    
    def add_event_listener(self, listener):
        """Add a listener for resource fetch events."""
        if callable(listener) and listener not in self.event_listeners:
            self.event_listeners.append(listener)
    
    def remove_event_listener(self, listener):
        """Remove a listener for resource fetch events."""
        if listener in self.event_listeners:
            self.event_listeners.remove(listener)
    
    def _process_events(self):
        """Process events and notify listeners."""
        while not self.shutdown_event.is_set():
            try:
                # Get event with a timeout to allow shutdown
                event = self.event_queue.get(timeout=1.0)
                
                # Notify all listeners
                for listener in self.event_listeners:
                    try:
                        listener(event)
                    except Exception as e:
                        logger.error(f"Error in event listener: {str(e)}")
                
                # Mark as processed
                self.event_queue.task_done()
                
            except queue.Empty:
                # No event, continue waiting
                continue
    
    def _add_event(self, event_type, data=None):
        """Add an event to the queue."""
        event = ResourceFetchEvent(event_type, data)
        self.event_queue.put(event)
    
    def _load_from_cache(self):
        """Load the hierarchical data from cache."""
        try:
            if os.path.exists(HIERARCHY_CACHE_FILE):
                file_age = time.time() - os.path.getmtime(HIERARCHY_CACHE_FILE)
                
                # Only use cache if it's valid (within TTL)
                if file_age < CACHE_TTL:
                    with open(HIERARCHY_CACHE_FILE, 'r') as f:
                        cached_data = json.load(f)
                    
                    with self.lock:
                        self.datacenters = cached_data.get('datacenters', [])
                        self.clusters_by_dc = cached_data.get('clusters_by_dc', {})
                        self.resources_by_cluster = cached_data.get('resources_by_cluster', {})
                        
                        # Update status
                        self.status['last_update'] = cached_data.get('timestamp')
                        self.status['loaded_datacenters'] = bool(self.datacenters)
                        
                        # Mark which datacenters have clusters loaded
                        self.status['loaded_clusters_for'] = set(self.clusters_by_dc.keys())
                        
                        # Mark which clusters have resources loaded  
                        self.status['loaded_resources_for'] = set(self.resources_by_cluster.keys())
                        
                        logger.info(f"Loaded hierarchy from cache: {len(self.datacenters)} datacenters, " +
                                   f"{sum(len(clusters) for clusters in self.clusters_by_dc.values())} clusters, " +
                                   f"{len(self.resources_by_cluster)} clusters with resources")
                    
                    # Emit event for cache loaded
                    self._add_event('cache_loaded', {
                        'datacenters_count': len(self.datacenters),
                        'clusters_count': sum(len(clusters) for clusters in self.clusters_by_dc.values()),
                        'resources_count': len(self.resources_by_cluster)
                    })
                    
                    return True
        except Exception as e:
            logger.error(f"Error loading cache: {str(e)}")
        
        return False
    
    def _save_to_cache(self):
        """Save the hierarchical data to cache."""
        try:
            with self.lock:
                cache_data = {
                    'datacenters': self.datacenters,
                    'clusters_by_dc': self.clusters_by_dc,
                    'resources_by_cluster': self.resources_by_cluster,
                    'timestamp': datetime.now().isoformat()
                }
            
            with CACHE_LOCK:
                with open(HIERARCHY_CACHE_FILE, 'w') as f:
                    json.dump(cache_data, f, indent=2)
                    
            logger.info("Saved hierarchy to cache")
            return True
            
        except Exception as e:
            logger.error(f"Error saving to cache: {str(e)}")
            return False
    
    def start_loading_datacenters(self):
        """Start loading datacenters in a background thread."""
        with self.lock:
            # Don't start if already loading
            if self.status['loading_datacenters']:
                logger.info("Datacenter loading already in progress")
                return False
                
            # Set loading flag
            self.status['loading_datacenters'] = True
            self.status['error'] = None
        
        # Start background thread
        thread = Thread(target=self._load_datacenters, daemon=True)
        thread.start()
        
        self.worker_threads.append(thread)
        logger.info("Started background thread for datacenter loading")
        
        # Emit event
        self._add_event('loading_datacenters_started')
        
        return True
    
    def _load_datacenters(self):
        """Load the list of datacenters in the background."""
        try:
            # Get instance of the cluster resources loader
            loader = vsphere_cluster_resources.get_instance()
            
            # Connect and get datacenters
            if not loader.connect():
                with self.lock:
                    self.status['loading_datacenters'] = False
                    self.status['error'] = "Failed to connect to vSphere"
                
                # Emit error event
                self._add_event('loading_datacenters_error', {
                    'error': "Failed to connect to vSphere"
                })
                
                return
            
            try:
                # Get datacenters with filter if provided
                dc_objects = loader.get_datacenter_list(self.datacenters_filter)
                
                # Convert to simplified objects
                datacenters = []
                for dc in dc_objects:
                    datacenters.append({
                        'name': dc.name,
                        'id': str(getattr(dc, '_moId', dc.name)),
                    })
                
                # Update state
                with self.lock:
                    self.datacenters = datacenters
                    self.status['loading_datacenters'] = False
                    self.status['loaded_datacenters'] = True
                    self.status['last_update'] = datetime.now().isoformat()
                
                # Save to cache
                self._save_to_cache()
                
                # Emit completed event
                self._add_event('loading_datacenters_completed', {
                    'datacenters': datacenters
                })
                
                logger.info(f"Loaded {len(datacenters)} datacenters")
                
            finally:
                # Always disconnect
                loader.disconnect()
            
        except Exception as e:
            logger.exception(f"Error loading datacenters: {str(e)}")
            
            with self.lock:
                self.status['loading_datacenters'] = False
                self.status['error'] = str(e)
            
            # Emit error event
            self._add_event('loading_datacenters_error', {
                'error': str(e)
            })
    
    def start_loading_clusters(self, datacenter_name):
        """Start loading clusters for a datacenter in a background thread."""
        with self.lock:
            # Don't start if already loading or if datacenter not found
            if self.status['loading_clusters'] or datacenter_name not in [dc['name'] for dc in self.datacenters]:
                return False
                
            # Set loading flag
            self.status['loading_clusters'] = True
            self.status['error'] = None
        
        # Start background thread
        thread = Thread(target=self._load_clusters, args=(datacenter_name,), daemon=True)
        thread.start()
        
        self.worker_threads.append(thread)
        logger.info(f"Started background thread for loading clusters in datacenter: {datacenter_name}")
        
        # Emit event
        self._add_event('loading_clusters_started', {
            'datacenter': datacenter_name
        })
        
        return True
    
    def _load_clusters(self, datacenter_name):
        """Load clusters for a datacenter in the background."""
        try:
            # First check if we already have these clusters
            with self.lock:
                if datacenter_name in self.status['loaded_clusters_for']:
                    logger.info(f"Already have clusters for datacenter: {datacenter_name}")
                    self.status['loading_clusters'] = False
                    
                    # Emit completed event with existing data
                    self._add_event('loading_clusters_completed', {
                        'datacenter': datacenter_name,
                        'clusters': self.clusters_by_dc.get(datacenter_name, [])
                    })
                    return
            
            # Get clusters from vsphere_cluster_resources
            clusters = vsphere_cluster_resources.get_clusters(
                use_cache=True,
                target_datacenters=[datacenter_name]
            )
            
            # Filter to only clusters in this datacenter
            dc_clusters = [c for c in clusters if c.get('datacenter') == datacenter_name]
            
            # Update state
            with self.lock:
                self.clusters_by_dc[datacenter_name] = dc_clusters
                self.status['loading_clusters'] = False
                self.status['loaded_clusters_for'].add(datacenter_name)
                self.status['last_update'] = datetime.now().isoformat()
            
            # Save to cache
            self._save_to_cache()
            
            # Emit completed event
            self._add_event('loading_clusters_completed', {
                'datacenter': datacenter_name,
                'clusters': dc_clusters
            })
            
            logger.info(f"Loaded {len(dc_clusters)} clusters for datacenter: {datacenter_name}")
            
        except Exception as e:
            logger.exception(f"Error loading clusters for datacenter {datacenter_name}: {str(e)}")
            
            with self.lock:
                self.status['loading_clusters'] = False
                self.status['error'] = str(e)
            
            # Emit error event
            self._add_event('loading_clusters_error', {
                'datacenter': datacenter_name,
                'error': str(e)
            })
    
    def start_loading_resources(self, cluster_id, cluster_name=None):
        """Start loading resources for a cluster in a background thread."""
        with self.lock:
            # Don't start if already loading this cluster
            if cluster_id in self.status['loading_resources']:
                logger.info(f"Already loading resources for cluster: {cluster_id}")
                return False
                
            # Add to loading set
            self.status['loading_resources'].add(cluster_id)
            self.status['error'] = None
        
        # Start background thread
        thread = Thread(target=self._load_cluster_resources, args=(cluster_id, cluster_name), daemon=True)
        thread.start()
        
        self.worker_threads.append(thread)
        logger.info(f"Started background thread for loading resources in cluster: {cluster_name or cluster_id}")
        
        # Emit event
        self._add_event('loading_resources_started', {
            'cluster_id': cluster_id,
            'cluster_name': cluster_name
        })
        
        return True
    
    @vsphere_redis_cache.timeit
    def _load_cluster_resources(self, cluster_id, cluster_name=None):
        """Load resources for a cluster in the background."""
        try:
            # Generate credentials hash for Redis cache
            creds_hash = vsphere_redis_cache.get_credentials_hash(
                self.server, self.username, self.password
            )
            
            # First check Redis cache for faster access
            redis_cached_resources = {}
            
            # Load essential resources (excluding templates) from Redis cache
            for res_type in ['datastores', 'networks', 'resource_pools']:
                cached_res = vsphere_redis_cache.get_cached_cluster_resources(
                    cluster_id, res_type, creds_hash
                )
                if cached_res:
                    redis_cached_resources[res_type] = cached_res
                    logger.debug(f"Redis cache hit for {res_type} in cluster {cluster_id}")
            
            # If we have all essential resources in Redis cache, we can use them
            if all(res_type in redis_cached_resources for res_type in ['datastores', 'networks', 'resource_pools']):
                # Check existing resources for templates
                existing_resources = None
                with self.lock:
                    if cluster_id in self.status['loaded_resources_for']:
                        existing_resources = self.resources_by_cluster.get(cluster_id, {})
                
                # Combine Redis-cached resources with any existing templates
                resources = {
                    'cluster_name': cluster_name or cluster_id,
                    'cluster_id': cluster_id,
                    'datastores': redis_cached_resources['datastores'],
                    'networks': redis_cached_resources['networks'],
                    'resource_pools': redis_cached_resources['resource_pools'],
                    'templates': existing_resources.get('templates', []) if existing_resources else [],
                    'last_update': datetime.now().isoformat()
                }
                
                # Update state
                with self.lock:
                    self.resources_by_cluster[cluster_id] = resources
                    self.status['loading_resources'].remove(cluster_id)
                    self.status['loaded_resources_for'].add(cluster_id)
                    self.status['last_update'] = datetime.now().isoformat()
                
                # Save to file cache too
                self._save_to_cache()
                
                # Start background template loading (non-blocking)
                # Templates often cause the timeout issues, so we load them separately
                instance = vsphere_cluster_resources.get_instance()
                if instance.connect():
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
                        
                        if cluster_obj:
                            # Launch template loading in background
                            vsphere_redis_cache.template_loader.start_loading_templates(
                                cluster_id, cluster_obj, instance, creds_hash
                            )
                    finally:
                        # Don't disconnect yet - template loader will do that
                        pass
                
                # Emit completed event
                self._add_event('loading_resources_completed', {
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name or resources.get('cluster_name', 'Unknown'),
                    'resources': resources,
                    'source': 'redis_cache'
                })
                
                logger.info(f"Loaded resources from Redis cache for cluster: {cluster_name or cluster_id}")
                return
            
            # Check if we already have resources in file cache
            existing_resources = None
            last_update_time = None
            
            with self.lock:
                if cluster_id in self.status['loaded_resources_for']:
                    existing_resources = self.resources_by_cluster.get(cluster_id, {})
                    if 'last_update' in existing_resources:
                        last_update_time = existing_resources['last_update']
                    logger.info(f"Resources exist for cluster: {cluster_id}, last updated: {last_update_time}")
                
            # Add timestamp to check if refresh needed
            if existing_resources and last_update_time:
                # Parse the time string to datetime
                try:
                    last_update = datetime.fromisoformat(last_update_time)
                    time_since_update = datetime.now() - last_update
                    
                    # Only if resource cache TTL has passed, do a full refresh
                    if time_since_update.total_seconds() < RESOURCE_CACHE_TTL:
                        logger.info(f"Using cached resources for cluster {cluster_id}, cache still valid (age: {time_since_update.total_seconds()/60:.1f} minutes)")
                        
                        with self.lock:
                            self.status['loading_resources'].remove(cluster_id)
                            
                        # Emit completed event with existing data
                        self._add_event('loading_resources_completed', {
                            'cluster_id': cluster_id,
                            'cluster_name': cluster_name,
                            'resources': existing_resources,
                            'source': 'file_cache'
                        })
                        return
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse last update time: {last_update_time}, error: {str(e)}")
            
            # Get resources from vsphere_cluster_resources if no cache hit
            logger.info(f"Fetching fresh resources for cluster: {cluster_name or cluster_id}")
            start_time = time.time()
            
            # Fetch all resources except templates
            instance = vsphere_cluster_resources.get_instance()
            if instance.connect():
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
                    
                    if cluster_obj:
                        # Get critical resources first (datastores, networks, resource pools)
                        resources = {
                            'cluster_name': cluster_name or getattr(cluster_obj, 'name', cluster_id),
                            'cluster_id': cluster_id,
                            'datastores': [],
                            'networks': [],
                            'resource_pools': [],
                            'templates': []  # Will be loaded in background
                        }
                        
                        # Always provide at least one template for the UI to display
                        if not resources['templates']:
                            resources['templates'] = [
                                {
                                    'id': 'vm-11682491',  # Use default template ID from env
                                    'name': 'RHEL9 Template (Loading in background...)',
                                    'guest_os': 'rhel9_64Guest',
                                    'cpu_count': 2,
                                    'memory_mb': 4096
                                }
                            ]
                        
                        # Get datastores
                        logger.info(f"Retrieving datastores for cluster: {cluster_name or cluster_id}")
                        resources['datastores'] = instance.get_datastores_by_cluster(cluster_obj)
                        # Cache in Redis
                        vsphere_redis_cache.cache_cluster_resources(
                            cluster_id, 'datastores', resources['datastores'], creds_hash
                        )
                        
                        # Get networks
                        logger.info(f"Retrieving networks for cluster: {cluster_name or cluster_id}")
                        resources['networks'] = instance.get_networks_by_cluster(cluster_obj)
                        # Cache in Redis
                        vsphere_redis_cache.cache_cluster_resources(
                            cluster_id, 'networks', resources['networks'], creds_hash
                        )
                        
                        # Get resource pools
                        logger.info(f"Retrieving resource pools for cluster: {cluster_name or cluster_id}")
                        resources['resource_pools'] = instance.get_resource_pools_by_cluster(cluster_obj)
                        # Cache in Redis
                        vsphere_redis_cache.cache_cluster_resources(
                            cluster_id, 'resource_pools', resources['resource_pools'], creds_hash
                        )
                        
                        # Launch template loading in background
                        vsphere_redis_cache.template_loader.start_loading_templates(
                            cluster_id, cluster_obj, instance, creds_hash
                        )
                        
                        # Filter out local datastores (containing "_local" in name)
                        if 'datastores' in resources:
                            original_count = len(resources['datastores'])
                            resources['datastores'] = [
                                ds for ds in resources['datastores'] 
                                if "_local" not in ds['name']
                            ]
                            filtered_count = len(resources['datastores'])
                            logger.info(f"Filtered datastores for cluster {resources.get('cluster_name', 'Unknown')}: {original_count} → {filtered_count}")
                finally:
                    # Don't disconnect yet - template loader will do that
                    pass
            else:
                # Use cached data or empty lists if connection fails
                resources = vsphere_cluster_resources.get_resources_for_cluster(
                    cluster_id=cluster_id,
                    use_cache=True
                )
            
            # Add timestamp for future cache checks
            resources['last_update'] = datetime.now().isoformat()
            
            # Update state
            with self.lock:
                self.resources_by_cluster[cluster_id] = resources
                self.status['loading_resources'].remove(cluster_id)
                self.status['loaded_resources_for'].add(cluster_id)
                self.status['last_update'] = datetime.now().isoformat()
            
            # Save to file cache
            self._save_to_cache()
            
            # Emit completed event
            self._add_event('loading_resources_completed', {
                'cluster_id': cluster_id,
                'cluster_name': cluster_name or resources.get('cluster_name', 'Unknown'),
                'resources': resources,
                'performance': {
                    'total_time_ms': int((time.time() - start_time) * 1000)
                }
            })
            
            logger.info(f"Loaded essential resources for cluster: {cluster_name or cluster_id} in {time.time() - start_time:.2f}s (templates loading in background)")
            
        except Exception as e:
            logger.exception(f"Error loading resources for cluster {cluster_id}: {str(e)}")
            
            with self.lock:
                if cluster_id in self.status['loading_resources']:
                    self.status['loading_resources'].remove(cluster_id)
                self.status['error'] = str(e)
            
            # Emit error event
            self._add_event('loading_resources_error', {
                'cluster_id': cluster_id,
                'cluster_name': cluster_name,
                'error': str(e)
            })
    
    def get_datacenters(self, force_load=False):
        """
        Get the list of datacenters.
        
        Args:
            force_load: If True, force a reload of datacenters
            
        Returns:
            list: List of datacenters
        """
        with self.lock:
            if not self.datacenters or force_load:
                # If force_load is True, load synchronously instead of in background
                if force_load:
                    logger.info(f"Force loading datacenters")
                    # Release lock while loading to avoid deadlock
                    self.lock.release()
                    try:
                        # Get instance of the cluster resources loader
                        loader = vsphere_cluster_resources.get_instance()
                        
                        # Connect and get datacenters
                        if loader.connect():
                            try:
                                # Get datacenters with filter if provided
                                dc_objects = loader.get_datacenter_list(self.datacenters_filter)
                                
                                # Convert to simplified objects
                                datacenters = []
                                for dc in dc_objects:
                                    datacenters.append({
                                        'name': dc.name,
                                        'id': str(getattr(dc, '_moId', dc.name)),
                                    })
                                
                                # Reacquire lock to update shared state
                                self.lock.acquire()
                                self.datacenters = datacenters
                                self.status['loaded_datacenters'] = True
                                self.status['last_update'] = datetime.now().isoformat()
                                
                                # Save to cache while we have the lock
                                self._save_to_cache()
                                
                                logger.info(f"Synchronously loaded {len(datacenters)} datacenters")
                                
                                # Return the datacenters (still holding lock)
                                return datacenters.copy()
                            finally:
                                # Always disconnect
                                loader.disconnect()
                                
                                # Make sure we reacquire the lock if we haven't already
                                if not self.lock._is_owned():
                                    self.lock.acquire()
                        else:
                            logger.error("Failed to connect to vSphere")
                            # Make sure we reacquire the lock
                            self.lock.acquire()
                    except Exception as e:
                        logger.exception(f"Error synchronously loading datacenters: {str(e)}")
                        # Make sure we reacquire the lock
                        if not self.lock._is_owned():
                            self.lock.acquire()
                else:
                    # Just start background loading if not force_load
                    self.start_loading_datacenters()
            
            return self.datacenters.copy()
    
    def get_clusters(self, datacenter_name, force_load=False):
        """
        Get clusters for a datacenter.
        
        Args:
            datacenter_name: Name of the datacenter
            force_load: If True, force a reload of clusters
            
        Returns:
            list: List of clusters in the datacenter
        """
        with self.lock:
            if datacenter_name not in self.clusters_by_dc or force_load:
                # If force_load is True, load synchronously instead of in background
                if force_load:
                    logger.info(f"Force loading clusters for datacenter: {datacenter_name}")
                    # Release lock while loading to avoid deadlock
                    self.lock.release()
                    try:
                        # Get instance of the cluster resources loader
                        loader = vsphere_cluster_resources.get_instance()
                        
                        # Connect and get clusters
                        if loader.connect():
                            try:
                                # Get datacenters with filter to find the one we want
                                dc_objects = loader.get_datacenter_list([datacenter_name])
                                
                                if dc_objects:
                                    # Get clusters for this datacenter
                                    dc = dc_objects[0]  # Use the first (and should be only) matching datacenter
                                    clusters = loader.get_clusters(dc)
                                    
                                    # Reacquire lock to update shared state
                                    self.lock.acquire()
                                    self.clusters_by_dc[datacenter_name] = clusters
                                    self.status['loaded_clusters_for'].add(datacenter_name)
                                    self.status['last_update'] = datetime.now().isoformat()
                                    
                                    # Save to cache while we have the lock
                                    self._save_to_cache()
                                    
                                    logger.info(f"Synchronously loaded {len(clusters)} clusters for datacenter: {datacenter_name}")
                                    
                                    # Return the clusters (still holding lock)
                                    return clusters.copy()
                                else:
                                    logger.warning(f"No datacenter found with name: {datacenter_name}")
                            finally:
                                # Always disconnect
                                loader.disconnect()
                                
                                # Make sure we reacquire the lock if we haven't already
                                if not self.lock._is_owned():
                                    self.lock.acquire()
                        else:
                            logger.error("Failed to connect to vSphere")
                            # Make sure we reacquire the lock
                            self.lock.acquire()
                    except Exception as e:
                        logger.exception(f"Error synchronously loading clusters for datacenter {datacenter_name}: {str(e)}")
                        # Make sure we reacquire the lock
                        if not self.lock._is_owned():
                            self.lock.acquire()
                else:
                    # Just start background loading if not force_load
                    self.start_loading_clusters(datacenter_name)
                    
                # Return empty list if we didn't load anything synchronously
                if datacenter_name not in self.clusters_by_dc:
                    return []
            
            return self.clusters_by_dc[datacenter_name].copy()
    
    def get_resources(self, cluster_id, cluster_name=None, force_load=False):
        """
        Get resources for a cluster.
        
        Args:
            cluster_id: ID of the cluster
            cluster_name: Name of the cluster (optional, for logging)
            force_load: If True, force a reload of resources
            
        Returns:
            dict: Dictionary with resources for the cluster
        """
        with self.lock:
            if cluster_id not in self.resources_by_cluster or force_load:
                # If force_load is True, load synchronously instead of in background
                if force_load:
                    logger.info(f"Force loading resources for cluster: {cluster_name or cluster_id}")
                    # Release lock while loading to avoid deadlock
                    self.lock.release()
                    lock_reacquired = False
                    try:
                        # Load resources synchronously with a timeout
                        logger.info(f"Starting synchronous resource load for cluster: {cluster_name or cluster_id}")
                        
                        # Load all needed resources - networks, datastores, and templates
                        resources = {
                            'cluster_name': cluster_name or cluster_id,
                            'cluster_id': cluster_id,
                            'datastores': [],
                            'networks': [],
                            'templates': [],
                            'resource_pools': []
                        }
                        
                        # Connect to vSphere and get a cluster object
                        instance = vsphere_cluster_resources.get_instance()
                        if instance.connect():
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
                                
                                if cluster_obj:
                                    # Get datastores and networks
                                    logger.info(f"Retrieving datastores for cluster: {cluster_name or cluster_id}")
                                    resources['datastores'] = instance.get_datastores_by_cluster(cluster_obj)
                                    
                                    logger.info(f"Retrieving networks for cluster: {cluster_name or cluster_id}")
                                    resources['networks'] = instance.get_networks_by_cluster(cluster_obj)
                                    
                                    # Get templates as well (now shown in UI)
                                    logger.info(f"Retrieving templates for cluster: {cluster_name or cluster_id}")
                                    resources['templates'] = instance.get_templates_by_cluster(cluster_obj)
                                    
                                    # Get resource pools (usually just one per cluster)
                                    logger.info(f"Retrieving resource pools for cluster: {cluster_name or cluster_id}")
                                    resources['resource_pools'] = instance.get_resource_pools_by_cluster(cluster_obj)
                                    
                                    # Filter out local datastores (containing "_local" in name)
                                    if 'datastores' in resources:
                                        original_count = len(resources['datastores'])
                                        resources['datastores'] = [
                                            ds for ds in resources['datastores'] 
                                            if "_local" not in ds['name']
                                        ]
                                        filtered_count = len(resources['datastores'])
                                        logger.info(f"Filtered datastores for cluster {resources.get('cluster_name', 'Unknown')}: {original_count} → {filtered_count}")
                            finally:
                                # Always disconnect
                                instance.disconnect()
                        
                        # Reacquire lock to update shared state
                        self.lock.acquire()
                        lock_reacquired = True
                        
                        # Update resources in our cache
                        self.resources_by_cluster[cluster_id] = resources
                        self.status['loaded_resources_for'].add(cluster_id)
                        self.status['last_update'] = datetime.now().isoformat()
                        
                        # Save to cache while we have the lock
                        self._save_to_cache()
                        
                        logger.info(f"Synchronously loaded essential resources for cluster: {cluster_name or cluster_id}")
                        
                        # Return the resources (still holding lock)
                        return resources.copy()
                        
                    except Exception as e:
                        logger.exception(f"Error synchronously loading resources for cluster {cluster_id}: {str(e)}")
                        # Make sure we reacquire the lock
                        if not lock_reacquired and not self.lock._is_owned():
                            try:
                                self.lock.acquire()
                                lock_reacquired = True
                            except Exception as lock_error:
                                logger.error(f"Failed to reacquire lock: {str(lock_error)}")
                else:
                    # Just start background loading if not force_load
                    self.start_loading_resources(cluster_id, cluster_name)
                    
                # Return default resources if we didn't load anything synchronously
                if cluster_id not in self.resources_by_cluster:
                    return {
                        'resource_pools': [],
                        'datastores': [],
                        'networks': [],
                        'templates': [],
                        'loading': True
                    }
            
            return self.resources_by_cluster[cluster_id].copy()
    
    def get_status(self):
        """Get the current status of resource loading."""
        with self.lock:
            status_copy = self.status.copy()
            
            # Convert sets to lists for serialization
            status_copy['loading_resources'] = list(status_copy['loading_resources'])
            status_copy['loaded_clusters_for'] = list(status_copy['loaded_clusters_for'])
            status_copy['loaded_resources_for'] = list(status_copy['loaded_resources_for'])
            
            # Add count information
            status_copy['datacenter_count'] = len(self.datacenters)
            status_copy['cluster_count'] = sum(len(clusters) for clusters in self.clusters_by_dc.values())
            status_copy['resource_clusters_count'] = len(self.resources_by_cluster)
            
            return status_copy
    
    def _background_sync_worker(self):
        """Background worker thread that periodically syncs resources."""
        logger.info(f"Starting background sync worker (interval: {self.sync_interval} seconds)")
        
        while not self.shutdown_event.is_set():
            # Sleep for a bit before checking if it's time to sync
            for _ in range(60):  # Check shutdown event every second
                if self.shutdown_event.is_set():
                    break
                time.sleep(1)
            
            # Skip if we should be shutting down
            if self.shutdown_event.is_set():
                break
                
            try:
                # Check if we should sync
                should_sync = False
                
                with self.lock:
                    # Don't sync if we're already syncing
                    if self.status['is_syncing']:
                        logger.debug("Skipping sync because another sync is in progress")
                        continue
                    
                    # Check when we last synced
                    last_sync = self.status.get('last_sync')
                    if last_sync:
                        try:
                            last_sync_time = datetime.fromisoformat(last_sync)
                            time_since_sync = datetime.now() - last_sync_time
                            
                            if time_since_sync.total_seconds() >= self.sync_interval:
                                should_sync = True
                                logger.info(f"Time to sync resources (last sync: {time_since_sync.total_seconds()/60:.1f} minutes ago)")
                            else:
                                logger.debug(f"Skipping sync, not enough time elapsed ({time_since_sync.total_seconds()/60:.1f} minutes since last sync)")
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Error parsing last sync time: {str(e)}")
                            should_sync = True
                    else:
                        # No record of last sync, do one now
                        should_sync = True
                    
                    # Set syncing status if we're going to sync
                    if should_sync:
                        self.status['is_syncing'] = True
                
                # Perform sync if we should
                if should_sync:
                    try:
                        logger.info("Starting background data sync...")
                        
                        # Sync only resources for clusters that have been used/loaded
                        with self.lock:
                            clusters_to_sync = list(self.status['loaded_resources_for'])
                        
                        # Sync resources for used clusters
                        for cluster_id in clusters_to_sync:
                            # Skip if shutting down
                            if self.shutdown_event.is_set():
                                break
                                
                            # Get cluster name if available
                            cluster_name = None
                            with self.lock:
                                if cluster_id in self.resources_by_cluster:
                                    cluster_name = self.resources_by_cluster[cluster_id].get('cluster_name')
                            
                            try:
                                logger.info(f"Syncing resources for cluster: {cluster_name or cluster_id}")
                                self._sync_cluster_resources(cluster_id, cluster_name)
                            except Exception as e:
                                logger.error(f"Error syncing resources for cluster {cluster_id}: {str(e)}")
                        
                        # Save to cache
                        self._save_to_cache()
                        
                        logger.info(f"Background sync completed for {len(clusters_to_sync)} clusters")
                        
                        # Update sync status
                        with self.lock:
                            self.status['is_syncing'] = False
                            self.status['last_sync'] = datetime.now().isoformat()
                            
                            # Emit sync completed event
                            self._add_event('background_sync_completed', {
                                'clusters_synced': len(clusters_to_sync),
                                'timestamp': self.status['last_sync']
                            })
                            
                    except Exception as e:
                        logger.exception(f"Error during background sync: {str(e)}")
                        
                        # Make sure we clear the syncing status
                        with self.lock:
                            self.status['is_syncing'] = False
            
            except Exception as e:
                logger.exception(f"Unexpected error in sync worker: {str(e)}")
                
                # Make sure we clear the syncing status
                with self.lock:
                    self.status['is_syncing'] = False
        
        logger.info("Background sync worker exiting")
    
    def _sync_cluster_resources(self, cluster_id, cluster_name=None):
        """Sync resources for a specific cluster, updating only changed data."""
        # Get existing resources
        existing_resources = None
        
        with self.lock:
            if cluster_id in self.resources_by_cluster:
                existing_resources = self.resources_by_cluster[cluster_id].copy()
        
        if not existing_resources:
            # No existing data, perform full load
            logger.info(f"No existing resources for cluster {cluster_id}, performing full load")
            self._load_cluster_resources(cluster_id, cluster_name)
            return
        
        # Track what's changed
        changes = {
            'datastores': {'added': 0, 'removed': 0, 'changed': 0},
            'networks': {'added': 0, 'removed': 0, 'changed': 0},
            'templates': {'added': 0, 'removed': 0, 'changed': 0},
            'resource_pools': {'added': 0, 'removed': 0, 'changed': 0}
        }
        
        # Get fresh resources from vSphere
        try:
            # Get a connection
            instance = vsphere_cluster_resources.get_instance()
            if not instance.connect():
                logger.error(f"Failed to connect to vSphere during sync for cluster {cluster_id}")
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
                    logger.warning(f"Could not find cluster object for ID {cluster_id} during sync")
                    return
                
                # Get fresh resources
                new_resources = {
                    'cluster_name': cluster_name or existing_resources.get('cluster_name', cluster_id),
                    'cluster_id': cluster_id,
                    'datastores': instance.get_datastores_by_cluster(cluster_obj),
                    'networks': instance.get_networks_by_cluster(cluster_obj),
                    'templates': instance.get_templates_by_cluster(cluster_obj),
                    'resource_pools': instance.get_resource_pools_by_cluster(cluster_obj),
                    'last_update': datetime.now().isoformat()
                }
                
                # Filter out local datastores
                if 'datastores' in new_resources:
                    original_count = len(new_resources['datastores'])
                    new_resources['datastores'] = [
                        ds for ds in new_resources['datastores'] 
                        if "_local" not in ds['name']
                    ]
                    filtered_count = len(new_resources['datastores'])
                    logger.debug(f"Filtered datastores during sync: {original_count} → {filtered_count}")
                
                # Compare and update resources
                with self.lock:
                    # Update each resource type, tracking changes
                    for res_type in ['datastores', 'networks', 'templates', 'resource_pools']:
                        # Skip if not in both new and existing resources
                        if res_type not in new_resources or res_type not in existing_resources:
                            continue
                            
                        # Create lookup dictionaries by ID
                        existing_by_id = {r['id']: r for r in existing_resources.get(res_type, [])}
                        new_by_id = {r['id']: r for r in new_resources.get(res_type, [])}
                        
                        # Find added, removed, and changed resources
                        added_ids = set(new_by_id.keys()) - set(existing_by_id.keys())
                        removed_ids = set(existing_by_id.keys()) - set(new_by_id.keys())
                        common_ids = set(existing_by_id.keys()) & set(new_by_id.keys())
                        
                        # Check for changes in common resources
                        changed_ids = set()
                        for res_id in common_ids:
                            # Check for significant changes
                            if res_type == 'datastores':
                                # For datastores, check free space
                                if 'free_gb' in new_by_id[res_id] and 'free_gb' in existing_by_id[res_id]:
                                    # If free space changed by more than 5%, consider it changed
                                    new_free = new_by_id[res_id]['free_gb']
                                    old_free = existing_by_id[res_id]['free_gb']
                                    
                                    if abs(new_free - old_free) > (old_free * 0.05):
                                        changed_ids.add(res_id)
                            # Other resource types - just consider them unchanged for now
                        
                        # Update counts for logging
                        changes[res_type]['added'] = len(added_ids)
                        changes[res_type]['removed'] = len(removed_ids)
                        changes[res_type]['changed'] = len(changed_ids)
                        
                    # Update our stored resources with the fresh data
                    self.resources_by_cluster[cluster_id] = new_resources
                    
                # Log changes
                for res_type, counts in changes.items():
                    if counts['added'] > 0 or counts['removed'] > 0 or counts['changed'] > 0:
                        logger.info(f"Cluster {cluster_id} {res_type} changes: +{counts['added']}, -{counts['removed']}, Δ{counts['changed']}")
                
            finally:
                # Always disconnect
                instance.disconnect()
                
        except Exception as e:
            logger.exception(f"Error syncing resources for cluster {cluster_id}: {str(e)}")
            # Don't update anything if we encountered an error
    
    def shutdown(self):
        """Shutdown the hierarchical loader and its threads."""
        # Signal all threads to exit
        self.shutdown_event.set()
        
        # Wait for worker threads to finish
        for thread in self.worker_threads:
            if thread.is_alive():
                thread.join(timeout=1.0)
        
        # Clear thread list
        self.worker_threads.clear()
        
        # Wait for event thread
        if self.event_thread.is_alive():
            self.event_thread.join(timeout=1.0)
        
        # Save cache one last time
        self._save_to_cache()
        
        logger.info("Hierarchical loader shutdown complete")

# Singleton instance
_hierarchical_loader = None

def get_loader(server=None, username=None, password=None, timeout=None, datacenters_filter=None):
    """Get the singleton hierarchical loader instance."""
    global _hierarchical_loader
    if _hierarchical_loader is None:
        _hierarchical_loader = VSphereHierarchicalLoader(
            server=server,
            username=username,
            password=password,
            timeout=timeout,
            datacenters_filter=datacenters_filter
        )
    return _hierarchical_loader

def get_default_resources():
    """Get default resources when vSphere connection fails."""
    # Use the same defaults as the optimized loader
    return vsphere_optimized_loader.get_default_resources()

def get_datacenters(force_load=False):
    """Convenience function to get datacenters."""
    loader = get_loader()
    return loader.get_datacenters(force_load=force_load)

def get_clusters(datacenter_name, force_load=False):
    """Convenience function to get clusters for a datacenter."""
    loader = get_loader()
    return loader.get_clusters(datacenter_name, force_load=force_load)

def get_resources(cluster_id, cluster_name=None, force_load=False):
    """Convenience function to get resources for a cluster."""
    loader = get_loader()
    return loader.get_resources(cluster_id, cluster_name, force_load=force_load)

def get_loading_status():
    """Convenience function to get the current loading status."""
    loader = get_loader()
    return loader.get_status()

def add_event_listener(listener):
    """Add a listener for resource fetch events."""
    loader = get_loader()
    loader.add_event_listener(listener)

def remove_event_listener(listener):
    """Remove a listener for resource fetch events."""
    loader = get_loader()
    loader.remove_event_listener(listener)

# Cleanup function
def shutdown():
    """Shutdown the hierarchical loader."""
    global _hierarchical_loader
    if _hierarchical_loader is not None:
        _hierarchical_loader.shutdown()
        _hierarchical_loader = None

# Register shutdown as an atexit function
import atexit
atexit.register(shutdown)
