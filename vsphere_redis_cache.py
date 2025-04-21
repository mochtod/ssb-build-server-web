import os
import json
import time
import logging
from datetime import datetime
import threading
import queue
from functools import partial
import pyVmomi
from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect
import ssl
import socket
import urllib3
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

# Redis keys and cache settings
VSPHERE_CACHE_PREFIX = 'vsphere:'
VSPHERE_LAST_SYNC_KEY = f'{VSPHERE_CACHE_PREFIX}last_sync'
VSPHERE_DATACENTERS_KEY = f'{VSPHERE_CACHE_PREFIX}datacenters'
VSPHERE_CLUSTERS_KEY = f'{VSPHERE_CACHE_PREFIX}clusters'
VSPHERE_HOSTS_KEY = f'{VSPHERE_CACHE_PREFIX}hosts'
VSPHERE_DATASTORES_KEY = f'{VSPHERE_CACHE_PREFIX}datastores'
VSPHERE_NETWORKS_KEY = f'{VSPHERE_CACHE_PREFIX}networks'
VSPHERE_VMS_KEY = f'{VSPHERE_CACHE_PREFIX}vms'
VSPHERE_RESOURCE_POOLS_KEY = f'{VSPHERE_CACHE_PREFIX}resource_pools'
VSPHERE_TEMPLATES_KEY = f'{VSPHERE_CACHE_PREFIX}templates'

# New keys for partial loading
VSPHERE_SYNC_STATUS_KEY = f'{VSPHERE_CACHE_PREFIX}sync_status'
VSPHERE_SYNC_PROGRESS_KEY = f'{VSPHERE_CACHE_PREFIX}sync_progress'

# Cache TTL in seconds (default: 1 hour)
VSPHERE_CACHE_TTL = int(os.environ.get('VSPHERE_CACHE_TTL', 3600))

# How long to wait before allowing a full re-sync (default: 15 minutes)
VSPHERE_SYNC_COOLDOWN = int(os.environ.get('VSPHERE_SYNC_COOLDOWN', 900))

# Background refresh settings
VSPHERE_REFRESH_INTERVAL = int(os.environ.get('VSPHERE_REFRESH_INTERVAL', 60))  # seconds

class VSphereRedisCache:
    """
    Handles synchronization of vSphere objects to Redis cache
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

    def connect_to_vsphere(self):
        """
        Connect to vSphere server
        """
        try:
            # SSL context setup for self-signed certificates
            context = None
            if VSPHERE_USE_SSL:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

            self.vsphere_conn = SmartConnect(
                host=VSPHERE_HOST,
                user=VSPHERE_USER,
                pwd=VSPHERE_PASSWORD,
                port=VSPHERE_PORT,
                sslContext=context
            )
            
            if not self.vsphere_conn:
                raise Exception("Failed to connect to vSphere")
                
            self.content = self.vsphere_conn.RetrieveContent()
            logger.info(f"Connected to vSphere server: {VSPHERE_HOST}")
            return True
        except Exception as e:
            logger.error(f"Error connecting to vSphere: {str(e)}")
            return False

    def disconnect_from_vsphere(self):
        """
        Disconnect from vSphere server
        """
        if self.vsphere_conn:
            Disconnect(self.vsphere_conn)
            self.vsphere_conn = None
            self.content = None
            logger.info("Disconnected from vSphere server")

    def get_all_datacenters(self):
        """
        Get all datacenters from vSphere
        """
        try:
            container = self.content.viewManager.CreateContainerView(
                self.content.rootFolder, [vim.Datacenter], True
            )
            datacenters = []
            for dc in container.view:
                datacenters.append({
                    'id': dc._moId,
                    'name': dc.name,
                    'vm_folder': dc.vmFolder._moId if dc.vmFolder else None,
                    'host_folder': dc.hostFolder._moId if dc.hostFolder else None,
                    'datastore_folder': dc.datastoreFolder._moId if dc.datastoreFolder else None,
                    'network_folder': dc.networkFolder._moId if dc.networkFolder else None
                })
            container.Destroy()
            return datacenters
        except Exception as e:
            logger.error(f"Error getting datacenters: {str(e)}")
            return []

    def get_all_clusters(self):
        """
        Get all clusters from vSphere
        """
        try:
            container = self.content.viewManager.CreateContainerView(
                self.content.rootFolder, [vim.ClusterComputeResource], True
            )
            clusters = []
            for cluster in container.view:
                clusters.append({
                    'id': cluster._moId,
                    'name': cluster.name,
                    'datacenter_id': cluster.parent.parent._moId if cluster.parent and cluster.parent.parent else None,
                    'total_cpu_mhz': cluster.summary.totalCpu if hasattr(cluster.summary, 'totalCpu') else 0,
                    'total_memory_bytes': cluster.summary.totalMemory if hasattr(cluster.summary, 'totalMemory') else 0,
                    'num_hosts': len(cluster.host) if hasattr(cluster, 'host') else 0,
                    'num_effective_hosts': cluster.summary.numEffectiveHosts if hasattr(cluster.summary, 'numEffectiveHosts') else 0,
                    'overall_status': cluster.overallStatus if hasattr(cluster, 'overallStatus') else None,
                })
            container.Destroy()
            return clusters
        except Exception as e:
            logger.error(f"Error getting clusters: {str(e)}")
            return []

    def get_all_hosts(self):
        """
        Get all hosts from vSphere
        """
        try:
            container = self.content.viewManager.CreateContainerView(
                self.content.rootFolder, [vim.HostSystem], True
            )
            hosts = []
            for host in container.view:
                # Get parent cluster if available
                parent_cluster_id = None
                if hasattr(host, 'parent') and host.parent:
                    if isinstance(host.parent, vim.ClusterComputeResource):
                        parent_cluster_id = host.parent._moId

                hosts.append({
                    'id': host._moId,
                    'name': host.name,
                    'cluster_id': parent_cluster_id,
                    'connection_state': host.runtime.connectionState if hasattr(host.runtime, 'connectionState') else None,
                    'power_state': host.runtime.powerState if hasattr(host.runtime, 'powerState') else None,
                    'in_maintenance_mode': host.runtime.inMaintenanceMode if hasattr(host.runtime, 'inMaintenanceMode') else False,
                    'cpu_model': host.summary.hardware.cpuModel if hasattr(host.summary, 'hardware') and hasattr(host.summary.hardware, 'cpuModel') else None,
                    'num_cpu_cores': host.summary.hardware.numCpuCores if hasattr(host.summary, 'hardware') and hasattr(host.summary.hardware, 'numCpuCores') else 0,
                    'cpu_mhz': host.summary.hardware.cpuMhz if hasattr(host.summary, 'hardware') and hasattr(host.summary.hardware, 'cpuMhz') else 0,
                    'memory_size_bytes': host.summary.hardware.memorySize if hasattr(host.summary, 'hardware') and hasattr(host.summary.hardware, 'memorySize') else 0,
                    'overall_status': host.overallStatus if hasattr(host, 'overallStatus') else None,
                })
            container.Destroy()
            return hosts
        except Exception as e:
            logger.error(f"Error getting hosts: {str(e)}")
            return []

    def get_all_datastores(self):
        """
        Get all datastores from vSphere
        """
        try:
            container = self.content.viewManager.CreateContainerView(
                self.content.rootFolder, [vim.Datastore], True
            )
            datastores = []
            for ds in container.view:
                datastores.append({
                    'id': ds._moId,
                    'name': ds.name,
                    'type': ds.summary.type if hasattr(ds.summary, 'type') else None,
                    'capacity_bytes': ds.summary.capacity if hasattr(ds.summary, 'capacity') else 0,
                    'free_space_bytes': ds.summary.freeSpace if hasattr(ds.summary, 'freeSpace') else 0,
                    'accessible': ds.summary.accessible if hasattr(ds.summary, 'accessible') else False,
                    'maintenance_mode': ds.summary.maintenanceMode if hasattr(ds.summary, 'maintenanceMode') else None,
                    'multiple_host_access': ds.summary.multipleHostAccess if hasattr(ds.summary, 'multipleHostAccess') else False,
                })
            container.Destroy()
            return datastores
        except Exception as e:
            logger.error(f"Error getting datastores: {str(e)}")
            return []

    def get_all_networks(self):
        """
        Get all networks from vSphere
        """
        try:
            container = self.content.viewManager.CreateContainerView(
                self.content.rootFolder, [vim.Network], True
            )
            networks = []
            for network in container.view:
                networks.append({
                    'id': network._moId,
                    'name': network.name,
                    'accessible': network.summary.accessible if hasattr(network.summary, 'accessible') else False,
                    'ip_pool_id': network.summary.ipPoolId if hasattr(network.summary, 'ipPoolId') else None,
                    'network_type': type(network).__name__,
                })
            container.Destroy()
            return networks
        except Exception as e:
            logger.error(f"Error getting networks: {str(e)}")
            return []

    def get_all_resource_pools(self):
        """
        Get all resource pools from vSphere
        """
        try:
            container = self.content.viewManager.CreateContainerView(
                self.content.rootFolder, [vim.ResourcePool], True
            )
            resource_pools = []
            for rp in container.view:
                # Skip hidden resource pools
                if rp.parent and isinstance(rp.parent, vim.ResourcePool) and rp.parent.parent and isinstance(rp.parent.parent, vim.ComputeResource):
                    if rp.name == 'Resources' and rp.parent.name == 'Resources':
                        continue

                # Get parent info
                parent_id = None
                parent_type = None
                if rp.parent:
                    parent_id = rp.parent._moId
                    parent_type = type(rp.parent).__name__

                resource_pools.append({
                    'id': rp._moId,
                    'name': rp.name,
                    'parent_id': parent_id,
                    'parent_type': parent_type,
                    'cpu_limit': rp.config.cpuAllocation.limit if hasattr(rp.config, 'cpuAllocation') and hasattr(rp.config.cpuAllocation, 'limit') else None,
                    'memory_limit': rp.config.memoryAllocation.limit if hasattr(rp.config, 'memoryAllocation') and hasattr(rp.config.memoryAllocation, 'limit') else None,
                    'overall_status': rp.overallStatus if hasattr(rp, 'overallStatus') else None,
                })
            container.Destroy()
            return resource_pools
        except Exception as e:
            logger.error(f"Error getting resource pools: {str(e)}")
            return []

    def get_all_vms(self):
        """
        Get all VMs from vSphere
        """
        try:
            container = self.content.viewManager.CreateContainerView(
                self.content.rootFolder, [vim.VirtualMachine], True
            )
            vms = []
            for vm in container.view:
                # Skip templates as we'll process them separately
                if vm.config and vm.config.template:
                    continue

                # Get resource pool
                resource_pool_id = None
                if hasattr(vm, 'resourcePool') and vm.resourcePool:
                    resource_pool_id = vm.resourcePool._moId

                # Get host
                host_id = None
                if hasattr(vm, 'runtime') and hasattr(vm.runtime, 'host') and vm.runtime.host:
                    host_id = vm.runtime.host._moId

                # Get network info
                networks = []
                if hasattr(vm, 'network'):
                    for net in vm.network:
                        networks.append(net._moId)

                # Get datastore info
                datastores = []
                if hasattr(vm, 'datastore'):
                    for ds in vm.datastore:
                        datastores.append(ds._moId)

                # Get basic VM info
                vm_info = {
                    'id': vm._moId,
                    'name': vm.name,
                    'power_state': vm.runtime.powerState if hasattr(vm.runtime, 'powerState') else None,
                    'connection_state': vm.runtime.connectionState if hasattr(vm.runtime, 'connectionState') else None,
                    'guest_id': vm.config.guestId if vm.config and hasattr(vm.config, 'guestId') else None,
                    'guest_full_name': vm.config.guestFullName if vm.config and hasattr(vm.config, 'guestFullName') else None,
                    'cpu_count': vm.config.hardware.numCPU if vm.config and hasattr(vm.config, 'hardware') and hasattr(vm.config.hardware, 'numCPU') else 0,
                    'memory_mb': vm.config.hardware.memoryMB if vm.config and hasattr(vm.config, 'hardware') and hasattr(vm.config.hardware, 'memoryMB') else 0,
                    'resource_pool_id': resource_pool_id,
                    'host_id': host_id,
                    'network_ids': networks,
                    'datastore_ids': datastores,
                    'overall_status': vm.overallStatus if hasattr(vm, 'overallStatus') else None,
                    'is_template': False
                }

                # Add IP information if available
                if hasattr(vm, 'guest') and hasattr(vm.guest, 'ipAddress') and vm.guest.ipAddress:
                    vm_info['ip_address'] = vm.guest.ipAddress

                vms.append(vm_info)

            container.Destroy()
            return vms
        except Exception as e:
            logger.error(f"Error getting VMs: {str(e)}")
            return []

    def get_all_templates(self):
        """
        Get all templates from vSphere
        """
        try:
            container = self.content.viewManager.CreateContainerView(
                self.content.rootFolder, [vim.VirtualMachine], True
            )
            templates = []
            for vm in container.view:
                # Only process templates
                if not (vm.config and vm.config.template):
                    continue

                # Get resource pool
                resource_pool_id = None
                if hasattr(vm, 'resourcePool') and vm.resourcePool:
                    resource_pool_id = vm.resourcePool._moId

                # Get host
                host_id = None
                if hasattr(vm, 'runtime') and hasattr(vm.runtime, 'host') and vm.runtime.host:
                    host_id = vm.runtime.host._moId

                # Get network info
                networks = []
                if hasattr(vm, 'network'):
                    for net in vm.network:
                        networks.append(net._moId)

                # Get datastore info
                datastores = []
                if hasattr(vm, 'datastore'):
                    for ds in vm.datastore:
                        datastores.append(ds._moId)

                templates.append({
                    'id': vm._moId,
                    'name': vm.name,
                    'guest_id': vm.config.guestId if vm.config and hasattr(vm.config, 'guestId') else None,
                    'guest_full_name': vm.config.guestFullName if vm.config and hasattr(vm.config, 'guestFullName') else None,
                    'cpu_count': vm.config.hardware.numCPU if vm.config and hasattr(vm.config, 'hardware') and hasattr(vm.config.hardware, 'numCPU') else 0,
                    'memory_mb': vm.config.hardware.memoryMB if vm.config and hasattr(vm.config, 'hardware') and hasattr(vm.config.hardware, 'memoryMB') else 0,
                    'host_id': host_id,
                    'network_ids': networks,
                    'datastore_ids': datastores,
                    'overall_status': vm.overallStatus if hasattr(vm, 'overallStatus') else None,
                    'is_template': True
                })

            container.Destroy()
            return templates
        except Exception as e:
            logger.error(f"Error getting templates: {str(e)}")
            return []

    def _sync_resource_to_redis(self, resource_type, get_resource_func, resource_key, sync_queue=None, progress_callback=None):
        """
        Sync a specific resource type to Redis
        """
        try:
            start = time.time()
            resources = get_resource_func()
            logger.info(f"Fetched {len(resources)} {resource_type} in {time.time() - start:.2f} seconds")
            self.redis_client.set(resource_key, resources, VSPHERE_CACHE_TTL)
            logger.info(f"Saved {len(resources)} {resource_type} to Redis")
            
            # Update progress if callback provided
            if sync_queue and progress_callback:
                sync_queue.put((resource_type, len(resources)))
            
            return len(resources)
        except Exception as e:
            logger.error(f"Error syncing {resource_type} to Redis: {str(e)}")
            if sync_queue and progress_callback:
                sync_queue.put((resource_type, -1))  # Signal error
            return 0

    def sync_essential_to_redis(self):
        """
        Sync only essential vSphere objects to Redis for initial UI loading
        """
        if not self.connect_to_vsphere():
            logger.error("Failed to connect to vSphere, cannot sync essential data")
            return False

        try:
            # Only get datacenters, clusters and templates (what's needed for UI)
            datacenters = self.get_all_datacenters()
            self.redis_client.set(VSPHERE_DATACENTERS_KEY, datacenters, VSPHERE_CACHE_TTL)
            
            clusters = self.get_all_clusters()
            self.redis_client.set(VSPHERE_CLUSTERS_KEY, clusters, VSPHERE_CACHE_TTL)
            
            templates = self.get_all_templates()
            self.redis_client.set(VSPHERE_TEMPLATES_KEY, templates, VSPHERE_CACHE_TTL)
            
            networks = self.get_all_networks()
            self.redis_client.set(VSPHERE_NETWORKS_KEY, networks, VSPHERE_CACHE_TTL)

            # Update last sync time (partial)
            now = datetime.utcnow().isoformat()
            self.redis_client.set(VSPHERE_LAST_SYNC_KEY, {
                'timestamp': now,
                'type': 'essential',
                'datacenters_count': len(datacenters),
                'clusters_count': len(clusters),
                'networks_count': len(networks),
                'templates_count': len(templates),
                'status': 'success'
            })

            logger.info(f"Essential vSphere data synchronized to Redis: {len(datacenters)} datacenters, "
                       f"{len(clusters)} clusters, {len(networks)} networks, {len(templates)} templates")
            
            # Start background sync for the rest
            self.start_background_sync()
            
            return True
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

    def sync_all_to_redis(self, background=False):
        """
        Sync all vSphere objects to Redis
        """
        # Use a lock to prevent multiple syncs running at the same time
        if not self._sync_lock.acquire(blocking=False):
            logger.warning("A sync is already in progress, skipping this request")
            return False
        
        try:
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
            
            if not self.connect_to_vsphere():
                logger.error("Failed to connect to vSphere, cannot sync data")
                self.redis_client.set(VSPHERE_SYNC_STATUS_KEY, 'error')
                self.redis_client.set(VSPHERE_SYNC_PROGRESS_KEY, {
                    'timestamp': datetime.utcnow().isoformat(),
                    'progress': 0,
                    'status': 'error',
                    'message': 'Failed to connect to vSphere server'
                })
                return False

            # Set up progress tracking
            sync_queue = queue.Queue()
            progress_data = {
                'total_resources': 8,  # datacenters, clusters, hosts, datastores, networks, resource_pools, vms, templates
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
                
                # Get all vSphere objects and sync to Redis
                self._sync_resource_to_redis('datacenters', self.get_all_datacenters, VSPHERE_DATACENTERS_KEY, sync_queue, update_progress)
                self._sync_resource_to_redis('clusters', self.get_all_clusters, VSPHERE_CLUSTERS_KEY, sync_queue, update_progress)
                self._sync_resource_to_redis('hosts', self.get_all_hosts, VSPHERE_HOSTS_KEY, sync_queue, update_progress)
                self._sync_resource_to_redis('datastores', self.get_all_datastores, VSPHERE_DATASTORES_KEY, sync_queue, update_progress)
                self._sync_resource_to_redis('networks', self.get_all_networks, VSPHERE_NETWORKS_KEY, sync_queue, update_progress)
                self._sync_resource_to_redis('resource_pools', self.get_all_resource_pools, VSPHERE_RESOURCE_POOLS_KEY, sync_queue, update_progress)
                self._sync_resource_to_redis('vms', self.get_all_vms, VSPHERE_VMS_KEY, sync_queue, update_progress)
                self._sync_resource_to_redis('templates', self.get_all_templates, VSPHERE_TEMPLATES_KEY, sync_queue, update_progress)
                
                # Signal worker to exit
                sync_queue.put(('DONE', 0))
                progress_thread.join(timeout=5)

                # Update last sync time
                now = datetime.utcnow().isoformat()
                result = {
                    'timestamp': now,
                    'type': 'full',
                    'counts': progress_data['counts'],
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
                    'message': 'Synchronization complete'
                })

                logger.info(f"vSphere data synchronized to Redis: {result}")
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

    def get_cache_status(self):
        """
        Get the status of the vSphere cache
        """
        last_sync = self.redis_client.get(VSPHERE_LAST_SYNC_KEY)
        
        # Check if each cache exists
        datacenters_exists = self.redis_client.exists(VSPHERE_DATACENTERS_KEY)
        clusters_exists = self.redis_client.exists(VSPHERE_CLUSTERS_KEY)
        hosts_exists = self.redis_client.exists(VSPHERE_HOSTS_KEY)
        datastores_exists = self.redis_client.exists(VSPHERE_DATASTORES_KEY)
        networks_exists = self.redis_client.exists(VSPHERE_NETWORKS_KEY)
        resource_pools_exists = self.redis_client.exists(VSPHERE_RESOURCE_POOLS_KEY)
        vms_exists = self.redis_client.exists(VSPHERE_VMS_KEY)
        templates_exists = self.redis_client.exists(VSPHERE_TEMPLATES_KEY)
        
        # Get TTL for each key
        datacenters_ttl = self.redis_client.get_ttl(VSPHERE_DATACENTERS_KEY)
        clusters_ttl = self.redis_client.get_ttl(VSPHERE_CLUSTERS_KEY)
        hosts_ttl = self.redis_client.get_ttl(VSPHERE_HOSTS_KEY)
        datastores_ttl = self.redis_client.get_ttl(VSPHERE_DATASTORES_KEY)
        networks_ttl = self.redis_client.get_ttl(VSPHERE_NETWORKS_KEY)
        resource_pools_ttl = self.redis_client.get_ttl(VSPHERE_RESOURCE_POOLS_KEY)
        vms_ttl = self.redis_client.get_ttl(VSPHERE_VMS_KEY)
        templates_ttl = self.redis_client.get_ttl(VSPHERE_TEMPLATES_KEY)
        
        # Get current sync status
        sync_status = self.redis_client.get(VSPHERE_SYNC_STATUS_KEY)
        sync_progress = self.redis_client.get(VSPHERE_SYNC_PROGRESS_KEY)
        
        status = {
            'last_sync': last_sync,
            'sync_status': sync_status,
            'sync_progress': sync_progress,
            'cache_status': {
                'datacenters': {
                    'exists': datacenters_exists,
                    'ttl': datacenters_ttl
                },
                'clusters': {
                    'exists': clusters_exists,
                    'ttl': clusters_ttl
                },
                'hosts': {
                    'exists': hosts_exists,
                    'ttl': hosts_ttl
                },
                'datastores': {
                    'exists': datastores_exists,
                    'ttl': datastores_ttl
                },
                'networks': {
                    'exists': networks_exists,
                    'ttl': networks_ttl
                },
                'resource_pools': {
                    'exists': resource_pools_exists,
                    'ttl': resource_pools_ttl
                },
                'vms': {
                    'exists': vms_exists,
                    'ttl': vms_ttl
                },
                'templates': {
                    'exists': templates_exists,
                    'ttl': templates_ttl
                }
            }
        }
        
        return status

    def clear_cache(self):
        """
        Clear all vSphere cache from Redis
        """
        try:
            # Get all keys with the vSphere prefix
            vsphere_keys = self.redis_client.keys_pattern(f"{VSPHERE_CACHE_PREFIX}*")
            
            # Delete each key
            for key in vsphere_keys:
                self.redis_client.delete(key)
            
            logger.info(f"Cleared {len(vsphere_keys)} vSphere cache keys from Redis")
            return True
        except Exception as e:
            logger.error(f"Error clearing vSphere cache: {str(e)}")
            return False

    def get_resource_for_terraform(self, environment):
        """
        Get vSphere resources needed for Terraform based on environment
        Returns a dictionary of resource IDs that can be used in Terraform
        """
        try:
            # Get resources from Redis
            resource_pools = self.redis_client.get(VSPHERE_RESOURCE_POOLS_KEY) or []
            datastores = self.redis_client.get(VSPHERE_DATASTORES_KEY) or []
            networks = self.redis_client.get(VSPHERE_NETWORKS_KEY) or []
            templates = self.redis_client.get(VSPHERE_TEMPLATES_KEY) or []
            
            # Select appropriate resources based on environment
            env_prefix = "PROD" if environment.lower() == "production" else "DEV"
            
            # Find resource pool
            selected_resource_pool = None
            for rp in resource_pools:
                if rp['name'].startswith(env_prefix):
                    selected_resource_pool = rp
                    break
            
            # Find datastore
            selected_datastore = None
            for ds in datastores:
                if ds['name'].startswith(env_prefix) and ds['accessible'] and ds['free_space_bytes'] > 0:
                    selected_datastore = ds
                    break
            
            # Find network
            selected_network = None
            for net in networks:
                if net['name'].startswith(env_prefix) and net['accessible']:
                    selected_network = net
                    break
            
            # Find template
            selected_template = None
            for template in templates:
                if template['name'].startswith('RHEL') and template['is_template']:
                    selected_template = template
                    break
            
            # Return resources
            return {
                'resource_pool_id': selected_resource_pool['id'] if selected_resource_pool else None,
                'datastore_id': selected_datastore['id'] if selected_datastore else None,
                'network_id': selected_network['id'] if selected_network else None,
                'template_uuid': selected_template['id'] if selected_template else None,
                'ipv4_gateway': f"192.168.{10 if environment.lower() == 'production' else 20}.1",
                'ipv4_address': f"192.168.{10 if environment.lower() == 'production' else 20}.100",
            }
        except Exception as e:
            logger.error(f"Error getting vSphere resources for Terraform: {str(e)}")
            return {
                'resource_pool_id': None,
                'datastore_id': None,
                'network_id': None,
                'template_uuid': None,
                'ipv4_gateway': None,
                'ipv4_address': None,
            }

    def get_vsphere_servers(self):
        """
        Get the list of available vSphere servers
        This is hardcoded as per requirements
        """
        return [
            {"id": "virtualcenter.chrobinson.com", "name": "virtualcenter.chrobinson.com PROD", "environment": "production"},
            {"id": "virtualcenter-ordc.chrobinson.com", "name": "virtualcenter-ordc.chrobinson.com DR", "environment": "dr"}
        ]

    def get_hierarchical_data(self, vsphere_server=None, datacenter_id=None, cluster_id=None, datastore_cluster_id=None):
        """
        Get vSphere data in a hierarchical structure based on the level of selection
        
        Args:
            vsphere_server: The selected vSphere server
            datacenter_id: The selected datacenter ID
            cluster_id: The selected cluster ID
            datastore_cluster_id: The selected datastore cluster ID
            
        Returns:
            A dictionary containing appropriate options for the next level in the hierarchy
        """
        try:
            # If no vSphere server is selected, return only the server list
            if not vsphere_server:
                return {
                    "vsphere_servers": self.get_vsphere_servers(),
                    "datacenters": [],
                    "clusters": [],
                    "datastore_clusters": [],
                    "networks": [],
                    "templates": []
                }
            
            # Get all data from Redis
            datacenters = self.redis_client.get(VSPHERE_DATACENTERS_KEY) or []
            clusters = self.redis_client.get(VSPHERE_CLUSTERS_KEY) or []
            datastores = self.redis_client.get(VSPHERE_DATASTORES_KEY) or []
            networks = self.redis_client.get(VSPHERE_NETWORKS_KEY) or []
            templates = self.redis_client.get(VSPHERE_TEMPLATES_KEY) or []
            hosts = self.redis_client.get(VSPHERE_HOSTS_KEY) or []
            
            # Filter datacenters - always return all datacenters since they're at the top level
            filtered_datacenters = datacenters
            
            # If datacenter is selected, filter clusters by datacenter
            filtered_clusters = clusters
            if datacenter_id:
                filtered_clusters = [c for c in clusters if c.get('datacenter_id') == datacenter_id]
            
            # If cluster is selected, filter datastores by cluster
            filtered_datastores = datastores
            if cluster_id:
                # Get hosts in the cluster
                cluster_host_ids = [h['id'] for h in hosts if h.get('cluster_id') == cluster_id]
                
                # Create a set of host IDs for efficient lookup
                cluster_host_ids_set = set(cluster_host_ids)
                
                # Filter datastores accessible by cluster hosts
                filtered_datastores = []
                for ds in datastores:
                    # Check if accessible and has connectivity to cluster hosts
                    if ds.get('accessible', False):
                        # For simplicity, show all accessible datastores since
                        # host_ids relationship might not be fully modeled in our cache
                        filtered_datastores.append(ds)
            
            # Filter networks by datacenter
            filtered_networks = networks
            if datacenter_id:
                # Our networks may not have datacenter_id in the model
                # For simplicity, we'll return all networks
                # In a real implementation, you'd filter by datacenter
                pass
            
            # Filter templates - only return deployable templates
            filtered_templates = [t for t in templates if t.get('is_template', False)]
            
            # Add helpful descriptions to templates where possible
            for template in filtered_templates:
                # Add OS version and size information if available
                if 'guest_full_name' in template and template['guest_full_name']:
                    template['name'] = f"{template['name']} ({template['guest_full_name']})"
                elif 'guest_id' in template and template['guest_id']:
                    template['name'] = f"{template['name']} ({template['guest_id']})"
                
                # Add CPU and memory info if available
                if 'cpu_count' in template and 'memory_mb' in template:
                    template['name'] = f"{template['name']} - {template['cpu_count']}CPU/{template['memory_mb']}MB"
            
            return {
                "vsphere_servers": self.get_vsphere_servers(),
                "datacenters": filtered_datacenters,
                "clusters": filtered_clusters,
                "datastore_clusters": filtered_datastores,
                "networks": filtered_networks,
                "templates": filtered_templates
            }
        except Exception as e:
            logger.error(f"Error getting hierarchical data: {str(e)}")
            return {
                "vsphere_servers": self.get_vsphere_servers(),
                "datacenters": [],
                "clusters": [],
                "datastore_clusters": [],
                "networks": [],
                "templates": []
            }

    def get_sync_progress(self):
        """
        Get the current synchronization progress
        """
        sync_status = self.redis_client.get(VSPHERE_SYNC_STATUS_KEY)
        sync_progress = self.redis_client.get(VSPHERE_SYNC_PROGRESS_KEY)
        
        if not sync_status or not sync_progress:
            return {
                'status': 'unknown',
                'progress': 0,
                'message': 'No synchronization information available'
            }
            
        return sync_progress

    def start_background_sync(self):
        """
        Start a background thread to sync all vSphere data
        """
        if self._background_refresh_running:
            logger.info("Background refresh already running")
            return

        self._background_refresh_running = True
        
        def background_sync():
            try:
                logger.info("Starting background vSphere sync")
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

# Convenience function to run a sync
def sync_vsphere_to_redis():
    """
    Run a sync of vSphere objects to Redis
    """
    vsphere_cache = VSphereRedisCache()
    return vsphere_cache.sync_all_to_redis()

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