#!/usr/bin/env python3
"""
Cluster-Centric vSphere Resource Retrieval

This module organizes vSphere resources in a hierarchical, cluster-centric way.
It ensures proper organization of resources based on the vSphere hierarchy:
- Clusters
- Resource Pools (one per cluster)
- Datastores (only storage clusters or DRS clusters, not individual ESXi hosts)
- Networks (associated with clusters)
- VM Templates (compatible with clusters)
"""
import os
import ssl
import json
import time
import logging
from datetime import datetime
from threading import Lock
from typing import Dict, List, Optional, Any, Set

try:
    from pyVim import connect
    from pyVmomi import vim
except ImportError:
    logging.error("Required packages not installed. Run: pip install pyVmomi")

# Configure logging
logger = logging.getLogger(__name__)

# Cache settings
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.vsphere_cache')
CACHE_TTL = 3600  # 1 hour in seconds
CACHE_LOCK = Lock()  # Lock for thread-safety

# Default connection parameters
DEFAULT_TIMEOUT = int(os.environ.get('VSPHERE_TIMEOUT', '30'))
DEFAULT_DATACENTERS = os.environ.get('VSPHERE_DATACENTERS', '').split(',')

class VSphereClusterResources:
    """Retrieves and organizes vSphere resources in a cluster-centric hierarchy."""
    
    def __init__(self, server=None, username=None, password=None, timeout=None):
        """Initialize the vSphere loader with connection parameters."""
        self.server = server or os.environ.get('VSPHERE_SERVER')
        self.username = username or os.environ.get('VSPHERE_USER')
        self.password = password or os.environ.get('VSPHERE_PASSWORD')
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.service_instance = None
        self.content = None
        
        # Ensure cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)
        
    def is_simulation_mode(self):
        """Check if we're in simulation mode with dummy credentials."""
        if (self.server == "vsphere-server" and 
            self.username == "vsphere-username" and 
            self.password == "vsphere-password"):
            return True
        return False
            
    def connect(self):
        """Connect to vSphere server."""
        if not (self.server and self.username and self.password):
            logger.error("Missing vSphere connection details")
            return False
        
        # Check if we're in simulation mode
        if self.is_simulation_mode():
            logger.warning("Running in simulation mode with dummy credentials")
            self.content = "SIMULATION"  # Set a marker that we can check for simulation mode
            return True
            
        try:
            # Create SSL context
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
            context.verify_mode = ssl.CERT_NONE  # Disable certificate verification
            
            logger.info(f"Connecting to vSphere server: {self.server}")
            
            # Attempt connection
            self.service_instance = connect.SmartConnect(
                host=self.server,
                user=self.username,
                pwd=self.password,
                sslContext=context
            )
            
            if not self.service_instance:
                logger.error("Failed to connect to vSphere server")
                return False
            
            # Retrieve content
            self.content = self.service_instance.RetrieveContent()
            logger.info("Successfully connected to vSphere server")
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to vSphere server: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from vSphere server."""
        if self.service_instance:
            connect.Disconnect(self.service_instance)
            self.service_instance = None
            self.content = None
    
    def _get_cache_path(self, resource_type):
        """Get the cache file path for a resource type."""
        return os.path.join(CACHE_DIR, f"cluster_{resource_type}.json")
    
    def _is_cache_valid(self, resource_type):
        """Check if cache for a resource type is valid."""
        cache_path = self._get_cache_path(resource_type)
        
        if not os.path.exists(cache_path):
            return False
            
        # Check cache age
        file_age = time.time() - os.path.getmtime(cache_path)
        return file_age < CACHE_TTL
    
    def _save_cache(self, resource_type, data):
        """Save data to cache."""
        with CACHE_LOCK:
            with open(self._get_cache_path(resource_type), 'w') as f:
                json.dump(data, f, indent=2)
    
    def _load_cache(self, resource_type):
        """Load data from cache."""
        try:
            with open(self._get_cache_path(resource_type), 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None
    
    def get_datacenter_list(self, filter_names=None):
        """Get list of datacenters, optionally filtered by name."""
        if not self.content:
            return []
        
        # If we're in simulation mode, return sample data
        if self.content == "SIMULATION":
            logger.info("Returning simulated datacenter data")
            
            # Create simulated datacenter objects
            datacenter_names = ["EBDC NONPROD", "EBDC PROD"] if not filter_names else [
                dc for dc in ["EBDC NONPROD", "EBDC PROD"] if dc in filter_names
            ]
            
            # Create simple object-like structures for simulation
            class SimulatedDC:
                def __init__(self, name):
                    self.name = name
                    self.hostFolder = "HOSTFOLDER"
                    self.datastoreFolder = "DATASTOREFOLDER"
                    self.networkFolder = "NETWORKFOLDER"
                    self.vmFolder = "VMFOLDER"
            
            return [SimulatedDC(name) for name in datacenter_names]
            
        # Normal mode - get real datacenters
        datacenter_list = []
        container = self.content.viewManager.CreateContainerView(
            self.content.rootFolder, [vim.Datacenter], True)
        
        for dc in container.view:
            # Skip if not in the filter list (if provided)
            if filter_names and dc.name not in filter_names:
                continue
            datacenter_list.append(dc)
        
        container.Destroy()
        return datacenter_list
    
    def get_clusters(self, datacenter=None):
        """Get all clusters from a datacenter or all datacenters."""
        if not self.content:
            return []
        
        # If we're in simulation mode, return sample data
        if self.content == "SIMULATION":
            logger.info("Returning simulated cluster data")
            
            # Define simulated cluster data based on datacenter
            dc_name = getattr(datacenter, 'name', None)
            
            if dc_name == "EBDC NONPROD":
                clusters = [
                    {
                        'name': 'NONPROD-Cluster-1',
                        'id': 'cluster-np-1',
                        'type': 'Cluster',
                        'datacenter': dc_name,
                        'host_count': 4
                    },
                    {
                        'name': 'NONPROD-Cluster-2',
                        'id': 'cluster-np-2',
                        'type': 'Cluster',
                        'datacenter': dc_name,
                        'host_count': 3
                    }
                ]
            elif dc_name == "EBDC PROD":
                clusters = [
                    {
                        'name': 'PROD-Cluster-1',
                        'id': 'cluster-p-1',
                        'type': 'Cluster',
                        'datacenter': dc_name,
                        'host_count': 6
                    },
                    {
                        'name': 'PROD-Cluster-2',
                        'id': 'cluster-p-2',
                        'type': 'Cluster',
                        'datacenter': dc_name,
                        'host_count': 5
                    }
                ]
            else:
                # Default clusters if datacenter not specified
                clusters = [
                    {
                        'name': 'DEFAULT-Cluster-1',
                        'id': 'cluster-d-1',
                        'type': 'Cluster',
                        'datacenter': 'UNKNOWN',
                        'host_count': 4
                    }
                ]
            
            return clusters
            
        # Normal mode - get real clusters
        # Use datacenter folder if provided, otherwise root folder
        folder = datacenter.hostFolder if datacenter else self.content.rootFolder
        
        # Get all clusters
        container = self.content.viewManager.CreateContainerView(
            folder, [vim.ClusterComputeResource], True)
        
        result = []
        for cluster in container.view:
            result.append({
                'name': cluster.name,
                'id': str(cluster._moId),
                'type': 'Cluster',
                'datacenter': datacenter.name if datacenter else None,
                'host_count': len(cluster.host) if hasattr(cluster, 'host') else 0
            })
        
        container.Destroy()
        return result
    
    def get_resource_pools_by_cluster(self, cluster_obj):
        """Get resource pools for a specific cluster, returning just one primary pool."""
        if not self.content or not cluster_obj:
            return []
            
        # For simplicity, we'll return the root resource pool of the cluster
        # This ensures one resource pool per cluster
        result = [{
            'name': f"{cluster_obj.name} Resources",
            'id': str(cluster_obj.resourcePool._moId),
            'type': 'ResourcePool',
            'cluster_id': str(cluster_obj._moId),
            'cluster_name': cluster_obj.name,
            'is_primary': True
        }]
        
        return result
    
    def get_datastores_by_cluster(self, cluster_obj):
        """Get datastores accessible by a specific cluster."""
        if not self.content or not cluster_obj:
            return []
            
        # Get all hosts in the cluster
        host_datastores = {}
        shared_datastores = set()
        
        # First pass: collect all datastores and track which hosts can access them
        for host in cluster_obj.host:
            for ds in host.datastore:
                ds_id = str(ds._moId)
                if ds_id not in host_datastores:
                    host_datastores[ds_id] = {
                        'datastore': ds,
                        'host_count': 0,
                        'hosts': set()
                    }
                host_datastores[ds_id]['host_count'] += 1
                host_datastores[ds_id]['hosts'].add(str(host._moId))
                
                # If a datastore is accessible by all hosts in the cluster, it's shared
                if host_datastores[ds_id]['host_count'] == len(cluster_obj.host):
                    shared_datastores.add(ds_id)
        
        result = []
        # Only include datastores that are shared across the entire cluster
        # or datastores that are part of a storage cluster (DRS)
        for ds_id, data in host_datastores.items():
            ds = data['datastore']
            
            # Skip individual host datastores (not shared)
            if ds_id not in shared_datastores and not getattr(ds, 'storageIORMConfiguration', None):
                continue
                
            # Get datastore information
            info = {
                'name': ds.name,
                'id': ds_id,
                'type': 'Datastore',
                'cluster_id': str(cluster_obj._moId),
                'cluster_name': cluster_obj.name,
                'shared_across_cluster': ds_id in shared_datastores
            }
            
            # Add capacity information if available
            if hasattr(ds, 'summary'):
                summary = ds.summary
                info['capacity'] = summary.capacity if hasattr(summary, 'capacity') else 0
                info['free_space'] = summary.freeSpace if hasattr(summary, 'freeSpace') else 0
                info['free_gb'] = round(info['free_space'] / (1024**3), 2)
            
            result.append(info)
        
        return result
    
    def get_networks_by_cluster(self, cluster_obj):
        """Get networks accessible by a specific cluster."""
        if not self.content or not cluster_obj:
            return []
            
        # Get all hosts in the cluster
        host_networks = {}
        shared_networks = set()
        
        # First pass: collect all networks and track which hosts can access them
        for host in cluster_obj.host:
            for network in host.network:
                net_id = str(network._moId)
                if net_id not in host_networks:
                    host_networks[net_id] = {
                        'network': network,
                        'host_count': 0,
                        'hosts': set()
                    }
                host_networks[net_id]['host_count'] += 1
                host_networks[net_id]['hosts'].add(str(host._moId))
                
                # If a network is accessible by all hosts in the cluster, it's shared
                if host_networks[net_id]['host_count'] == len(cluster_obj.host):
                    shared_networks.add(net_id)
        
        result = []
        # Only include networks that are shared across the entire cluster
        for net_id, data in host_networks.items():
            network = data['network']
            
            # Skip networks not shared across the cluster
            if net_id not in shared_networks:
                continue
                
            # Get network information
            info = {
                'name': network.name,
                'id': net_id,
                'type': 'Network',
                'cluster_id': str(cluster_obj._moId),
                'cluster_name': cluster_obj.name,
                'is_dvs': isinstance(network, vim.DistributedVirtualPortgroup)
            }
            
            result.append(info)
        
        return result
    
    def get_templates_by_cluster(self, cluster_obj):
        """Get VM templates compatible with a specific cluster."""
        if not self.content or not cluster_obj:
            return []
            
        # Get datacenter of this cluster
        container = self.content.viewManager.CreateContainerView(
            self.content.rootFolder, [vim.Datacenter], True)
        
        datacenter = None
        for dc in container.view:
            # Check if this cluster is in this datacenter
            dc_clusters = self.content.viewManager.CreateContainerView(
                dc.hostFolder, [vim.ClusterComputeResource], True)
            
            for c in dc_clusters.view:
                if str(c._moId) == str(cluster_obj._moId):
                    datacenter = dc
                    break
            
            dc_clusters.Destroy()
            if datacenter:
                break
        
        container.Destroy()
        
        if not datacenter:
            return []
        
        # Get all VM templates in the datacenter
        container = self.content.viewManager.CreateContainerView(
            datacenter.vmFolder, [vim.VirtualMachine], True)
        
        result = []
        for vm in container.view:
            if vm.config and vm.config.template:
                template_info = {
                    'name': vm.name,
                    'id': str(vm._moId),
                    'type': 'VirtualMachine',
                    'cluster_id': str(cluster_obj._moId),
                    'cluster_name': cluster_obj.name,
                    'is_template': True,
                    'guest_id': vm.config.guestId if vm.config else None,
                    'guest_fullname': vm.config.guestFullName if vm.config else None
                }
                result.append(template_info)
        
        container.Destroy()
        return result
    
    def get_cluster_resources(self, use_cache=True, force_refresh=False, target_datacenters=None):
        """
        Get all vSphere resources organized by clusters.
        
        Args:
            use_cache: Whether to use cached data if available
            force_refresh: Whether to force refresh the cache
            target_datacenters: List of datacenter names to target (limits scope)
            
        Returns:
            dict: Dictionary with clusters and their associated resources
        """
        # Resource types to retrieve
        resource_types = ['clusters']
        
        # Check if we can use cache
        if use_cache and not force_refresh:
            all_cached = True
            cached_resources = {}
            
            for resource_type in resource_types:
                if self._is_cache_valid(resource_type):
                    cached_resources[resource_type] = self._load_cache(resource_type)
                    if not cached_resources[resource_type]:
                        all_cached = False
                        break
                else:
                    all_cached = False
                    break
            
            if all_cached:
                logger.info("Using cached vSphere cluster resources")
                return cached_resources
        
        # Connect to vSphere if not already connected
        if not self.content and not self.connect():
            logger.error("Could not connect to vSphere")
            return {resource_type: [] for resource_type in resource_types}
        
        try:
            # Get datacenters, filtered if needed
            datacenters = self.get_datacenter_list(target_datacenters)
            logger.info(f"Found {len(datacenters)} datacenters" + 
                      (f" matching filter: {target_datacenters}" if target_datacenters else ""))
            
            # Get all clusters across all datacenters
            all_clusters = []
            for dc in datacenters:
                start_time = time.time()
                clusters = self.get_clusters(dc)
                all_clusters.extend(clusters)
                logger.info(f"Retrieved {len(clusters)} clusters from {dc.name} in {time.time() - start_time:.2f}s")
            
            # Create result structure
            result = {
                'clusters': all_clusters,
                'timestamp': datetime.now().isoformat()
            }
            
            # Update cache
            if use_cache:
                self._save_cache('clusters', result)
                logger.info("Updated vSphere cluster resources cache")
            
            return result
            
        except Exception as e:
            logger.exception(f"Error retrieving vSphere cluster resources: {str(e)}")
            return {'clusters': []}
            
        finally:
            # Disconnect when done
            self.disconnect()
    
    def get_resources_for_cluster(self, cluster_id, use_cache=True, force_refresh=False):
        """
        Get all resources for a specific cluster.
        
        Args:
            cluster_id: The ID of the cluster
            use_cache: Whether to use cached data if available
            force_refresh: Whether to force refresh the cache
            
        Returns:
            dict: Dictionary with resources for the specified cluster
        """
        cache_key = f"cluster_{cluster_id}_resources"
        
        # Check if we can use cache
        if use_cache and not force_refresh and self._is_cache_valid(cache_key):
            cached_data = self._load_cache(cache_key)
            if cached_data:
                logger.info(f"Using cached resources for cluster {cluster_id}")
                return cached_data
        
        # Connect to vSphere if not already connected
        if not self.content and not self.connect():
            logger.error("Could not connect to vSphere")
            return {
                'resource_pools': [],
                'datastores': [],
                'networks': [],
                'templates': []
            }
        
        # If we're in simulation mode, return sample data
        if self.content == "SIMULATION":
            logger.info(f"Returning simulated resources for cluster {cluster_id}")
            
            # Determine cluster name based on ID
            cluster_names = {
                'cluster-np-1': 'NONPROD-Cluster-1',
                'cluster-np-2': 'NONPROD-Cluster-2',
                'cluster-p-1': 'PROD-Cluster-1',
                'cluster-p-2': 'PROD-Cluster-2',
                'cluster-d-1': 'DEFAULT-Cluster-1'
            }
            cluster_name = cluster_names.get(cluster_id, f"Cluster-{cluster_id}")
            
            # Create simulated resources
            resource_pools = [{
                'name': f"{cluster_name} Resources",
                'id': f"resgroup-{cluster_id}-1",
                'type': 'ResourcePool',
                'cluster_id': cluster_id,
                'cluster_name': cluster_name,
                'is_primary': True
            }]
            
            # Simulated datastores with no "_local" datastores
            datastores = [
                {
                    'name': f"{cluster_name}-SAN-DS01",
                    'id': f"datastore-{cluster_id}-1",
                    'type': 'Datastore',
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'shared_across_cluster': True,
                    'capacity': 2000 * (1024**3),
                    'free_space': 1200 * (1024**3),
                    'free_gb': 1200
                },
                {
                    'name': f"{cluster_name}-SAN-DS02",
                    'id': f"datastore-{cluster_id}-2",
                    'type': 'Datastore',
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'shared_across_cluster': True,
                    'capacity': 3000 * (1024**3),
                    'free_space': 1800 * (1024**3),
                    'free_gb': 1800
                },
                {
                    'name': f"{cluster_name}-SAN-DS03",
                    'id': f"datastore-{cluster_id}-3",
                    'type': 'Datastore',
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'shared_across_cluster': True,
                    'capacity': 4000 * (1024**3),
                    'free_space': 2500 * (1024**3),
                    'free_gb': 2500
                }
            ]
            
            # Simulated networks
            networks = [
                {
                    'name': f"{cluster_name}-VLAN-101",
                    'id': f"network-{cluster_id}-1",
                    'type': 'Network',
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'is_dvs': True
                },
                {
                    'name': f"{cluster_name}-VLAN-102",
                    'id': f"network-{cluster_id}-2",
                    'type': 'Network',
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'is_dvs': True
                },
                {
                    'name': f"{cluster_name}-VLAN-103",
                    'id': f"network-{cluster_id}-3",
                    'type': 'Network',
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'is_dvs': True
                }
            ]
            
            # Simulated templates
            templates = [
                {
                    'name': "RHEL9-Standard-Template",
                    'id': f"template-{cluster_id}-1",
                    'type': 'VirtualMachine',
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'is_template': True,
                    'guest_id': 'rhel9_64Guest',
                    'guest_fullname': 'Red Hat Enterprise Linux 9 (64-bit)'
                },
                {
                    'name': "Windows-2022-Template",
                    'id': f"template-{cluster_id}-2",
                    'type': 'VirtualMachine',
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_name,
                    'is_template': True,
                    'guest_id': 'windows2022srv_64Guest',
                    'guest_fullname': 'Microsoft Windows Server 2022 (64-bit)'
                }
            ]
            
            # Create result structure
            result = {
                'cluster_name': cluster_name,
                'cluster_id': cluster_id,
                'resource_pools': resource_pools,
                'datastores': datastores,
                'networks': networks,
                'templates': templates,
                'timestamp': datetime.now().isoformat()
            }
            
            # Update cache
            if use_cache:
                self._save_cache(cache_key, result)
                logger.info(f"Updated cache for cluster {cluster_id} simulated resources")
            
            return result
        
        # Normal mode - get real resources
        try:
            # Find the cluster object
            container = self.content.viewManager.CreateContainerView(
                self.content.rootFolder, [vim.ClusterComputeResource], True)
            
            cluster_obj = None
            for cluster in container.view:
                if str(cluster._moId) == cluster_id:
                    cluster_obj = cluster
                    break
            
            container.Destroy()
            
            if not cluster_obj:
                logger.error(f"Cluster with ID {cluster_id} not found")
                return {
                    'resource_pools': [],
                    'datastores': [],
                    'networks': [],
                    'templates': []
                }
            
            # Get resources for this cluster
            start_time = time.time()
            
            # Get resource pools (one per cluster)
            resource_pools = self.get_resource_pools_by_cluster(cluster_obj)
            
            # Get datastores
            datastores = self.get_datastores_by_cluster(cluster_obj)
            
            # Get networks
            networks = self.get_networks_by_cluster(cluster_obj)
            
            # Get templates
            templates = self.get_templates_by_cluster(cluster_obj)
            
            logger.info(f"Retrieved all resources for cluster {cluster_obj.name} in {time.time() - start_time:.2f}s")
            
            # Create result structure
            result = {
                'cluster_name': cluster_obj.name,
                'cluster_id': cluster_id,
                'resource_pools': resource_pools,
                'datastores': datastores,
                'networks': networks,
                'templates': templates,
                'timestamp': datetime.now().isoformat()
            }
            
            # Update cache
            if use_cache:
                self._save_cache(cache_key, result)
                logger.info(f"Updated cache for cluster {cluster_id} resources")
            
            return result
            
        except Exception as e:
            logger.exception(f"Error retrieving resources for cluster {cluster_id}: {str(e)}")
            return {
                'resource_pools': [],
                'datastores': [],
                'networks': [],
                'templates': []
            }
            
        finally:
            # Disconnect when done
            self.disconnect()

# Singleton instance
_cluster_resources_instance = None

def get_instance():
    """Get the singleton VSphereClusterResources instance."""
    global _cluster_resources_instance
    if _cluster_resources_instance is None:
        _cluster_resources_instance = VSphereClusterResources()
    return _cluster_resources_instance

def get_clusters(use_cache=True, force_refresh=False, target_datacenters=None):
    """Convenience function to get all clusters."""
    instance = get_instance()
    result = instance.get_cluster_resources(
        use_cache=use_cache,
        force_refresh=force_refresh,
        target_datacenters=target_datacenters
    )
    return result.get('clusters', [])

def get_resources_for_cluster(cluster_id, use_cache=True, force_refresh=False):
    """Convenience function to get resources for a specific cluster."""
    instance = get_instance()
    return instance.get_resources_for_cluster(
        cluster_id=cluster_id,
        use_cache=use_cache,
        force_refresh=force_refresh
    )

def get_ebdc_resources(force_refresh=False):
    """
    Get resources specifically from EBDC NONPROD and EBDC PROD datacenters.
    
    Args:
        force_refresh: Whether to force refresh the cache
        
    Returns:
        dict: Dictionary with EBDC datacenters, clusters, and their resources
    """
    # Target only EBDC datacenters
    target_datacenters = ["EBDC NONPROD", "EBDC PROD"]
    logger.info(f"Retrieving resources specifically for datacenters: {target_datacenters}")
    
    # Get clusters for these specific datacenters
    clusters = get_clusters(use_cache=True, force_refresh=force_refresh, target_datacenters=target_datacenters)
    
    if not clusters:
        logger.warning(f"No clusters found for datacenters: {target_datacenters}")
        return {
            'datacenters': target_datacenters,
            'clusters': [],
            'resources': {}
        }
    
    # Group clusters by datacenter
    clusters_by_dc = {}
    for cluster in clusters:
        dc_name = cluster.get('datacenter')
        if dc_name not in clusters_by_dc:
            clusters_by_dc[dc_name] = []
        clusters_by_dc[dc_name].append(cluster)
    
    # Get resources for each cluster
    resources_by_cluster = {}
    for cluster in clusters:
        cluster_id = cluster['id']
        cluster_name = cluster['name']
        logger.info(f"Retrieving resources for cluster: {cluster_name}")
        
        # Get resources for this cluster
        resources = get_resources_for_cluster(cluster_id, use_cache=True, force_refresh=force_refresh)
        
        # Filter out local datastores (containing "_local" in name)
        if 'datastores' in resources:
            original_count = len(resources['datastores'])
            resources['datastores'] = [
                ds for ds in resources['datastores'] 
                if "_local" not in ds['name']
            ]
            filtered_count = len(resources['datastores'])
            logger.info(f"Filtered datastores for {cluster_name}: {original_count} → {filtered_count} (removed {original_count - filtered_count} local datastores)")
        
        resources_by_cluster[cluster_id] = resources
    
    result = {
        'datacenters': target_datacenters,
        'clusters': clusters,
        'clusters_by_datacenter': clusters_by_dc,
        'resources': resources_by_cluster,
        'timestamp': datetime.now().isoformat()
    }
    
    return result

if __name__ == "__main__":
    # Setup logging for command-line testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Simple test
    print("Testing VSphere Cluster Resources...")
    
    # Get all clusters
    clusters = get_clusters(use_cache=True)
    print(f"Found {len(clusters)} clusters")
    
    # Print cluster information
    for i, cluster in enumerate(clusters, 1):
        print(f"\n{i}. {cluster['name']} (ID: {cluster['id']})")
        
        # Get resources for this cluster
        if i <= 2:  # Only get details for the first two clusters to avoid too much output
            resources = get_resources_for_cluster(cluster['id'])
            
            print(f"  Resource Pools: {len(resources['resource_pools'])}")
            for rp in resources['resource_pools']:
                print(f"   - {rp['name']} (ID: {rp['id']})")
            
            print(f"  Datastores: {len(resources['datastores'])}")
            for ds in resources['datastores'][:3]:  # Show just first 3
                print(f"   - {ds['name']} (ID: {ds['id']})")
                if len(resources['datastores']) > 3:
                    print(f"   - ... and {len(resources['datastores']) - 3} more")
            
            print(f"  Networks: {len(resources['networks'])}")
            for net in resources['networks'][:3]:  # Show just first 3
                print(f"   - {net['name']} (ID: {net['id']})")
                if len(resources['networks']) > 3:
                    print(f"   - ... and {len(resources['networks']) - 3} more")
            
            print(f"  Templates: {len(resources['templates'])}")
            for tpl in resources['templates'][:3]:  # Show just first 3
                print(f"   - {tpl['name']} (ID: {tpl['id']})")
                if len(resources['templates']) > 3:
                    print(f"   - ... and {len(resources['templates']) - 3} more")
