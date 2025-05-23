
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
avoid blocking the user interface. This module now includes memory optimization
techniques to reduce memory usage and improve performance.
"""
import os
import ssl
import json
import time
import logging
import threading
import queue
import gc
import weakref
from datetime import datetime, timedelta
from threading import Lock, Thread
from typing import Dict, List, Optional, Set, Any

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

# Optional import for memory profiling
try:
    import tracemalloc
    import linecache
    from tracemalloc import Snapshot
    MEMORY_PROFILING_AVAILABLE = True
except ImportError:
    MEMORY_PROFILING_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)

# Cache settings
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.vsphere_cache')
HIERARCHY_CACHE_FILE = os.path.join(CACHE_DIR, 'vsphere_hierarchy.json')
CACHE_TTL = 86400  # 24 hours in seconds for base data
RESOURCE_CACHE_TTL = 3600  # 1 hour for resources (more volatile)
CACHE_LOCK = Lock()  # Lock for thread-safety

# Memory optimization settings
MEMORY_PROFILING_ENABLED = os.environ.get('VSPHERE_MEMORY_PROFILING', 'false').lower() == 'true'
LAZY_LOADING_ENABLED = os.environ.get('VSPHERE_LAZY_LOADING', 'true').lower() == 'true'
PAGINATION_SIZE = int(os.environ.get('VSPHERE_PAGINATION_SIZE', '50'))
DATA_PRUNING_ENABLED = os.environ.get('VSPHERE_DATA_PRUNING', 'true').lower() == 'true'
EXPLICIT_GC = os.environ.get('VSPHERE_EXPLICIT_GC', 'true').lower() == 'true'

# Memory profiling top results to keep
MEMORY_TOP_STATS = int(os.environ.get('VSPHERE_MEMORY_TOP_STATS', '25'))

# Essential attributes to keep when pruning data
ESSENTIAL_ATTRIBUTES = {
    'datacenters': ['name', 'id'],
    'clusters': ['name', 'id', 'datacenter', 'type', 'host_count'],
    'datastores': ['name', 'id', 'type', 'free_gb', 'capacity', 'free_space', 'cluster_id', 
                  'cluster_name', 'shared_across_cluster'],
    'networks': ['name', 'id', 'type', 'cluster_id', 'cluster_name', 'is_dvs'],
    'resource_pools': ['name', 'id', 'type', 'cluster_id', 'cluster_name', 'is_primary'],
    'templates': ['name', 'id', 'type', 'cluster_id', 'cluster_name', 'is_template', 
                 'guest_id', 'guest_fullname']
}

class MemoryProfiler:
    """Memory profiling utility for vSphere resource loading operations."""
    
    def __init__(self):
        """Initialize the memory profiler."""
        self.enabled = MEMORY_PROFILING_ENABLED and MEMORY_PROFILING_AVAILABLE
        self.lock = Lock()
        self.last_snapshot = None
        self.baseline_snapshot = None
        self.snapshots = {}  # key: operation name, value: tracemalloc snapshot
        
        if self.enabled:
            try:
                tracemalloc.start()
                logger.info("Memory profiling enabled")
                # Take baseline snapshot
                self.baseline_snapshot = tracemalloc.take_snapshot()
            except Exception as e:
                logger.error(f"Failed to start memory profiling: {e}")
                self.enabled = False
    
    def take_snapshot(self, operation_name):
        """Take a memory snapshot for a specific operation."""
        if not self.enabled:
            return
            
        with self.lock:
            try:
                snapshot = tracemalloc.take_snapshot()
                self.snapshots[operation_name] = snapshot
                self.last_snapshot = snapshot
                logger.debug(f"Memory snapshot taken for operation: {operation_name}")
            except Exception as e:
                logger.error(f"Failed to take memory snapshot: {e}")
    
    def get_memory_diff(self, operation_name=None, baseline=False):
        """Get memory usage difference between snapshots."""
        if not self.enabled:
            return None
            
        with self.lock:
            if operation_name and operation_name in self.snapshots:
                snapshot = self.snapshots[operation_name]
            elif self.last_snapshot:
                snapshot = self.last_snapshot
            else:
                return None
                
            # Compare with baseline or previous snapshot
            compare_with = self.baseline_snapshot if baseline else self.snapshots.get(
                list(self.snapshots.keys())[-2] if len(self.snapshots) > 1 else None,
                self.baseline_snapshot
            )
            
            if not compare_with:
                return None
                
            # Calculate statistics
            stats = snapshot.compare_to(compare_with, 'lineno')
            
            # Format results
            result = []
            for stat in stats[:MEMORY_TOP_STATS]:
                frame = stat.traceback[0]
                filename = os.path.basename(frame.filename)
                line = linecache.getline(frame.filename, frame.lineno).strip()
                result.append({
                    'filename': filename,
                    'lineno': frame.lineno,
                    'line': line,
                    'size': stat.size_diff,
                    'size_human': f"{stat.size_diff / 1024:.1f} KB",
                    'count': stat.count_diff
                })
            
            # Add summary
            total_size = sum(stat.size_diff for stat in stats)
            total_count = sum(stat.count_diff for stat in stats)
            summary = {
                'operation': operation_name or 'latest',
                'compared_to': 'baseline' if baseline else 'previous',
                'total_size': total_size,
                'total_size_human': f"{total_size / 1024 / 1024:.2f} MB",
                'total_objects': total_count
            }
            
            return {
                'summary': summary,
                'details': result
            }
    
    def get_current_memory_usage(self):
        """Get current memory usage."""
        if not self.enabled:
            return None
            
        try:
            # Get current and peak memory usage
            current, peak = tracemalloc.get_traced_memory()
            
            return {
                'current': current,
                'current_human': f"{current / 1024 / 1024:.2f} MB",
                'peak': peak,
                'peak_human': f"{peak / 1024 / 1024:.2f} MB"
            }
        except Exception as e:
            logger.error(f"Failed to get memory usage: {e}")
            return None
    
    def log_memory_usage(self, operation_name=None):
        """Log memory usage for a specific operation."""
        if not self.enabled:
            return
            
        usage = self.get_current_memory_usage()
        if usage:
            logger.info(f"Memory usage {f'for {operation_name}' if operation_name else ''}: "
                       f"Current: {usage['current_human']}, Peak: {usage['peak_human']}")
    
    def stop(self):
        """Stop memory profiling."""
        if self.enabled:
            try:
                tracemalloc.stop()
                logger.info("Memory profiling stopped")
            except Exception as e:
                logger.error(f"Failed to stop memory profiling: {e}")

# Initialize memory profiler
memory_profiler = MemoryProfiler()

class ResourceFetchEvent:
    """Event object for resource fetch operations."""
    
    def __init__(self, event_type, data=None):
        self.event_type = event_type
        self.data = data or {}
        self.timestamp = datetime.now().isoformat()
        
        # Add memory usage information if profiling is enabled
        if MEMORY_PROFILING_ENABLED and MEMORY_PROFILING_AVAILABLE:
            usage = memory_profiler.get_current_memory_usage()
            if usage:
                self.data['memory_usage'] = usage

def prune_attributes(data, resource_type):
    """Remove unnecessary attributes from resource objects to save memory."""
    if not DATA_PRUNING_ENABLED or resource_type not in ESSENTIAL_ATTRIBUTES:
        return data
        
    if isinstance(data, list):
        # Handle list of resources
        essential_attrs = set(ESSENTIAL_ATTRIBUTES.get(resource_type, []))
        
        pruned_data = []
        for item in data:
            if isinstance(item, dict):
                # Only keep essential attributes
                pruned_item = {k: v for k, v in item.items() if k in essential_attrs}
                pruned_data.append(pruned_item)
            else:
                # Non-dict items (unlikely) are kept as is
                pruned_data.append(item)
        
        return pruned_data
    
    elif isinstance(data, dict):
        # Handle single resource
        essential_attrs = set(ESSENTIAL_ATTRIBUTES.get(resource_type, []))
        return {k: v for k, v in data.items() if k in essential_attrs}
    
    # Return unchanged for unsupported types
    return data

def batch_process(items, batch_size, processor_func, *args, **kwargs):
    """Process items in batches to reduce peak memory usage."""
    results = []
    
    # Process items in batches
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        
        # Process this batch
        batch_results = processor_func(batch, *args, **kwargs)
        
        # Append batch results to overall results
        if batch_results:
            results.extend(batch_results)
            
        # Explicitly clear batch references to free memory
        if EXPLICIT_GC:
            del batch
            gc.collect()
    
    return results

class VSphereHierarchicalLoader:
    """
    Hierarchical loader for vSphere resources using background threads.
    
    This class implements a staged loading approach:
    1. Datacenter list (fast)
    2. Clusters per datacenter (medium)
    3. Resources per cluster (slow, on-demand)
    
    All operations are performed in background threads to avoid blocking the UI.
    Memory optimization techniques are applied to reduce RAM usage.
    """
    
    def __init__(self, 
                server=None, 
                username=None, 
                password=None, 
                timeout=None,
                datacenters_filter=None,
                auto_sync=True,
                sync_interval=1800,  # 30 minutes default
                memory_optimization=True):
        """Initialize the hierarchical loader."""
        self.server = server or os.environ.get('VSPHERE_SERVER')
        self.username = username or os.environ.get('VSPHERE_USER')
        self.password = password or os.environ.get('VSPHERE_PASSWORD')
        self.timeout = timeout or int(os.environ.get('VSPHERE_TIMEOUT', '30'))
        self.datacenters_filter = datacenters_filter or self._get_datacenter_filter()
        self.auto_sync = auto_sync
        self.sync_interval = sync_interval
        self.memory_optimization = memory_optimization
        
        # Resource state
        # Use WeakValueDictionary for resources to allow GC to reclaim memory
        self.datacenters = []
        self.clusters_by_dc = {}
        self.resources_by_cluster = {}
        
        # Lazy-loading trackers
        self._lazy_loaded_datacenters = False
        self._lazy_loading_datacenters = False
        
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
            'last_sync': None,
            'memory_profiling': MEMORY_PROFILING_ENABLED and MEMORY_PROFILING_AVAILABLE
        }
        
        # Thread management
        self.lock = threading.RLock()
        self.worker_threads = []
        self.shutdown_event = threading.Event()
        
        # Event queue for callbacks
        self.event_queue = queue.Queue()
        self.event_listeners = []
        
        # Keep track of active worker threads for memory leak prevention
        self._active_workers = weakref.WeakSet()
        
        # Start event processor thread
        self.event_thread = Thread(target=self._process_events, daemon=True)
        self.event_thread.start()
        
        # Start background sync thread if auto_sync enabled
        if self.auto_sync:
            self.sync_thread = Thread(target=self._background_sync_worker, daemon=True)
            self.sync_thread.start()
            self._active_workers.add(self.sync_thread)
            self.worker_threads.append(self.sync_thread)
        
        # Ensure cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)
        
        # Take initial memory snapshot if profiling enabled
        if MEMORY_PROFILING_ENABLED and MEMORY_PROFILING_AVAILABLE:
            memory_profiler.take_snapshot("loader_init")
        
        # Try to load from cache initially
        self._load_from_cache()
        
        # Perform initial lazy loading if enabled
        if LAZY_LOADING_ENABLED and not self._lazy_loaded_datacenters and not self._lazy_loading_datacenters:
            self._lazy_loading_datacenters = True
            self._start_lazy_loading_thread()
    
    def _start_lazy_loading_thread(self):
        """Start a thread for lazy loading initial data."""
        if LAZY_LOADING_ENABLED:
            lazy_thread = Thread(target=self._lazy_load_initial_data, daemon=True)
            lazy_thread.start()
            self._active_workers.add(lazy_thread)
    
    def _lazy_load_initial_data(self):
        """Lazily load initial data in background."""
        try:
            # First, try to get datacenters
            if not self.datacenters:
                logger.debug("Starting lazy loading of datacenters")
                self.get_datacenters(force_load=True)
                
                # Take memory snapshot after datacenter load
                if MEMORY_PROFILING_ENABLED and MEMORY_PROFILING_AVAILABLE:
                    memory_profiler.take_snapshot("lazy_load_datacenters")
                    memory_profiler.log_memory_usage("lazy_load_datacenters")
                
                # After loading datacenters, pre-load first datacenter's clusters
                if self.datacenters and not self.status['is_syncing']:
                    first_dc = self.datacenters[0]['name']
                    logger.debug(f"Lazy loading clusters for datacenter: {first_dc}")
                    self.get_clusters(first_dc, force_load=False)  # Start background loading
                    
                self._lazy_loaded_datacenters = True
        except Exception as e:
            logger.error(f"Error during lazy loading: {str(e)}")
        finally:
            self._lazy_loading_datacenters = False
    
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
            
            # Run garbage collection after processing events if explicit GC enabled
            if EXPLICIT_GC and len(self._active_workers) > 5:  # Only run GC when we have many active threads
                gc.collect()
    
    def _add_event(self, event_type, data=None):
        """Add an event to the queue."""
        event = ResourceFetchEvent(event_type, data)
        self.event_queue.put(event)
    
    def _is_valid_json_file(self, file_path):
        """Validate if a file contains valid JSON data."""
        try:
            with open(file_path, 'r') as f:
                # Only read a small portion first to validate structure
                start_content = f.read(1024)
                if not start_content.strip().startswith('{'):
                    return False
                
                # Reset file pointer
                f.seek(0)
                
                # Try to parse JSON
                json.load(f)
            return True
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in cache file: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error validating JSON file: {str(e)}")
            return False
    
    def _load_from_cache(self):
        """Load the hierarchical data from cache with robust error handling."""
        try:
            if not os.path.exists(HIERARCHY_CACHE_FILE):
                logger.info("Cache file does not exist")
                return False
                
            # Validate file age
            file_age = time.time() - os.path.getmtime(HIERARCHY_CACHE_FILE)
            if file_age >= CACHE_TTL:
                logger.info(f"Cache file too old: {file_age:.1f} seconds (TTL: {CACHE_TTL})")
                return False
            
            # Validate JSON before attempting to load
            if not self._is_valid_json_file(HIERARCHY_CACHE_FILE):
                logger.warning("Cache file contains invalid JSON, removing corrupted file")
                try:
                    # Create a backup of corrupted file for debugging
                    backup_path = f"{HIERARCHY_CACHE_FILE}.corrupted"
                    shutil.copy2(HIERARCHY_CACHE_FILE, backup_path)
                    logger.info(f"Created backup of corrupted cache at: {backup_path}")
                    
                    # Remove corrupted file
                    os.remove(HIERARCHY_CACHE_FILE)
                except Exception as backup_err:
                    logger.error(f"Error backing up corrupted cache: {str(backup_err)}")
                return False
            
            # Load cache data
            with open(HIERARCHY_CACHE_FILE, 'r') as f:
                try:
                    cached_data = json.load(f)
                except json.JSONDecodeError as json_err:
                    # This shouldn't happen since we already validated the JSON,
                    # but handle it just in case
                    logger.error(f"JSON decode error when loading cache: {str(json_err)}")
                    return False
            
            # Validate minimum required data
            if not isinstance(cached_data, dict) or 'datacenters' not in cached_data:
                logger.warning("Cache file missing required data structure")
                return False
            
            with self.lock:
                # Apply data pruning if enabled
                self.datacenters = prune_attributes(cached_data.get('datacenters', []), 'datacenters')
                
                # Process clusters by datacenter
                self.clusters_by_dc = {}
                for dc_name, clusters in cached_data.get('clusters_by_dc', {}).items():
                    self.clusters_by_dc[dc_name] = prune_attributes(clusters, 'clusters')
                
                # Process resources by cluster
                self.resources_by_cluster = {}
                for cluster_id, resources in cached_data.get('resources_by_cluster', {}).items():
                    # Process each resource type within the cluster resources
                    pruned_resources = {}
                    for res_type, res_items in resources.items():
                        if res_type in ESSENTIAL_ATTRIBUTES and isinstance(res_items, list):
                            pruned_resources[res_type] = prune_attributes(res_items, res_type)
                        else:
                            pruned_resources[res_type] = res_items
                    self.resources_by_cluster[cluster_id] = pruned_resources
                
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
            
            # Take memory snapshot after loading cache
            if MEMORY_PROFILING_ENABLED and MEMORY_PROFILING_AVAILABLE:
                memory_profiler.take_snapshot("load_from_cache")
                memory_profiler.log_memory_usage("load_from_cache")
            
            # Emit event for cache loaded
            self._add_event('cache_loaded', {
                'datacenters_count': len(self.datacenters),
                'clusters_count': sum(len(clusters) for clusters in self.clusters_by_dc.values()),
                'resources_count': len(self.resources_by_cluster)
            })
            
            return True
        except Exception as e:
            logger.error(f"Error loading cache: {str(e)}")
            
            # If there was an error loading the cache, let's ensure we don't use corrupted data
            with self.lock:
                self.datacenters = []
                self.clusters_by_dc = {}
                self.resources_by_cluster = {}
            
            # Attempt to delete the corrupted file
            try:
                if os.path.exists(HIERARCHY_CACHE_FILE):
                    # Create a backup first
                    backup_path = f"{HIERARCHY_CACHE_FILE}.error"
                    shutil.copy2(HIERARCHY_CACHE_FILE, backup_path)
                    os.remove(HIERARCHY_CACHE_FILE)
                    logger.info(f"Removed corrupted cache file (backup at: {backup_path})")
            except Exception as cleanup_err:
                logger.error(f"Error cleaning up corrupted cache: {str(cleanup_err)}")
            
            return False
    
    def _check_cache_directory_permissions(self):
        """Check if the cache directory exists and is writable, create if necessary."""
        try:
            # Check if directory exists, create if not
            if not os.path.exists(CACHE_DIR):
                try:
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    logger.info(f"Created cache directory: {CACHE_DIR}")
                except (OSError, PermissionError) as e:
                    logger.error(f"Failed to create cache directory: {str(e)}")
                    return False
            
            # Check if directory is writable by attempting to create a test file
            test_file = os.path.join(CACHE_DIR, ".test_write")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)  # Clean up test file
                return True
            except (OSError, PermissionError) as e:
                logger.error(f"Cache directory is not writable: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking cache directory permissions: {str(e)}")
            return False
    
    def _save_to_cache(self):
        """Save the hierarchical data to cache with permission handling."""
        # Check if cache directory is writable first
        if not self._check_cache_directory_permissions():
            logger.warning("Skipping cache save - directory not writable")
            return False
            
        try:
            with self.lock:
                cache_data = {
                    'datacenters': self.datacenters,
                    'clusters_by_dc': self.clusters_by_dc,
                    'resources_by_cluster': self.resources_by_cluster,
                    'timestamp': datetime.now().isoformat()
                }
            
            # First write to a temporary file, then rename to avoid partial writes
            temp_file = f"{HIERARCHY_CACHE_FILE}.tmp"
            with CACHE_LOCK:
                with open(temp_file, 'w') as f:
                    json.dump(cache_data, f, indent=2)
                
                # Atomic rename to final location
                import shutil
                shutil.move(temp_file, HIERARCHY_CACHE_FILE)
                    
            logger.info("Saved hierarchy to cache")
            return True
            
        except PermissionError as e:
            logger.error(f"Permission denied when saving to cache: {str(e)}")
            # Log helpful debugging information
            try:
                import os, pwd, grp
                stat_info = os.stat(CACHE_DIR)
                uid = stat_info.st_uid
                gid = stat_info.st_gid
                user = pwd.getpwuid(uid).pw_name
                group = grp.getgrgid(gid).gr_name
                mode = oct(stat_info.st_mode)[-3:]
                logger.error(f"Cache directory owned by {user}:{group}, mode {mode}")
            except Exception as debug_error:
                logger.error(f"Error getting debug info: {debug_error}")
            return False
            
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
            # Make sure we're only processing dictionaries (guard against string values)
            dc_clusters = []
            for c in clusters:
                if isinstance(c, dict) and c.get('datacenter') == datacenter_name:
                    dc_clusters.append(c)
                elif isinstance(c, str):
                    logger.warning(f"Unexpected string value in clusters data: {c}")
            
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
                        # Avoid blocking operations that can cause worker timeouts
                        instance = vsphere_cluster_resources.get_instance()
                        
                        # Set a flag to track connection 
                        connection_success = False
                        templates = []
                        
                        try:
                            # Connect with shorter timeout
                            connection_success = instance.connect(timeout=10)
                            
                            if connection_success:
                                # Get only critical quick resources - skip templates (high timeout risk)
                                try:
                                    # Find the cluster object with timeout protection
                                    cluster_obj = None
                                    container = instance.content.viewManager.CreateContainerView(
                                        instance.content.rootFolder, [vim.ClusterComputeResource], True)
                                    
                                    for cluster in container.view:
                                        if str(cluster._moId) == cluster_id:
                                            cluster_obj = cluster
                                            break
                                    
                                    container.Destroy()
                                    
                                    if cluster_obj:
                                        try:
                                            # Start with default placeholder template for immediate display
                                            templates = [{
                                                'id': os.environ.get('TEMPLATE_UUID', 'vm-11682491'),
                                                'name': 'RHEL 9 Template (Loading in background...)',
                                                'guest_os': 'rhel9_64Guest',
                                                'cpu_count': 2,
                                                'memory_mb': 4096
                                            }]
                                            
                                            # Get fast resources first
                                            logger.info(f"Retrieving datastores for cluster: {cluster_name or cluster_id}")
                                            resources['datastores'] = instance.get_datastores_by_cluster(cluster_obj)
                                            
                                            logger.info(f"Retrieving networks for cluster: {cluster_name or cluster_id}")
                                            resources['networks'] = instance.get_networks_by_cluster(cluster_obj)
                                            
                                            # Get resource pools (usually just one per cluster)
                                            logger.info(f"Retrieving resource pools for cluster: {cluster_name or cluster_id}")
                                            resources['resource_pools'] = instance.get_resource_pools_by_cluster(cluster_obj)
                                            
                                            # Skip template retrieval - it's slow and causes timeout issues
                                            # We'll use a placeholder and load real ones in background
                                            resources['templates'] = templates
                                            
                                            # Filter out local datastores (containing "_local" in name)
                                            if resources.get('datastores'):
                                                original_count = len(resources['datastores'])
                                                resources['datastores'] = [
                                                    ds for ds in resources['datastores'] 
                                                    if "_local" not in ds['name']
                                                ]
                                                filtered_count = len(resources['datastores'])
                                                logger.info(f"Filtered datastores for cluster {resources.get('cluster_name', 'Unknown')}: {original_count} → {filtered_count}")
                                        except Exception as inner_e:
                                            logger.error(f"Error in resource retrieval: {str(inner_e)}")
                                            # Continue with partial data
                                except Exception as e:
                                    logger.error(f"Error retrieving critical resources: {str(e)}")
                                    # Continue with partial data
                        except Exception as conn_error:
                            logger.error(f"Connection error: {str(conn_error)}")
                        finally:
                            # Always disconnect if connected
                            if connection_success:
                                try:
                                    instance.disconnect()
                                except Exception as disc_error:
                                    logger.error(f"Error disconnecting: {str(disc_error)}")
                        
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
                        'templates': [{
                            'id': os.environ.get('TEMPLATE_UUID', 'vm-11682491'),
                            'name': 'RHEL 9 Template (Loading...)',
                            'guest_os': 'rhel9_64Guest',
                            'cpu_count': 2,
                            'memory_mb': 4096
                        }],
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
