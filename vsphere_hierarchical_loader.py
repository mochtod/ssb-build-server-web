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

# Import the existing loaders
import vsphere_optimized_loader
import vsphere_cluster_resources

# Configure logging
logger = logging.getLogger(__name__)

# Cache settings
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.vsphere_cache')
HIERARCHY_CACHE_FILE = os.path.join(CACHE_DIR, 'vsphere_hierarchy.json')
CACHE_TTL = 3600  # 1 hour in seconds
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
                datacenters_filter=None):
        """Initialize the hierarchical loader."""
        self.server = server or os.environ.get('VSPHERE_SERVER')
        self.username = username or os.environ.get('VSPHERE_USER')
        self.password = password or os.environ.get('VSPHERE_PASSWORD')
        self.timeout = timeout or int(os.environ.get('VSPHERE_TIMEOUT', '30'))
        self.datacenters_filter = datacenters_filter or self._get_datacenter_filter()
        
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
            'loaded_resources_for': set()  # Set of cluster IDs
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
    
    def _load_cluster_resources(self, cluster_id, cluster_name=None):
        """Load resources for a cluster in the background."""
        try:
            # First check if we already have resources for this cluster
            with self.lock:
                if cluster_id in self.status['loaded_resources_for']:
                    logger.info(f"Already have resources for cluster: {cluster_id}")
                    self.status['loading_resources'].remove(cluster_id)
                    
                    # Emit completed event with existing data
                    self._add_event('loading_resources_completed', {
                        'cluster_id': cluster_id,
                        'cluster_name': cluster_name,
                        'resources': self.resources_by_cluster.get(cluster_id, {})
                    })
                    return
            
            # Get resources from vsphere_cluster_resources
            resources = vsphere_cluster_resources.get_resources_for_cluster(
                cluster_id=cluster_id,
                use_cache=True
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
            
            # Update state
            with self.lock:
                self.resources_by_cluster[cluster_id] = resources
                self.status['loading_resources'].remove(cluster_id)
                self.status['loaded_resources_for'].add(cluster_id)
                self.status['last_update'] = datetime.now().isoformat()
            
            # Save to cache
            self._save_to_cache()
            
            # Emit completed event
            self._add_event('loading_resources_completed', {
                'cluster_id': cluster_id,
                'cluster_name': cluster_name or resources.get('cluster_name', 'Unknown'),
                'resources': resources
            })
            
            logger.info(f"Loaded resources for cluster: {cluster_name or cluster_id}")
            
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
                self.start_loading_clusters(datacenter_name)
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
                self.start_loading_resources(cluster_id, cluster_name)
                
                # Return default resources while loading
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
