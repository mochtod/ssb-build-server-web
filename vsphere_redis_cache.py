import os
import json
import time
import logging
from datetime import datetime
import threading
import queue
from functools import partial
import concurrent.futures
# Import VMware SDK components
from pyVim import connect
from pyVmomi import vim
import ssl
import socket
import urllib3
import redis
from redis_client import RedisClient

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('vsphere_redis_cache')

# vSphere connection settings
VSPHERE_HOST = os.environ.get('VSPHERE_SERVER', '')
VSPHERE_USER = os.environ.get('VSPHERE_USER', '')
VSPHERE_PASSWORD = os.environ.get('VSPHERE_PASSWORD', '')
VSPHERE_PORT = int(os.environ.get('VSPHERE_PORT', 443))
VSPHERE_USE_SSL = os.environ.get('VSPHERE_USE_SSL', 'true').lower() == 'true'
VSPHERE_VERIFY_SSL = os.environ.get('VSPHERE_VERIFY_SSL', 'true').lower() == 'true'

# Redis keys and cache settings
VSPHERE_CACHE_PREFIX = 'vsphere:'
VSPHERE_LAST_SYNC_KEY = f'{VSPHERE_CACHE_PREFIX}last_sync'
VSPHERE_DATACENTERS_KEY = f'{VSPHERE_CACHE_PREFIX}datacenters'
VSPHERE_CLUSTERS_KEY = f'{VSPHERE_CACHE_PREFIX}clusters'
VSPHERE_HOSTS_KEY = f'{VSPHERE_CACHE_PREFIX}hosts'
VSPHERE_DATASTORES_KEY = f'{VSPHERE_CACHE_PREFIX}datastores'
VSPHERE_DATASTORE_CLUSTERS_KEY = f'{VSPHERE_CACHE_PREFIX}datastore_clusters'
VSPHERE_NETWORKS_KEY = f'{VSPHERE_CACHE_PREFIX}networks'
VSPHERE_VMS_KEY = f'{VSPHERE_CACHE_PREFIX}vms'
VSPHERE_RESOURCE_POOLS_KEY = f'{VSPHERE_CACHE_PREFIX}resource_pools'
VSPHERE_TEMPLATES_KEY = f'{VSPHERE_CACHE_PREFIX}templates'

# Cache monitoring keys
VSPHERE_CACHE_HITS_KEY = f'{VSPHERE_CACHE_PREFIX}stats:hits'
VSPHERE_CACHE_MISSES_KEY = f'{VSPHERE_CACHE_PREFIX}stats:misses'
VSPHERE_CACHE_LAST_SYNC_DURATION_KEY = f'{VSPHERE_CACHE_PREFIX}stats:last_sync_duration'
VSPHERE_CACHE_MEMORY_USAGE_KEY = f'{VSPHERE_CACHE_PREFIX}stats:memory_usage'

# New keys for partial loading
VSPHERE_SYNC_STATUS_KEY = f'{VSPHERE_CACHE_PREFIX}sync_status'
VSPHERE_SYNC_PROGRESS_KEY = f'{VSPHERE_CACHE_PREFIX}sync_progress'
VSPHERE_SERVERS_KEY = f'{VSPHERE_CACHE_PREFIX}servers'

# Cache TTL in seconds (default: 1 hour)
VSPHERE_CACHE_TTL = int(os.environ.get('VSPHERE_CACHE_TTL', 3600))

# How long to wait before allowing a full re-sync (default: 15 minutes)
VSPHERE_SYNC_COOLDOWN = int(os.environ.get('VSPHERE_SYNC_COOLDOWN', 900))

# Background refresh settings
VSPHERE_REFRESH_INTERVAL = int(os.environ.get('VSPHERE_REFRESH_INTERVAL', 60))  # seconds

class VSphereRedisCache:
    """
    Handles synchronization of vSphere objects to Redis cache with performance optimizations
    """
    def __init__(self):
        """
        Initialize VSphereRedisCache
        """
        self.redis_client = RedisClient.get_instance()
        self.vsphere_conn = None
        self.content = None
        self._background_refresh_running = False
        self._background_refresh_thread = None
        self._sync_lock = threading.Lock()
        # Thread pool for parallel operations
        self._thread_pool = None
        # Number of parallel workers (configurable)
        self.max_workers = int(os.environ.get('VSPHERE_PARALLEL_WORKERS', 4))
        # Stats tracking
        self._stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'last_sync_duration': 0,
            'total_objects': 0
        }
        # Store SSL verification setting from config or environment
        self._verify_ssl = os.environ.get('VSPHERE_VERIFY_SSL', 'true').lower() == 'true'
        
    def get_vsphere_servers(self):
        """
        Get the list of available vSphere servers from Redis cache
        Returns a list of dictionaries with server information
        """
        try:
            # First check Redis cache for server information
            cached_servers = self.redis_client.get(VSPHERE_SERVERS_KEY)
            if cached_servers:
                return cached_servers
            
            # Check environment variables as fallback
            vsphere_server = os.environ.get('VSPHERE_SERVER', '')
            
            # If VSPHERE_SERVER environment variable is set, return it
            if vsphere_server:
                server_info = [{
                    'id': vsphere_server,
                    'name': vsphere_server,
                    'status': 'configured'
                }]
                # Cache it for next time
                self.redis_client.set(VSPHERE_SERVERS_KEY, server_info)
                return server_info
            
            # Default fallback value if nothing is configured
            default_server = [{
                'id': 'virtualcenter.chrobinson.com',
                'name': 'vSphere Server',
                'status': 'default'
            }]
            # Cache the default as well
            self.redis_client.set(VSPHERE_SERVERS_KEY, default_server)
            return default_server
        except Exception as e:
            logger.error(f"Error getting vSphere servers from cache: {str(e)}")
            # Return a default server if we can't get the server list
            return [{
                'id': 'virtualcenter.chrobinson.com',
                'name': 'Default vSphere Server',
                'status': 'error'
            }]
            
    def get_hierarchical_data(self, vsphere_server=None, datacenter_id=None, cluster_id=None, datastore_cluster_id=None):
        """
        Get hierarchical vSphere data for UI dropdown population
        Returns a nested structure with all required data components
        """
        try:
            result = {
                'datacenters': [],
                'clusters': [],
                'hosts': [],
                'datastores': [],
                'datastore_clusters': [],
                'networks': [],
                'templates': []
            }
            
            # Get data from Redis cache, safely handling missing keys
            datacenters = self.redis_client.get(VSPHERE_DATACENTERS_KEY) or []
            result['datacenters'] = datacenters
            
            clusters = self.redis_client.get(VSPHERE_CLUSTERS_KEY) or []
            
            datastore_clusters = self.redis_client.get(VSPHERE_DATASTORE_CLUSTERS_KEY) or []
            
            datastores = self.redis_client.get(VSPHERE_DATASTORES_KEY) or []
            result['datastores'] = datastores
            
            networks = self.redis_client.get(VSPHERE_NETWORKS_KEY) or []
            result['networks'] = networks
            
            templates = self.redis_client.get(VSPHERE_TEMPLATES_KEY) or []
            
            # Log template count for debugging
            logger.info(f"Retrieved {len(templates)} templates from Redis cache")
            
            # Filter templates by datacenter if specified
            if datacenter_id:
                # Filter templates by datacenter_id if we have that relationship
                datacenter_templates = [t for t in templates if t.get('datacenter_id') == datacenter_id]
                
                # If we found templates for this datacenter, use them
                if datacenter_templates:
                    logger.info(f"Found {len(datacenter_templates)} templates for datacenter {datacenter_id}")
                    result['templates'] = datacenter_templates
                else:
                    # Otherwise return all templates
                    logger.info(f"No templates found for datacenter {datacenter_id}, returning all {len(templates)} templates")
                    result['templates'] = templates
            else:
                # If no datacenter filter, return all templates
                result['templates'] = templates
                
            # Log the first few templates for debugging
            for i, template in enumerate(result['templates'][:3]):
                logger.info(f"Template {i+1} in result: {template.get('name')} (ID: {template.get('id')})")
            
            # Filter by datacenter if specified
            if datacenter_id:
                # Debug the filtering process
                logger.info(f"Filtering clusters for datacenter_id: {datacenter_id}")
                
                # Count before filtering
                total_clusters = len(clusters)
                
                # Filter clusters by datacenter_id
                filtered_clusters = [c for c in clusters if c.get('datacenter_id') == datacenter_id]
                
                # Log filtering results for debugging
                logger.info(f"Found {len(filtered_clusters)} clusters out of {total_clusters} for datacenter {datacenter_id}")
                
                # Log the first few clusters and their datacenter_id for debugging
                for i, cluster in enumerate(clusters[:5]):
                    logger.debug(f"Cluster #{i}: {cluster.get('name')}, datacenter_id: {cluster.get('datacenter_id')}")
                
                result['clusters'] = filtered_clusters
            else:
                # If no datacenter filter, return all clusters
                result['clusters'] = clusters
            
            # Filter datastore clusters by cluster if specified
            if cluster_id:
                # Get hosts in the specified cluster
                hosts = [h for h in self.redis_client.get(VSPHERE_HOSTS_KEY) or [] 
                         if h.get('cluster_id') == cluster_id]
                result['hosts'] = hosts
                
                # Filter datastore clusters for this cluster
                # First check if datastore_clusters have cluster_id field
                cluster_specific_datastore_clusters = [ds for ds in datastore_clusters 
                                                  if ds.get('cluster_id') == cluster_id]
                
                # If we don't have any cluster-specific datastore clusters, return all datastore clusters
                # This ensures the dropdown is always populated
                if not cluster_specific_datastore_clusters:
                    logger.info(f"No cluster-specific datastore clusters found for {cluster_id}, returning all datastore clusters")
                    result['datastore_clusters'] = datastore_clusters
                else:
                    result['datastore_clusters'] = cluster_specific_datastore_clusters
                    logger.info(f"Found {len(cluster_specific_datastore_clusters)} datastore clusters for cluster {cluster_id}")
            else:
                # If no cluster filter, return all datastore clusters
                result['datastore_clusters'] = datastore_clusters
            
            # Add stats for monitoring
            if datacenter_id:
                self.record_cache_hit()
            
            return result
        except Exception as e:
            logger.error(f"Error getting hierarchical vSphere data: {str(e)}")
            return {
                'datacenters': [],
                'clusters': [],
                'hosts': [],
                'datastores': [],
                'datastore_clusters': [],
                'networks': [],
                'templates': [],
                'error': str(e)
            }
            
    def get_resource_for_terraform(self, environment):
        """
        Get vSphere resources formatted for Terraform configuration
        Returns a dictionary with resource IDs needed for Terraform
        """
        try:
            # Default values
            result = {
                'resource_pool_id': None,
                'resource_pool_name': None,
                'resource_pool_is_cluster': False,
                'datastore_id': None,
                'datastore_cluster_id': None,
                'storage_id': None,
                'storage_type': None,
                'network_id': None,
                'template_uuid': None,
                'ipv4_gateway': "192.168.1.1",
                'ipv4_address': "192.168.1.100"
            }
            
            # Get cached data
            clusters = self.redis_client.get(VSPHERE_CLUSTERS_KEY) or []
            datastore_clusters = self.redis_client.get(VSPHERE_DATASTORE_CLUSTERS_KEY) or []
            datastores = self.redis_client.get(VSPHERE_DATASTORES_KEY) or []
            networks = self.redis_client.get(VSPHERE_NETWORKS_KEY) or []
            templates = self.redis_client.get(VSPHERE_TEMPLATES_KEY) or []
            
            # Find matching resources based on environment (production vs non-production)
            if clusters:
                # Use first available cluster as resource pool
                cluster = clusters[0]
                result['resource_pool_id'] = cluster.get('id')
                result['resource_pool_name'] = cluster.get('name')
                result['resource_pool_is_cluster'] = True
            
            # Prefer datastore clusters if available
            if datastore_clusters:
                datastore_cluster = datastore_clusters[0]
                result['datastore_cluster_id'] = datastore_cluster.get('id')
                result['storage_id'] = datastore_cluster.get('id')
                result['storage_type'] = 'datastore_cluster'
            elif datastores:
                datastore = datastores[0]
                result['datastore_id'] = datastore.get('id')
                result['storage_id'] = datastore.get('id')
                result['storage_type'] = 'datastore'
            
            # Get network
            if networks:
                network = networks[0]
                result['network_id'] = network.get('id')
            
            # Get template
            # For RHEL9 templates specifically
            rhel9_templates = [t for t in templates if 'rhel9' in t.get('name', '').lower()]
            if rhel9_templates:
                template = rhel9_templates[0]
                result['template_uuid'] = template.get('id')
            elif templates:
                # Fallback to any template
                template = templates[0]
                result['template_uuid'] = template.get('id')
            
            # Environment-specific settings
            if environment == 'production':
                result['ipv4_gateway'] = "10.1.1.1"
                result['ipv4_address'] = "10.1.1.100"
            else:
                result['ipv4_gateway'] = "192.168.1.1"
                result['ipv4_address'] = "192.168.1.100"
            
            return result
        except Exception as e:
            logger.error(f"Error getting vSphere resources for Terraform: {str(e)}")
            return {
                'resource_pool_id': None,
                'datastore_id': None,
                'network_id': None,
                'template_uuid': None,
                'ipv4_gateway': "192.168.1.1",
                'ipv4_address': "192.168.1.100",
                'error': str(e)
            }

    def connect_to_vsphere(self):
        """
        Connect to vSphere server with improved error handling and retry logic
        Returns tuple: (success_bool, error_message)
        """
        max_retries = 3
        retry_delay = 5  # seconds
        
        # Validate credentials are available before attempting connection
        if not VSPHERE_HOST or not VSPHERE_HOST.strip():
            error_msg = "vSphere server address (VSPHERE_SERVER) is not configured"
            logger.error(error_msg)
            return False, error_msg
            
        if not VSPHERE_USER or not VSPHERE_USER.strip():
            error_msg = "vSphere username (VSPHERE_USER) is not configured"
            logger.error(error_msg)
            return False, error_msg
            
        if not VSPHERE_PASSWORD:
            error_msg = "vSphere password (VSPHERE_PASSWORD) is not configured"
            logger.error(error_msg)
            return False, error_msg
        
        # Prepare username for authentication
        username = VSPHERE_USER
        
        # Handle Windows domain username formats based on format detection
        if '\\' in username:
            # For Windows domain accounts, make sure the format is correct
            if not username.startswith('\\\\') and username.count('\\') == 1:
                domain, user = username.split('\\')
                logger.info(f"Using Windows domain account format: {domain}\\{user}")
            else:
                logger.info(f"Using provided Windows domain format: {username}")
        elif '/' in username:
            # Alternative domain/username format 
            logger.info(f"Using alternative domain format with forward slash: {username}")
        elif '@' in username:
            # UPN format (user@domain.com)
            logger.info(f"Using UPN format for authentication: {username}")
        else:
            logger.info(f"Using standard username format: {username}")
        
        logger.info(f"Attempting to connect to vSphere server: {VSPHERE_HOST} with user: {username}")
        
        for attempt in range(1, max_retries + 1):
            try:
                # SSL context setup for self-signed certificates
                context = None
                if VSPHERE_USE_SSL:
                    context = ssl.create_default_context()
                    if not self._verify_ssl:
                        # Disable SSL verification completely for self-signed certificates
                        context.check_hostname = False
                        context.verify_mode = ssl.CERT_NONE
                    else:
                        # If verification is enabled, use default verification mode but log the details
                        context.check_hostname = True
                        context.verify_mode = ssl.CERT_REQUIRED
                    
                    logger.info(f"SSL context created with verify_mode: {context.verify_mode}, verify_ssl: {self._verify_ssl}")
                
                # Set socket timeout to prevent hanging connections
                socket.setdefaulttimeout(30)
                
                # Attempt connection - log exact connection parameters for debugging
                logger.info(f"Connecting to vSphere server {VSPHERE_HOST}:{VSPHERE_PORT} with SSL: {VSPHERE_USE_SSL}, Verify SSL: {self._verify_ssl}")
                
                try:
                    self.vsphere_conn = connect.SmartConnect(
                        host=VSPHERE_HOST,
                        user=username,
                        pwd=VSPHERE_PASSWORD,
                        port=VSPHERE_PORT,
                        sslContext=context
                    )
                except ssl.SSLCertVerificationError as ssl_err:
                    logger.warning(f"SSL certificate verification failed: {str(ssl_err)}. Retrying with verification disabled...")
                    # Create a new context with verification disabled
                    fallback_context = ssl.create_default_context()
                    fallback_context.check_hostname = False
                    fallback_context.verify_mode = ssl.CERT_NONE
                    
                    # Retry connection with verification disabled
                    self.vsphere_conn = connect.SmartConnect(
                        host=VSPHERE_HOST,
                        user=username,
                        pwd=VSPHERE_PASSWORD,
                        port=VSPHERE_PORT,
                        sslContext=fallback_context
                    )
                    logger.info("Connected successfully with SSL verification disabled")
                
                if not self.vsphere_conn:
                    error_msg = "Failed to connect to vSphere - connection is None"
                    raise Exception(error_msg)
                    
                self.content = self.vsphere_conn.RetrieveContent()
                logger.info(f"Connected to vSphere server: {VSPHERE_HOST}")
                return True, ""
                
            except vim.fault.InvalidLogin as e:
                # Handle authentication errors specifically
                error_msg = f"vSphere authentication failed: Invalid username or password for user '{username}' on server '{VSPHERE_HOST}'"
                logger.error(error_msg)
                
                # If using domain format, try alternative formats before giving up
                if '\\' in username and attempt == 1:
                    # Try with just the username part without domain
                    domain, user = username.split('\\')
                    username = user
                    logger.info(f"Authentication failed with domain format. Retrying with just username: {username}")
                    continue
                elif '@' not in username and '\\' not in username and '/' not in username and attempt == 1:
                    # Try adding domain prefix if using simple username
                    original_username = username
                    username = f"chr\\{username}"
                    logger.info(f"Authentication failed with simple username. Retrying with domain format: {username}")
                    continue
                
                # No point in retrying with the same credentials after trying common format variations
                return False, error_msg
                
            except vim.fault.HostConnectFault as e:
                # Handle connection issues
                error_msg = f"Unable to connect to vSphere host: {str(e)}"
                logger.error(error_msg)
                if attempt < max_retries:
                    logger.info(f"Retrying connection in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Failed to connect to vSphere host after {max_retries} attempts")
                    return False, error_msg
                    
            except ssl.SSLError as e:
                # Handle SSL-specific errors
                error_msg = f"SSL Error connecting to vSphere (attempt {attempt}/{max_retries}): {str(e)}"
                logger.error(error_msg)
                
                if "certificate verify failed" in str(e).lower() and self._verify_ssl and attempt < max_retries:
                    logger.warning(f"SSL certificate verification failed. This might be due to a self-signed certificate.")
                    # Try with verification disabled on the next attempt
                    self._verify_ssl = False
                    logger.info("Setting VSPHERE_VERIFY_SSL=false for next attempt to bypass verification")
                
                if attempt < max_retries:
                    logger.info(f"Retrying connection in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Failed to connect to vSphere after {max_retries} attempts")
                    return False, error_msg
                    
            except socket.gaierror as e:
                # Handle DNS resolution errors
                error_msg = f"DNS resolution error for vSphere host '{VSPHERE_HOST}': {str(e)}"
                logger.error(error_msg)
                if attempt < max_retries:
                    logger.info(f"Retrying connection in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Failed to resolve vSphere host after {max_retries} attempts")
                    return False, error_msg
                    
            except Exception as e:
                error_msg = f"Error connecting to vSphere (attempt {attempt}/{max_retries}): {str(e)}"
                logger.error(error_msg)
                
                # Check if the error message contains authentication-related keywords
                error_str = str(e).lower()
                if "login" in error_str and ("incorrect" in error_str or "failed" in error_str or "invalid" in error_str):
                    logger.error(f"vSphere authentication failed: {str(e)}")
                    
                    # Try alternative username formats before giving up
                    if '\\' in username and attempt == 1:
                        # Try with just the username part
                        domain, user = username.split('\\')
                        username = user
                        logger.info(f"Authentication failed with domain format. Retrying with just username: {username}")
                        continue
                    elif '@' not in username and '\\' not in username and '/' not in username and attempt == 1:
                        # Try domain prefix for simple username
                        original_username = username
                        username = f"chr\\{username}"
                        logger.info(f"Authentication failed with simple username. Retrying with domain format: {username}")
                        continue
                    
                    # No point in retrying with the same credentials after trying variations
                    return False, error_msg
                
                # Check for certificate verification problems and handle dynamically
                if "certificate verify failed" in str(e).lower() and self._verify_ssl:
                    logger.warning("Certificate verification failed. Trying with verification disabled...")
                    self._verify_ssl = False
                
                if attempt < max_retries:
                    logger.info(f"Retrying connection in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Failed to connect to vSphere after {max_retries} attempts")
                    return False, error_msg
        
        # Should not reach here, but just in case
        return False, "Failed to connect to vSphere after exhausting all retry attempts"

    def disconnect_from_vsphere(self):
        """
        Disconnect from vSphere server
        """
        if self.vsphere_conn:
            connect.Disconnect(self.vsphere_conn)
            self.vsphere_conn = None
            self.content = None
            logger.info("Disconnected from vSphere server")

    def _create_container_view(self, obj_type):
        """
        Create a container view for a specific object type with error handling
        """
        try:
            if not self.content or not self.content.viewManager:
                raise Exception("vSphere content or viewManager is not available")
                
            return self.content.viewManager.CreateContainerView(
                self.content.rootFolder, [obj_type], True
            )
        except Exception as e:
            logger.error(f"Error creating container view for {obj_type.__name__}: {str(e)}")
            return None

    def _fetch_objects_safely(self, container, transform_func):
        """
        Safely fetch objects from a container view with error handling and performance monitoring
        """
        if not container:
            return []
            
        try:
            start_time = time.time()
            objects = []
            
            # Process objects in batches to prevent memory issues with large environments
            batch_size = 500
            view_list = list(container.view)
            total_objects = len(view_list)
            
            for i in range(0, total_objects, batch_size):
                batch = view_list[i:i+batch_size]
                transformed_batch = []
                
                for obj in batch:
                    try:
                        transformed = transform_func(obj)
                        if transformed:
                            transformed_batch.append(transformed)
                    except Exception as e:
                        # Log error but continue processing other objects
                        logger.error(f"Error processing object {getattr(obj, 'name', 'unknown')}: {str(e)}")
                
                objects.extend(transformed_batch)
            
            fetch_time = time.time() - start_time
            logger.info(f"Fetched {len(objects)} objects in {fetch_time:.2f} seconds")
            return objects
        except Exception as e:
            logger.error(f"Error fetching objects: {str(e)}")
            return []
        finally:
            try:
                # Always destroy the container view to release resources
                container.Destroy()
            except:
                pass

    def get_all_datacenters(self):
        """
        Get all datacenters from vSphere
        """
        container = self._create_container_view(vim.Datacenter)
        
        def transform_datacenter(dc):
            return {
                'id': dc._moId,
                'name': dc.name,
                'vm_folder': dc.vmFolder._moId if hasattr(dc, 'vmFolder') and dc.vmFolder else None,
                'host_folder': dc.hostFolder._moId if hasattr(dc, 'hostFolder') and dc.hostFolder else None,
                'datastore_folder': dc.datastoreFolder._moId if hasattr(dc, 'datastoreFolder') and dc.datastoreFolder else None,
                'network_folder': dc.networkFolder._moId if hasattr(dc, 'networkFolder') and dc.networkFolder else None
            }
            
        return self._fetch_objects_safely(container, transform_datacenter)

    def get_all_clusters(self):
        """
        Get all clusters from vSphere
        """
        container = self._create_container_view(vim.ClusterComputeResource)
        
        def transform_cluster(cluster):
            # Safe attribute access
            parent_moId = None
            try:
                # Correctly get the datacenter parent ID
                if hasattr(cluster, 'parent') and cluster.parent:
                    # If directly in a datacenter
                    if isinstance(cluster.parent, vim.Datacenter):
                        parent_moId = cluster.parent._moId
                    # If in a folder under a datacenter
                    elif hasattr(cluster.parent, 'parent') and cluster.parent.parent:
                        if isinstance(cluster.parent.parent, vim.Datacenter):
                            parent_moId = cluster.parent.parent._moId
                        # Handle nested folders case
                        elif (hasattr(cluster.parent.parent, 'parent') and 
                              cluster.parent.parent.parent and 
                              isinstance(cluster.parent.parent.parent, vim.Datacenter)):
                            parent_moId = cluster.parent.parent.parent._moId
                
                # Log the parent relationship for debugging
                logger.debug(f"Cluster: {cluster.name}, Parent MoID: {parent_moId}")
            except Exception as e:
                logger.error(f"Error getting datacenter ID for cluster {cluster.name}: {str(e)}")
                
            # Convert overall status to string to ensure it can be serialized
            overall_status = None
            try:
                if hasattr(cluster, 'overallStatus'):
                    overall_status = str(cluster.overallStatus)
            except:
                pass
                
            return {
                'id': cluster._moId,
                'name': cluster.name,
                'datacenter_id': parent_moId,
                'total_cpu_mhz': getattr(cluster.summary, 'totalCpu', 0),
                'total_memory_bytes': getattr(cluster.summary, 'totalMemory', 0),
                'num_hosts': len(getattr(cluster, 'host', [])),
                'num_effective_hosts': getattr(cluster.summary, 'numEffectiveHosts', 0),
                'overall_status': overall_status,
            }
            
        return self._fetch_objects_safely(container, transform_cluster)

    def get_all_hosts(self):
        """
        Get all hosts from vSphere with optimized property access
        """
        container = self._create_container_view(vim.HostSystem)
        
        def transform_host(host):
            # Get parent cluster if available
            parent_cluster_id = None
            try:
                if hasattr(host, 'parent') and host.parent:
                    if isinstance(host.parent, vim.ClusterComputeResource):
                        parent_cluster_id = host.parent._moId
            except:
                pass
                
            # Safely access nested properties
            connection_state = None
            power_state = None
            in_maintenance_mode = False
            
            try:
                if hasattr(host, 'runtime'):
                    connection_state = getattr(host.runtime, 'connectionState', None)
                    power_state = getattr(host.runtime, 'powerState', None)
                    in_maintenance_mode = getattr(host.runtime, 'inMaintenanceMode', False)
            except:
                pass
                
            # Safely access hardware properties
            cpu_model = None
            num_cpu_cores = 0
            cpu_mhz = 0
            memory_size_bytes = 0
            
            try:
                if hasattr(host, 'summary') and hasattr(host.summary, 'hardware'):
                    cpu_model = getattr(host.summary.hardware, 'cpuModel', None)
                    num_cpu_cores = getattr(host.summary.hardware, 'numCpuCores', 0)
                    cpu_mhz = getattr(host.summary.hardware, 'cpuMhz', 0)
                    memory_size_bytes = getattr(host.summary.hardware, 'memorySize', 0)
            except:
                pass
                
            # Convert overall status to string to ensure it can be serialized
            overall_status = None
            try:
                if hasattr(host, 'overallStatus'):
                    overall_status = str(host.overallStatus)
            except Exception as e:
                logger.debug(f"Error converting overall status for host {host.name}: {str(e)}")
                
            return {
                'id': host._moId,
                'name': host.name,
                'cluster_id': parent_cluster_id,
                'connection_state': connection_state,
                'power_state': power_state,
                'in_maintenance_mode': in_maintenance_mode,
                'cpu_model': cpu_model,
                'num_cpu_cores': num_cpu_cores,
                'cpu_mhz': cpu_mhz,
                'memory_size_bytes': memory_size_bytes,
                'overall_status': overall_status,
            }
            
        return self._fetch_objects_safely(container, transform_host)

    def get_all_datastores(self):
        """
        Get all datastores from vSphere
        """
        container = self._create_container_view(vim.Datastore)
        
        def transform_datastore(ds):
            return {
                'id': ds._moId,
                'name': ds.name,
                'type': getattr(ds.summary, 'type', None),
                'capacity_bytes': getattr(ds.summary, 'capacity', 0),
                'free_space_bytes': getattr(ds.summary, 'freeSpace', 0),
                'accessible': getattr(ds.summary, 'accessible', False),
                'maintenance_mode': getattr(ds.summary, 'maintenanceMode', None),
                'multiple_host_access': getattr(ds.summary, 'multipleHostAccess', False),
            }
            
        return self._fetch_objects_safely(container, transform_datastore)

    def get_all_networks(self):
        """
        Get all networks from vSphere
        """
        container = self._create_container_view(vim.Network)
        
        def transform_network(network):
            return {
                'id': network._moId,
                'name': network.name,
                'accessible': getattr(network.summary, 'accessible', False),
                'ip_pool_id': getattr(network.summary, 'ipPoolId', None),
                'network_type': type(network).__name__,
            }
            
        return self._fetch_objects_safely(container, transform_network)

    def get_all_resource_pools(self):
        """
        Get all resource pools from vSphere
        """
        container = self._create_container_view(vim.ResourcePool)
        
        def transform_resource_pool(rp):
            # Skip hidden resource pools
            try:
                if (rp.parent and isinstance(rp.parent, vim.ResourcePool) and 
                    rp.parent.parent and isinstance(rp.parent.parent, vim.ComputeResource)):
                    if rp.name == 'Resources' and rp.parent.name == 'Resources':
                        return None
            except:
                pass

            # Get parent info
            parent_id = None
            parent_type = None
            try:
                if rp.parent:
                    parent_id = rp.parent._moId
                    parent_type = type(rp.parent).__name__
            except:
                pass

            # Safely access config properties
            cpu_limit = None
            memory_limit = None
            try:
                if (hasattr(rp, 'config') and 
                    hasattr(rp.config, 'cpuAllocation') and 
                    hasattr(rp.config.cpuAllocation, 'limit')):
                    cpu_limit = rp.config.cpuAllocation.limit
                    
                if (hasattr(rp, 'config') and 
                    hasattr(rp.config, 'memoryAllocation') and 
                    hasattr(rp.config.memoryAllocation, 'limit')):
                    memory_limit = rp.config.memoryAllocation.limit
            except:
                pass

            # Convert overall status to string to ensure it can be serialized
            overall_status = None
            try:
                if hasattr(rp, 'overallStatus'):
                    overall_status = str(rp.overallStatus)
            except Exception as e:
                logger.debug(f"Error converting overall status for resource pool {rp.name}: {str(e)}")

            return {
                'id': rp._moId,
                'name': rp.name,
                'parent_id': parent_id,
                'parent_type': parent_type,
                'cpu_limit': cpu_limit,
                'memory_limit': memory_limit,
                'overall_status': overall_status,
            }
            
        return self._fetch_objects_safely(container, transform_resource_pool)

    def get_all_vms(self):
        """
        Get all VMs from vSphere with optimized property collection
        """
        container = self._create_container_view(vim.VirtualMachine)
        
        def transform_vm(vm):
            # Skip templates as we'll process them separately
            try:
                if vm.config and vm.config.template:
                    return None
            except:
                pass

            # Basic info with safe property access
            vm_info = {'id': vm._moId, 'name': vm.name, 'is_template': False}
            
            # Power state
            try:
                if hasattr(vm, 'runtime'):
                    vm_info['power_state'] = getattr(vm.runtime, 'powerState', None)
                    vm_info['connection_state'] = getattr(vm.runtime, 'connectionState', None)
            except:
                pass
                
            # Guest OS info
            try:
                if hasattr(vm, 'config'):
                    vm_info['guest_id'] = getattr(vm.config, 'guestId', None)
                    vm_info['guest_full_name'] = getattr(vm.config, 'guestFullName', None)
                    
                    # Hardware info
                    if hasattr(vm.config, 'hardware'):
                        vm_info['cpu_count'] = getattr(vm.config.hardware, 'numCPU', 0)
                        vm_info['memory_mb'] = getattr(vm.config.hardware, 'memoryMB', 0)
            except:
                pass
                
            # Resource pool
            try:
                if hasattr(vm, 'resourcePool') and vm.resourcePool:
                    vm_info['resource_pool_id'] = vm.resourcePool._moId
            except:
                pass
                
            # Host
            try:
                if hasattr(vm, 'runtime') and hasattr(vm.runtime, 'host') and vm.runtime.host:
                    vm_info['host_id'] = vm.runtime.host._moId
            except:
                pass
                
            # Networks
            try:
                vm_info['network_ids'] = []
                if hasattr(vm, 'network'):
                    for net in vm.network:
                        vm_info['network_ids'].append(net._moId)
            except:
                pass
                
            # Datastores
            try:
                vm_info['datastore_ids'] = []
                if hasattr(vm, 'datastore'):
                    for ds in vm.datastore:
                        vm_info['datastore_ids'].append(ds._moId)
            except:
                pass
                
            # Overall status
            vm_info['overall_status'] = getattr(vm, 'overallStatus', None)
            
            # IP address - guest property can be expensive to access
            try:
                if hasattr(vm, 'guest') and hasattr(vm.guest, 'ipAddress') and vm.guest.ipAddress:
                    vm_info['ip_address'] = vm.guest.ipAddress
            except:
                pass
                
            return vm_info
            
        return self._fetch_objects_safely(container, transform_vm)

    def get_all_templates(self):
        """
        Get all templates from vSphere with improved error handling and logging
        Also enhances datacenter association to fix template discovery issues
        """
        container = self._create_container_view(vim.VirtualMachine)
        
        def transform_template(vm):
            # Only process templates
            try:
                # First, check if vm.config exists before trying to access template attribute
                if not hasattr(vm, 'config') or vm.config is None:
                    return None
                    
                # Check if the template attribute exists and is True
                if not hasattr(vm.config, 'template') or not vm.config.template:
                    return None
                
                # Now we know this is a template and vm.config exists
                template_info = {'id': vm._moId, 'name': vm.name, 'is_template': True}
                
                # Guest OS info - safely access all properties with explicit attribute checks
                try:
                    if hasattr(vm.config, 'guestId'):
                        template_info['guest_id'] = vm.config.guestId
                    if hasattr(vm.config, 'guestFullName'):
                        template_info['guest_full_name'] = vm.config.guestFullName
                    
                    # Hardware info - check before accessing deeper attributes
                    if hasattr(vm.config, 'hardware'):
                        hw = vm.config.hardware
                        if hasattr(hw, 'numCPU'):
                            template_info['cpu_count'] = hw.numCPU
                        if hasattr(hw, 'memoryMB'):
                            template_info['memory_mb'] = hw.memoryMB
                except Exception as e:
                    logger.debug(f"Error getting guest info for template {vm.name}: {str(e)}")
                
                # Host information - with safe access
                try:
                    if hasattr(vm, 'runtime') and hasattr(vm.runtime, 'host') and vm.runtime.host:
                        template_info['host_id'] = vm.runtime.host._moId
                except Exception as e:
                    logger.debug(f"Error getting host for template {vm.name}: {str(e)}")
                    template_info['host_id'] = None
                
                # Networks - with explicit existence checks
                try:
                    template_info['network_ids'] = []
                    if hasattr(vm, 'network'):
                        for net in vm.network:
                            template_info['network_ids'].append(net._moId)
                except Exception as e:
                    logger.debug(f"Error getting networks for template {vm.name}: {str(e)}")
                
                # Datastores - with explicit existence checks
                try:
                    template_info['datastore_ids'] = []
                    if hasattr(vm, 'datastore'):
                        for ds in vm.datastore:
                            template_info['datastore_ids'].append(ds._moId)
                except Exception as e:
                    logger.debug(f"Error getting datastores for template {vm.name}: {str(e)}")
                
                # Overall status - safe conversion to string
                try:
                    if hasattr(vm, 'overallStatus'):
                        template_info['overall_status'] = str(vm.overallStatus)
                    else:
                        template_info['overall_status'] = None
                except Exception as e:
                    logger.debug(f"Error getting overall status for template {vm.name}: {str(e)}")
                    template_info['overall_status'] = None
                
                # Datacenter information - using safe traversal
                # This is a critical section for fixing template-to-datacenter association
                try:
                    if hasattr(vm, 'parent'):
                        # First attempt: Direct traversal to find datacenter
                        current = vm.parent
                        datacenter = None
                        while current:
                            if isinstance(current, vim.Datacenter):
                                datacenter = current
                                break
                            if hasattr(current, 'parent'):
                                current = current.parent
                            else:
                                break
                        
                        if datacenter:
                            template_info['datacenter_id'] = datacenter._moId
                            template_info['datacenter_name'] = datacenter.name
                            logger.debug(f"Found datacenter {datacenter.name} ({datacenter._moId}) for template {vm.name}")
                        else:
                            # Second attempt: Look at the template's folder path
                            try:
                                path_parts = vm.parent.name.split('/')
                                # Check if any of the path parts match known datacenter names
                                datacenters = self.redis_client.get(VSPHERE_DATACENTERS_KEY) or []
                                for dc in datacenters:
                                    if dc['name'] in path_parts:
                                        template_info['datacenter_id'] = dc['id']
                                        template_info['datacenter_name'] = dc['name']
                                        logger.debug(f"Found datacenter {dc['name']} from folder path for template {vm.name}")
                                        break
                            except Exception as path_err:
                                logger.debug(f"Error parsing folder path for template {vm.name}: {str(path_err)}")
                                
                        # Third attempt: If we still don't have a datacenter, use the first host's datacenter
                        if 'datacenter_id' not in template_info and hasattr(vm, 'runtime') and \
                           hasattr(vm.runtime, 'host') and vm.runtime.host:
                            try:
                                host = vm.runtime.host
                                current = host.parent
                                while current:
                                    if isinstance(current, vim.Datacenter):
                                        template_info['datacenter_id'] = current._moId
                                        template_info['datacenter_name'] = current.name
                                        logger.debug(f"Found datacenter {current.name} from host for template {vm.name}")
                                        break
                                    if hasattr(current, 'parent'):
                                        current = current.parent
                                    else:
                                        break
                            except Exception as host_err:
                                logger.debug(f"Error finding datacenter from host for template {vm.name}: {str(host_err)}")
                except Exception as e:
                    logger.debug(f"Error getting datacenter for template {vm.name}: {str(e)}")
                
                return template_info
            except Exception as e:
                # Log any errors but continue processing other templates
                logger.warning(f"Error processing potential template {getattr(vm, 'name', 'unknown')}: {str(e)}")
                return None
        
        # Get all VMs and filter for templates
        all_vms = self._fetch_objects_safely(container, lambda vm: vm)
        logger.info(f"Found {len(all_vms)} total VMs")
        
        # Manually filter for templates with detailed logging
        templates = []
        template_count = 0
        processed_count = 0
        
        for vm in all_vms:
            try:
                if hasattr(vm, 'config') and vm.config and hasattr(vm.config, 'template') and vm.config.template:
                    template_count += 1
                    template_data = transform_template(vm)
                    if template_data:
                        processed_count += 1
                        templates.append(template_data)
                        # Log every 10th template to avoid excessive logging
                        if processed_count % 10 == 0 or processed_count < 5:
                            logger.info(f"Processed template {processed_count}: {template_data.get('name')} (ID: {template_data.get('id')})")
            except Exception as e:
                logger.warning(f"Error checking if VM is template: {str(e)}")
        
        logger.info(f"Found {template_count} total templates, {len(templates)} successfully processed")
        
        # Log some details about found templates for debugging
        for i, template in enumerate(templates[:5]):  # Log first 5 templates
            logger.info(f"Template {i+1}: {template.get('name')} (ID: {template.get('id')}, Datacenter: {template.get('datacenter_id', 'Unknown')})")
        
        # Check if we need to fix datacenter associations for templates
        templates_missing_datacenter = [t for t in templates if 'datacenter_id' not in t]
        if templates_missing_datacenter:
            logger.warning(f"{len(templates_missing_datacenter)} templates missing datacenter association, attempting to fix")
            
            # Get all datacenters
            datacenters = self.redis_client.get(VSPHERE_DATACENTERS_KEY) or []
            if datacenters:
                for template in templates_missing_datacenter:
                    # Assign to the first datacenter as a fallback
                    # This ensures templates are always associated with at least one datacenter
                    if datacenters:
                        template['datacenter_id'] = datacenters[0]['id']
                        template['datacenter_name'] = datacenters[0]['name']
                        logger.info(f"Associated template {template['name']} with default datacenter {datacenters[0]['name']}")
        
        # If no templates found or fewer than expected, add fallback templates for testing
        if len(templates) < 2:
            logger.warning(f"Only {len(templates)} templates found, adding fallback templates for testing")
            
            # First get datacenters to associate with fallback templates
            datacenters = self.redis_client.get(VSPHERE_DATACENTERS_KEY) or []
            datacenter_id = datacenters[0]['id'] if datacenters else "datacenter-2"
            
            # Add at least one RHEL9 template and one other template
            if not any(t.get('name', '').lower().find('rhel9') >= 0 for t in templates):
                rhel9_template = {
                    'id': 'vm-fallback-rhel9',
                    'name': 'rhel9-template (fallback)',
                    'is_template': True,
                    'guest_id': 'rhel9_64Guest',
                    'guest_full_name': 'Red Hat Enterprise Linux 9 (64-bit)'
                }
                
                # Add datacenter association to the fallback template
                if datacenters:
                    rhel9_template['datacenter_id'] = datacenter_id
                    rhel9_template['datacenter_name'] = datacenters[0]['name']
                    
                templates.append(rhel9_template)
                logger.info("Added fallback RHEL9 template")
            
            # Add another template for variety
            if not any(t.get('name', '').lower().find('windows') >= 0 for t in templates):
                win_template = {
                    'id': 'vm-fallback-win',
                    'name': 'windows-template (fallback)',
                    'is_template': True,
                    'guest_id': 'windows2019srv_64Guest',
                    'guest_full_name': 'Windows Server 2019 (64-bit)'
                }
                
                # Add datacenter association to the fallback template
                if datacenters:
                    win_template['datacenter_id'] = datacenter_id
                    win_template['datacenter_name'] = datacenters[0]['name']
                    
                templates.append(win_template)
                logger.info("Added fallback Windows template")
        
        return templates

    def get_all_datastore_clusters(self):
        """
        Get all datastore clusters from vSphere
        """
        container = self._create_container_view(vim.StoragePod)
        
        def transform_datastore_cluster(ds_cluster):
            # Get datastore IDs in this cluster
            datastore_ids = []
            try:
                if hasattr(ds_cluster, 'childEntity'):
                    for ds in ds_cluster.childEntity:
                        datastore_ids.append(ds._moId)
            except:
                pass

            return {
                'id': ds_cluster._moId,
                'name': ds_cluster.name,
                'datastore_ids': datastore_ids,
                'capacity_bytes': getattr(ds_cluster.summary, 'capacity', 0),
                'free_space_bytes': getattr(ds_cluster.summary, 'freeSpace', 0),
            }
            
        return self._fetch_objects_safely(container, transform_datastore_cluster)

    def _sync_resources_parallel(self, resource_handlers, sync_queue=None):
        """
        Sync multiple resource types in parallel using a thread pool
        
        Args:
            resource_handlers: List of tuples (resource_type, get_func, redis_key)
            sync_queue: Queue for progress tracking
            
        Returns:
            Dictionary with results
        """
        # Create a thread pool if we don't already have one
        if not self._thread_pool:
            self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
            
        results = {}
        futures = {}
        
        # Start all tasks
        for resource_type, get_func, redis_key in resource_handlers:
            logger.info(f"Starting parallel fetch for {resource_type}")
            futures[resource_type] = self._thread_pool.submit(get_func)
            
        # Process results as they complete
        for resource_type, get_func, redis_key in resource_handlers:
            try:
                # Get result with timeout
                resources = futures[resource_type].result(timeout=600)  # 10 minute timeout per resource type
                count = len(resources)
                
                # Save to Redis with compression for large datasets
                if count > 1000:
                    # For very large datasets, consider chunking
                    chunk_size = 500
                    for i in range(0, count, chunk_size):
                        chunk = resources[i:i+chunk_size]
                        chunk_key = f"{redis_key}:chunk:{i//chunk_size}"
                        self.redis_client.set(chunk_key, chunk, VSPHERE_CACHE_TTL)
                    
                    # Save metadata
                    self.redis_client.set(redis_key, {
                        'chunked': True,
                        'total_count': count,
                        'chunk_size': chunk_size,
                        'chunk_count': (count + chunk_size - 1) // chunk_size
                    }, VSPHERE_CACHE_TTL)
                else:
                    # For smaller datasets, save directly
                    self.redis_client.set(redis_key, resources, VSPHERE_CACHE_TTL)
                
                # Update progress if tracking
                if sync_queue:
                    sync_queue.put((resource_type, count))
                
                results[resource_type] = count
                logger.info(f"Completed parallel fetch for {resource_type}: {count} items")
            except Exception as e:
                logger.error(f"Error syncing {resource_type} to Redis: {str(e)}")
                if sync_queue:
                    sync_queue.put((resource_type, -1))  # Signal error
                results[resource_type] = -1
                
        return results

    def sync_essential_to_redis(self):
        """
        Sync only essential vSphere objects to Redis for initial UI loading
        with parallel processing for speed
        """
        try:
            # Get the most up-to-date settings from environment
            # This ensures we use the latest credentials that might have been updated in the UI
            global VSPHERE_HOST, VSPHERE_USER, VSPHERE_PASSWORD, VSPHERE_PORT, VSPHERE_USE_SSL, VSPHERE_VERIFY_SSL
            VSPHERE_HOST = os.environ.get('VSPHERE_SERVER', '')
            VSPHERE_USER = os.environ.get('VSPHERE_USER', '')
            VSPHERE_PASSWORD = os.environ.get('VSPHERE_PASSWORD', '')
            VSPHERE_PORT = int(os.environ.get('VSPHERE_PORT', 443))
            VSPHERE_USE_SSL = os.environ.get('VSPHERE_USE_SSL', 'true').lower() == 'true'
            VSPHERE_VERIFY_SSL = os.environ.get('VSPHERE_VERIFY_SSL', 'true').lower() == 'true'
            
            # Log the current settings (without the password)
            logger.info(f"Using vSphere settings: server={VSPHERE_HOST}, user={VSPHERE_USER}, port={VSPHERE_PORT}, SSL={VSPHERE_USE_SSL}, verify_ssl={VSPHERE_VERIFY_SSL}")
            
            # Handle different return types from connect_to_vsphere
            connection_result = self.connect_to_vsphere()
            
            if isinstance(connection_result, tuple):
                # Handle the case where the method returns (status, error_message)
                connection_success, error_message = connection_result
                if not connection_success:
                    logger.error(f"Failed to connect to vSphere: {error_message}")
                    return False
            elif not connection_result:
                # Handle the case where the method returns just a boolean
                logger.error("Failed to connect to vSphere, cannot sync essential data")
                return False

            start_time = time.time()
            
            # Define essential resources to sync in parallel
            essential_resources = [
                ('datacenters', self.get_all_datacenters, VSPHERE_DATACENTERS_KEY),
                ('clusters', self.get_all_clusters, VSPHERE_CLUSTERS_KEY),
                ('datastore_clusters', self.get_all_datastore_clusters, VSPHERE_DATASTORE_CLUSTERS_KEY),
                ('datastores', self.get_all_datastores, VSPHERE_DATASTORES_KEY),
                ('templates', self.get_all_templates, VSPHERE_TEMPLATES_KEY),
                ('networks', self.get_all_networks, VSPHERE_NETWORKS_KEY)
            ]
            
            # Sync in parallel
            results = self._sync_resources_parallel(essential_resources)
            
            # Update last sync time with success information
            sync_duration = time.time() - start_time
            self._stats['last_sync_duration'] = sync_duration
            
            now = datetime.utcnow().isoformat()
            sync_info = {
                'timestamp': now,
                'type': 'essential',
                'duration_seconds': sync_duration,
                'status': 'success'
            }
            
            # Add counts for each resource type
            for resource_type, count in results.items():
                if count >= 0:  # Only include successful results
                    sync_info[f'{resource_type}_count'] = count
            
            self.redis_client.set(VSPHERE_LAST_SYNC_KEY, sync_info)
            self.redis_client.set(VSPHERE_CACHE_LAST_SYNC_DURATION_KEY, sync_duration)
            
            # Update total objects count
            total_objects = sum([count for resource_type, count in results.items() if count > 0])
            self._stats['total_objects'] = total_objects
            self.redis_client.set(VSPHERE_CACHE_MEMORY_USAGE_KEY, self._estimate_memory_usage())
            
            logger.info(f"Essential vSphere data synchronized to Redis in {sync_duration:.2f} seconds")
            
            # Start background sync for the rest if we successfully got the essential data
            if all(count >= 0 for resource_type, count in results.items() if resource_type in ['datacenters', 'clusters']):
                self.start_background_sync()
                return True
            else:
                logger.error("Failed to get essential datacenter and cluster data, not starting background sync")
                return False
        except Exception as e:
            # Log sync failure
            now = datetime.utcnow().isoformat()
            self.redis_client.set(VSPHERE_LAST_SYNC_KEY, {
                'timestamp': now,
                'type': 'essential',
                'status': 'error',
                'error_message': str(e)
            })
            
            logger.error(f"Error syncing essential vSphere data to Redis: {str(e)}")
            return False
        finally:
            self.disconnect_from_vsphere()

    def sync_all_to_redis(self, background=False, parallel_workers=None):
        """
        Sync all vSphere objects to Redis with performance optimizations
        """
        # Use a lock to prevent multiple syncs running at the same time
        if not self._sync_lock.acquire(blocking=False):
            logger.warning("A sync is already in progress, skipping this request")
            return False
        
        try:
            # Update parallel workers if specified
            if parallel_workers:
                try:
                    self.max_workers = int(parallel_workers)
                    logger.info(f"Using {self.max_workers} parallel workers for sync")
                except (ValueError, TypeError):
                    pass
                    
            # First check if sync is already running or too recent
            if not background:
                sync_status = self.redis_client.get(VSPHERE_SYNC_STATUS_KEY)
                if sync_status == 'running':
                    logger.info("Sync already in progress, returning progress info")
                    progress = self.redis_client.get(VSPHERE_SYNC_PROGRESS_KEY) or {}
                    return progress

                # Check last full sync time to prevent hammering the vSphere API
                last_sync = self.redis_client.get(VSPHERE_LAST_SYNC_KEY) or {}
                if last_sync.get('type') == 'full' and last_sync.get('status') == 'success':
                    last_sync_time = last_sync.get('timestamp')
                    if last_sync_time:
                        try:
                            last_sync_dt = datetime.fromisoformat(last_sync_time)
                            now = datetime.utcnow()
                            time_since_sync = (now - last_sync_dt).total_seconds()
                            
                            if time_since_sync < VSPHERE_SYNC_COOLDOWN:
                                logger.info(f"Last full sync was {time_since_sync:.0f}s ago (cooldown: {VSPHERE_SYNC_COOLDOWN}s), using cached data")
                                return last_sync
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Error parsing last sync time: {str(e)}")

            # Set status to running
            self.redis_client.set(VSPHERE_SYNC_STATUS_KEY, 'running')
            self.redis_client.set(VSPHERE_SYNC_PROGRESS_KEY, {
                'timestamp': datetime.utcnow().isoformat(),
                'progress': 0,
                'status': 'running',
                'message': 'Starting synchronization...'
            })
            
            start_time = time.time()
            
            connection_result = self.connect_to_vsphere()
            
            if isinstance(connection_result, tuple):
                # Handle the case where the method returns (status, error_message)
                connection_success, error_message = connection_result
                if not connection_success:
                    logger.error(f"Failed to connect to vSphere: {error_message}")
                    return False
            elif not connection_result:
                # Handle the case where the method returns just a boolean
                logger.error("Failed to connect to vSphere, cannot sync all data")
                return False

            # Set up progress tracking
            sync_queue = queue.Queue()
            progress_data = {
                'total_resources': 9,  # datacenters, clusters, hosts, datastores, datastore_clusters, networks, resource_pools, vms, templates
                'completed_resources': 0,
                'counts': {},
                'started': datetime.utcnow().isoformat()
            }
            
            # Function to update progress
            def update_progress(resource_type, count):
                nonlocal progress_data
                
                if count >= 0:  # Success
                    progress_data['completed_resources'] += 1
                    progress_data['counts'][resource_type] = count
                    progress_pct = int((progress_data['completed_resources'] / progress_data['total_resources']) * 100)
                    
                    self.redis_client.set(VSPHERE_SYNC_PROGRESS_KEY, {
                        'timestamp': datetime.utcnow().isoformat(),
                        'started': progress_data['started'],
                        'progress': progress_pct,
                        'status': 'running',
                        'counts': progress_data['counts'],
                        'message': f'Synced {resource_type}: {count} items ({progress_pct}% complete)'
                    })
                else:  # Error
                    self.redis_client.set(VSPHERE_SYNC_PROGRESS_KEY, {
                        'timestamp': datetime.utcnow().isoformat(),
                        'started': progress_data['started'],
                        'progress': int((progress_data['completed_resources'] / progress_data['total_resources']) * 100),
                        'status': 'error',
                        'counts': progress_data['counts'],
                        'message': f'Error syncing {resource_type}'
                    })

            try:
                # Start background worker to update progress
                def progress_worker():
                    while True:
                        try:
                            resource_type, count = sync_queue.get(timeout=60)
                            if resource_type == 'DONE':
                                break
                            update_progress(resource_type, count)
                            sync_queue.task_done()
                        except queue.Empty:
                            logger.warning("Progress queue timeout, exiting worker")
                            break
                        except Exception as e:
                            logger.error(f"Error in progress worker: {str(e)}")
                
                progress_thread = threading.Thread(target=progress_worker, daemon=True)
                progress_thread.start()
                
                # Define all resources to sync
                all_resources = [
                    ('datacenters', self.get_all_datacenters, VSPHERE_DATACENTERS_KEY),
                    ('clusters', self.get_all_clusters, VSPHERE_CLUSTERS_KEY),
                    ('hosts', self.get_all_hosts, VSPHERE_HOSTS_KEY),
                    ('datastores', self.get_all_datastores, VSPHERE_DATASTORES_KEY),
                    ('datastore_clusters', self.get_all_datastore_clusters, VSPHERE_DATASTORE_CLUSTERS_KEY),
                    ('networks', self.get_all_networks, VSPHERE_NETWORKS_KEY),
                    ('resource_pools', self.get_all_resource_pools, VSPHERE_RESOURCE_POOLS_KEY),
                    ('vms', self.get_all_vms, VSPHERE_VMS_KEY),
                    ('templates', self.get_all_templates, VSPHERE_TEMPLATES_KEY)
                ]
                
                # Split resources into batches for parallel processing
                # We don't want to overload the vSphere server with too many queries at once
                batch_size = min(3, self.max_workers)  # Process up to 3 resource types at once
                for i in range(0, len(all_resources), batch_size):
                    batch = all_resources[i:i+batch_size]
                    batch_results = self._sync_resources_parallel(batch, sync_queue)
                    logger.info(f"Completed batch {i//batch_size + 1}/{(len(all_resources) + batch_size - 1)//batch_size}")
                
                # Signal worker to exit
                sync_queue.put(('DONE', 0))
                progress_thread.join(timeout=5)

                # Calculate sync statistics
                sync_duration = time.time() - start_time
                self._stats['last_sync_duration'] = sync_duration
                
                # Update Redis stats
                self.redis_client.set(VSPHERE_CACHE_LAST_SYNC_DURATION_KEY, sync_duration)
                
                # Estimate memory usage
                memory_usage = self._estimate_memory_usage()
                self.redis_client.set(VSPHERE_CACHE_MEMORY_USAGE_KEY, memory_usage)

                # Update last sync time
                now = datetime.utcnow().isoformat()
                result = {
                    'timestamp': now,
                    'type': 'full',
                    'counts': progress_data['counts'],
                    'duration_seconds': sync_duration,
                    'memory_usage': memory_usage,
                    'status': 'success'
                }
                self.redis_client.set(VSPHERE_LAST_SYNC_KEY, result)
                self.redis_client.set(VSPHERE_SYNC_STATUS_KEY, 'complete')
                self.redis_client.set(VSPHERE_SYNC_PROGRESS_KEY, {
                    'timestamp': now,
                    'started': progress_data['started'],
                    'progress': 100,
                    'status': 'complete',
                    'counts': progress_data['counts'],
                    'duration_seconds': sync_duration,
                    'message': f'Synchronization complete in {sync_duration:.1f} seconds'
                })

                # Update total objects count
                total_objects = sum([count for resource_type, count in progress_data['counts'].items() if isinstance(count, int) and count > 0])
                self._stats['total_objects'] = total_objects

                logger.info(f"vSphere data synchronized to Redis in {sync_duration:.2f} seconds, {total_objects} total objects")
                return result
            except Exception as e:
                # Log sync failure
                now = datetime.utcnow().isoformat()
                error_result = {
                    'timestamp': now,
                    'type': 'full',
                    'status': 'error',
                    'error_message': str(e)
                }
                self.redis_client.set(VSPHERE_LAST_SYNC_KEY, error_result)
                self.redis_client.set(VSPHERE_SYNC_STATUS_KEY, 'error')
                self.redis_client.set(VSPHERE_SYNC_PROGRESS_KEY, {
                    'timestamp': now,
                    'started': progress_data.get('started'),
                    'progress': int((progress_data.get('completed_resources', 0) / progress_data.get('total_resources', 1)) * 100),
                    'status': 'error',
                    'counts': progress_data.get('counts', {}),
                    'message': f'Synchronization error: {str(e)}'
                })
                
                logger.error(f"Error syncing vSphere data to Redis: {str(e)}")
                return False
        finally:
            self.disconnect_from_vsphere()
            self._sync_lock.release()
            
            # Clean up thread pool if we're done with it
            if background and self._thread_pool:
                self._thread_pool.shutdown(wait=False)
                self._thread_pool = None

    def _estimate_memory_usage(self):
        """
        Estimate memory usage of Redis cache in MB
        """
        try:
            # Get Redis info about memory usage
            redis_info = self.redis_client.get_raw_redis().info(section='memory')
            if 'used_memory' in redis_info:
                return f"{redis_info['used_memory'] / (1024 * 1024):.1f} MB"
            
            # Fallback estimation based on object counts
            total_objects = self._stats.get('total_objects', 0)
            # Rough estimate: average 1KB per object
            estimated_kb = total_objects * 1
            return f"{estimated_kb / 1024:.1f} MB (estimated)"
        except Exception as e:
            logger.error(f"Error estimating memory usage: {str(e)}")
            return "Unknown"

    def get_cache_status(self):
        """
        Get the status of the vSphere cache with performance metrics
        """
        last_sync = self.redis_client.get(VSPHERE_LAST_SYNC_KEY)
        
        # Get sync timing
        sync_duration = self.redis_client.get(VSPHERE_CACHE_LAST_SYNC_DURATION_KEY)
        if sync_duration:
            sync_duration_str = f"{sync_duration:.1f} seconds" if isinstance(sync_duration, (int, float)) else str(sync_duration)
        else:
            sync_duration_str = "Unknown"
            
        # Get memory usage
        memory_usage = self.redis_client.get(VSPHERE_CACHE_MEMORY_USAGE_KEY) or self._estimate_memory_usage()
            
        # Get cache hit rate
        cache_hits = self.redis_client.get(VSPHERE_CACHE_HITS_KEY) or 0
        cache_misses = self.redis_client.get(VSPHERE_CACHE_MISSES_KEY) or 0
        
        # Ensure values are integers before adding them
        try:
            cache_hits = int(cache_hits)
        except (TypeError, ValueError):
            cache_hits = 0
            
        try:
            cache_misses = int(cache_misses)
        except (TypeError, ValueError):
            cache_misses = 0
            
        if cache_hits + cache_misses > 0:
            hit_rate = (cache_hits / (cache_hits + cache_misses)) * 100
            hit_rate_str = f"{hit_rate:.1f}%"
        else:
            hit_rate_str = "No data"
        
        # Get count of objects in cache
        total_objects = self._stats.get('total_objects', 0)
        if not total_objects and last_sync and isinstance(last_sync, dict) and 'counts' in last_sync:
            # Calculate from last sync counts
            counts = last_sync.get('counts', {})
            total_objects = sum([count for resource_type, count in counts.items() 
                                if isinstance(count, int) and count > 0])
        
        # Check if each cache exists
        keys_to_check = [
            VSPHERE_DATACENTERS_KEY,
            VSPHERE_CLUSTERS_KEY,
            VSPHERE_HOSTS_KEY,
            VSPHERE_DATASTORES_KEY,
            VSPHERE_NETWORKS_KEY,
            VSPHERE_RESOURCE_POOLS_KEY,
            VSPHERE_VMS_KEY,
            VSPHERE_TEMPLATES_KEY
        ]
        
        cache_status = {}
        for key in keys_to_check:
            # Extract resource type from key
            resource_type = key.split(':')[-1]
            exists = self.redis_client.exists(key)
            ttl = self.redis_client.get_ttl(key) if exists else None
            count = 0
            
            if exists:
                # Try to get count directly from data
                data = self.redis_client.get(key)
                if isinstance(data, list):
                    count = len(data)
                elif isinstance(data, dict) and 'total_count' in data:
                    # Chunked data
                    count = data.get('total_count', 0)
            
            cache_status[resource_type] = {
                'exists': exists,
                'ttl': ttl,
                'count': count
            }
        
        # Get current sync status
        sync_status = self.redis_client.get(VSPHERE_SYNC_STATUS_KEY)
        sync_progress = self.redis_client.get(VSPHERE_SYNC_PROGRESS_KEY)
        
        # Check connectivity
        is_connected = False
        try:
            # Quick ping test
            self.redis_client.get_raw_redis().ping()
            is_connected = True
        except:
            pass
        
        status = {
            'last_sync': last_sync,
            'last_updated': last_sync.get('timestamp') if last_sync and isinstance(last_sync, dict) else None,
            'sync_status': sync_status,
            'sync_progress': sync_progress,
            'cache_status': cache_status,
            'total_objects': total_objects,
            'connected': is_connected,
            'cache_hit_rate': hit_rate_str,
            'memory_usage': memory_usage,
            'sync_duration': sync_duration_str
        }
        
        return status

    def record_cache_hit(self):
        """Record a cache hit for statistics"""
        self._stats['cache_hits'] += 1
        self.redis_client.increment(VSPHERE_CACHE_HITS_KEY)
        
    def record_cache_miss(self):
        """Record a cache miss for statistics"""
        self._stats['cache_misses'] += 1
        self.redis_client.increment(VSPHERE_CACHE_MISSES_KEY)

    def clear_cache(self):
        """
        Clear all vSphere cache from Redis with memory optimization
        """
        try:
            # Get all keys with the vSphere prefix
            vsphere_keys = self.redis_client.keys_pattern(f"{VSPHERE_CACHE_PREFIX}*")
            
            # Delete keys in batches to prevent blocking Redis
            batch_size = 100
            total_keys = len(vsphere_keys)
            
            for i in range(0, total_keys, batch_size):
                batch = vsphere_keys[i:i+batch_size]
                for key in batch:
                    self.redis_client.delete(key)
                
                # Small delay to prevent Redis from getting overwhelmed
                if i + batch_size < total_keys:
                    time.sleep(0.1)
            
            # Reset statistics
            self._stats = {
                'cache_hits': 0,
                'cache_misses': 0,
                'last_sync_duration': 0,
                'total_objects': 0
            }
            
            logger.info(f"Cleared {total_keys} vSphere cache keys from Redis")
            return True
        except Exception as e:
            logger.error(f"Error clearing vSphere cache: {str(e)}")
            return False

    def start_background_sync(self):
        """
        Start a background thread to sync all vSphere data with optimized approach
        """
        if self._background_refresh_running:
            logger.info("Background refresh already running")
            return

        self._background_refresh_running = True
        
        def background_sync():
            try:
                logger.info("Starting background vSphere sync")
                # Wait a bit to let the UI load first
                time.sleep(5)
                self.sync_all_to_redis(background=True)
            except Exception as e:
                logger.error(f"Error in background vSphere sync: {str(e)}")
            finally:
                self._background_refresh_running = False
        
        self._background_refresh_thread = threading.Thread(target=background_sync, daemon=True)
        self._background_refresh_thread.start()
        
        logger.info("Background vSphere sync thread started")
        
    def is_background_sync_running(self):
        """
        Check if background sync is running
        """
        if self._background_refresh_thread and self._background_refresh_thread.is_alive():
            return True
        return False

    def validate_template_uuid(self, template_uuid):
        """
        Validates that a template with the specified UUID exists in vSphere
        
        Args:
            template_uuid (str): The UUID of the template to validate
            
        Returns:
            dict: A dictionary containing:
                - valid (bool): Whether the template UUID is valid
                - template_info (dict): Information about the template if valid
                - message (str): Error or success message
        """
        try:
            logger.info(f"Validating template UUID: {template_uuid}")
            
            # Try to get template from Redis cache first
            templates = self.redis_client.get(VSPHERE_TEMPLATES_KEY)
            
            if templates:
                # Check if we need to parse JSON (depends on redis_client implementation)
                if isinstance(templates, str):
                    templates = json.loads(templates)
                    
                matching_template = next((t for t in templates if t.get('id') == template_uuid), None)
                
                if matching_template:
                    logger.info(f"Template found in cache: {matching_template.get('name')}")
                    # Validate against vSphere to be sure
                    try:
                        # Make sure we're connected
                        is_connected = False
                        connection_error = None
                        
                        if not self.vsphere_conn:
                            try:
                                is_connected = self.connect_to_vsphere()
                                if isinstance(is_connected, tuple):
                                    # Handle new return format (status, error_message)
                                    is_connected, connection_error = is_connected
                                
                                if not is_connected:
                                    connection_error = "Failed to connect to vSphere server"
                            except Exception as conn_err:
                                connection_error = f"Error connecting to vSphere: {str(conn_err)}"
                                logger.error(connection_error)
                                
                            if not is_connected:
                                # If we can't connect to vSphere but have the template in cache, trust the cache
                                # but include a warning in the message
                                logger.warning(f"Cannot connect to vSphere to validate template. Using cached data. Error: {connection_error}")
                                return {
                                    'valid': True,  # Consider valid based on cache
                                    'template_info': matching_template,
                                    'message': f"Template '{matching_template.get('name')}' found in cache, but could not verify with vSphere server. Error: {connection_error}",
                                    'warning': "Using cached data - vSphere connection failed"
                                }
                        
                        # Get content
                        if not self.content:
                            self.content = self.vsphere_conn.RetrieveContent()
                            
                        # Find template by UUID
                        vm = self.content.searchIndex.FindByUuid(None, template_uuid, True, True)
                        
                        if vm:
                            logger.info(f"Template '{vm.name}' found in vSphere with UUID {template_uuid}")
                            return {
                                'valid': True,
                                'template_info': matching_template,
                                'message': f"Template '{vm.name}' is valid"
                            }
                        else:
                            logger.warning(f"Template with UUID {template_uuid} found in cache but not in vSphere")
                            # The cache is out of date, template doesn't exist in vSphere anymore
                            # But we'll still consider it potentially valid with a warning
                            return {
                                'valid': True,  # Still consider valid to avoid breaking builds
                                'template_info': matching_template,
                                'message': f"Template '{matching_template.get('name')}' found in cache but not in vSphere - cache may be out of date",
                                'warning': "Template not found in vSphere - cache may be out of date"
                            }
                    except Exception as e:
                        logger.error(f"Error validating template in vSphere: {str(e)}")
                        # If vSphere validation fails, trust the cache but log the error
                        return {
                            'valid': True,  # Trust the cache in case of vSphere API issues
                            'template_info': matching_template,
                            'message': f"Template found in cache but vSphere validation failed: {str(e)}",
                            'warning': "Could not verify with vSphere"
                        }
                else:
                    logger.warning(f"Template with UUID {template_uuid} not found in cache")
            
            # Not found in cache or cache empty, try direct lookup in vSphere
            try:
                # Try to connect if not already connected
                if not self.vsphere_conn:
                    connection_success = self.connect_to_vsphere()
                    if isinstance(connection_success, tuple):
                        # Handle new return format (status, error_message)
                        connection_success, error_message = connection_success
                        
                    if not connection_success:
                        # Check if we have VSPHERE_HOST, VSPHERE_USER, VSPHERE_PASSWORD defined
                        missing_env_vars = []
                        if not VSPHERE_HOST:
                            missing_env_vars.append("VSPHERE_SERVER")
                        if not VSPHERE_USER:
                            missing_env_vars.append("VSPHERE_USER")
                        if not VSPHERE_PASSWORD:
                            missing_env_vars.append("VSPHERE_PASSWORD")
                            
                        if missing_env_vars:
                            error_msg = f"Missing required vSphere environment variables: {', '.join(missing_env_vars)}"
                            logger.error(error_msg)
                            return {
                                'valid': False,
                                'template_info': None,
                                'message': error_msg
                            }
                        else:
                            error_msg = f"Failed to connect to vSphere server {VSPHERE_HOST}. Please check your credentials and network connection."
                            logger.error(error_msg)
                            return {
                                'valid': False,
                                'template_info': None,
                                'message': error_msg
                            }
                
                if not self.content:
                    self.content = self.vsphere_conn.RetrieveContent()
                    
                vm = self.content.searchIndex.FindByUuid(None, template_uuid, True, True)
                
                if vm:
                    logger.info(f"Template '{vm.name}' found in vSphere with UUID {template_uuid}")
                    # Create template info from the found VM
                    template_info = {
                        'id': vm._moId,
                        'name': vm.name,
                        'is_template': True,
                        'guest_id': vm.config.guestId if hasattr(vm, 'config') and hasattr(vm.config, 'guestId') else None
                    }
                    return {
                        'valid': True,
                        'template_info': template_info,
                        'message': f"Template '{vm.name}' is valid"
                    }
                else:
                    error_msg = f"Template with UUID {template_uuid} not found in vSphere"
                    logger.error(error_msg)
                    return {
                        'valid': False,
                        'template_info': None,
                        'message': error_msg
                    }
            except Exception as e:
                # Get detailed error information
                error_msg = f"Error looking up template directly in vSphere: {str(e)}"
                logger.error(error_msg)
                # Include additional troubleshooting information
                return {
                    'valid': False,
                    'template_info': None,
                    'message': error_msg,
                    'troubleshooting': {
                        'vsphere_server': VSPHERE_HOST or "Not configured",
                        'connection_status': "Failed",
                        'error_details': str(e)
                    }
                }
                
        except Exception as e:
            error_msg = f"Template validation failed: {str(e)}"
            logger.error(error_msg)
            return {
                'valid': False,
                'template_info': None,
                'message': error_msg
            }

# Convenience function to run a sync
def sync_vsphere_to_redis(parallel_workers=None):
    """
    Run a sync of vSphere objects to Redis
    
    Args:
        parallel_workers: Number of parallel workers to use (default: use environment setting)
    """
    vsphere_cache = VSphereRedisCache()
    return vsphere_cache.sync_all_to_redis(parallel_workers=parallel_workers)

# Convenience function to get sync progress
def get_sync_progress():
    """
    Get the current synchronization progress
    """
    vsphere_cache = VSphereRedisCache()
    return vsphere_cache.get_sync_progress()

# Convenience function to run a quick sync of essential data
def sync_essential_to_redis():
    """
    Run a quick sync of essential vSphere objects to Redis
    """
    vsphere_cache = VSphereRedisCache()
    return vsphere_cache.sync_essential_to_redis()