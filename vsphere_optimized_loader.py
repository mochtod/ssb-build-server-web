#!/usr/bin/env python3
"""
Optimized vSphere Resource Loader for SSB Build Server Web.

This module provides optimized functions for retrieving vSphere resources
with enhanced performance and caching.
"""
import os
import ssl
import json
import time
import logging
from datetime import datetime, timedelta
from threading import Lock
from pathlib import Path

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

class VSphereOptimizedLoader:
    """Optimized loader for vSphere resources with enhanced caching and performance."""
    
    def __init__(self, server=None, username=None, password=None, timeout=None):
        """Initialize the vSphere loader with connection parameters."""
        self.server = server or os.environ.get('VSPHERE_SERVER')
        self.username = username or os.environ.get('VSPHERE_USER')
        self.password = password or os.environ.get('VSPHERE_PASSWORD')
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.service_instance = None
        self.content = None
        self.datacenters = []
        
        # Ensure cache directory exists
        os.makedirs(CACHE_DIR, exist_ok=True)
        
    def connect(self):
        """Connect to vSphere server."""
        if not (self.server and self.username and self.password):
            logger.error("Missing vSphere connection details")
            return False
            
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
        return os.path.join(CACHE_DIR, f"{resource_type}.json")
    
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
    
    def get_resource_info(self, obj, obj_type):
        """Get basic info about a vSphere resource."""
        info = {
            'name': obj.name,
            'id': str(obj._moId),
            'type': obj_type
        }
        
        # Add type-specific details
        if obj_type == 'Datastore':
            if hasattr(obj, 'summary'):
                summary = obj.summary
                info['capacity'] = summary.capacity if hasattr(summary, 'capacity') else 0
                info['free_space'] = summary.freeSpace if hasattr(summary, 'freeSpace') else 0
                info['free_gb'] = round(info['free_space'] / (1024**3), 2)
        
        elif obj_type == 'VirtualMachine':
            info['is_template'] = obj.config and obj.config.template
        
        return info
    
    def get_all_resource_pools(self, datacenter=None, limit=50):
        """Get all resource pools, optionally from a specific datacenter with limiting."""
        if not self.content:
            return []
            
        # Use datacenter folder if provided, otherwise root folder
        folder = datacenter.hostFolder if datacenter else self.content.rootFolder
        
        # Get all resource pools
        container = self.content.viewManager.CreateContainerView(
            folder, [vim.ResourcePool], True)
        
        result = []
        for i, rp in enumerate(container.view):
            # Apply limiting
            if limit and i >= limit:
                break
            result.append(self.get_resource_info(rp, 'ResourcePool'))
        
        container.Destroy()
        return result
    
    def get_all_datastores(self, datacenter=None, limit=50):
        """Get all datastores, optionally from a specific datacenter with limiting."""
        if not self.content:
            return []
            
        # Use datacenter folder if provided, otherwise root folder
        folder = datacenter.datastoreFolder if datacenter else self.content.rootFolder
        
        # Get all datastores
        container = self.content.viewManager.CreateContainerView(
            folder, [vim.Datastore], True)
        
        result = []
        for i, ds in enumerate(container.view):
            # Apply limiting
            if limit and i >= limit:
                break
            result.append(self.get_resource_info(ds, 'Datastore'))
        
        container.Destroy()
        return result
    
    def get_all_networks(self, datacenter=None, limit=50):
        """Get all networks, optionally from a specific datacenter with limiting."""
        if not self.content:
            return []
            
        # Use datacenter folder if provided, otherwise root folder
        folder = datacenter.networkFolder if datacenter else self.content.rootFolder
        
        # Get all networks
        container = self.content.viewManager.CreateContainerView(
            folder, [vim.Network], True)
        
        result = []
        for i, net in enumerate(container.view):
            # Apply limiting
            if limit and i >= limit:
                break
            result.append(self.get_resource_info(net, 'Network'))
        
        container.Destroy()
        return result
    
    def get_all_templates(self, datacenter=None, limit=20):
        """Get all VM templates, optionally from a specific datacenter with limiting."""
        if not self.content:
            return []
            
        # Use datacenter folder if provided, otherwise root folder
        folder = datacenter.vmFolder if datacenter else self.content.rootFolder
        
        # Get all VMs
        container = self.content.viewManager.CreateContainerView(
            folder, [vim.VirtualMachine], True)
        
        result = []
        template_count = 0
        
        for vm in container.view:
            # Check if it's a template
            if vm.config and vm.config.template:
                # Apply limiting
                if limit and template_count >= limit:
                    break
                    
                result.append(self.get_resource_info(vm, 'VirtualMachine'))
                template_count += 1
        
        container.Destroy()
        return result
    
    def get_vsphere_resources(self, use_cache=True, force_refresh=False, 
                              target_datacenters=None, resource_limits=None):
        """
        Get all vSphere resources needed for VM provisioning.
        
        Args:
            use_cache: Whether to use cached data if available
            force_refresh: Whether to force refresh the cache
            target_datacenters: List of datacenter names to target (limits scope)
            resource_limits: Dict with limits for each resource type
            
        Returns:
            dict: Dictionary with resource pools, datastores, networks, and templates
        """
        # Set defaults
        if resource_limits is None:
            resource_limits = {
                'resource_pools': 50,
                'datastores': 50,
                'networks': 50,
                'templates': 20
            }
        
        # Resource types to retrieve
        resource_types = ['resource_pools', 'datastores', 'networks', 'templates']
        
        # Check if we can use cache for all resource types
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
                logger.info("Using cached vSphere resources")
                return cached_resources
        
        # Connect to vSphere if not already connected
        if not self.content and not self.connect():
            logger.error("Could not connect to vSphere")
            return {resource_type: [] for resource_type in resource_types}
        
        try:
            # Storage for all resources
            all_resources = {resource_type: [] for resource_type in resource_types}
            
            # Get datacenters, filtered if needed
            datacenters = self.get_datacenter_list(target_datacenters)
            logger.info(f"Found {len(datacenters)} datacenters" + 
                      (f" matching filter: {target_datacenters}" if target_datacenters else ""))
            
            # Process each datacenter
            for dc in datacenters:
                logger.info(f"Processing datacenter: {dc.name}")
                
                # Resource Pools
                start_time = time.time()
                resource_pools = self.get_all_resource_pools(
                    dc, limit=resource_limits['resource_pools'])
                all_resources['resource_pools'].extend(resource_pools)
                logger.info(f"Retrieved {len(resource_pools)} resource pools in {time.time() - start_time:.2f}s")
                
                # Datastores
                start_time = time.time()
                datastores = self.get_all_datastores(
                    dc, limit=resource_limits['datastores'])
                all_resources['datastores'].extend(datastores)
                logger.info(f"Retrieved {len(datastores)} datastores in {time.time() - start_time:.2f}s")
                
                # Networks
                start_time = time.time()
                networks = self.get_all_networks(
                    dc, limit=resource_limits['networks'])
                all_resources['networks'].extend(networks)
                logger.info(f"Retrieved {len(networks)} networks in {time.time() - start_time:.2f}s")
                
                # Templates
                start_time = time.time()
                templates = self.get_all_templates(
                    dc, limit=resource_limits['templates'])
                all_resources['templates'].extend(templates)
                logger.info(f"Retrieved {len(templates)} templates in {time.time() - start_time:.2f}s")
            
            # Update cache
            if use_cache:
                for resource_type, resources in all_resources.items():
                    self._save_cache(resource_type, resources)
                logger.info("Updated vSphere resource cache")
            
            return all_resources
            
        except Exception as e:
            logger.exception(f"Error retrieving vSphere resources: {str(e)}")
            return {resource_type: [] for resource_type in resource_types}
            
        finally:
            # Disconnect when done
            self.disconnect()

# Singleton instance of the loader
_loader_instance = None

def get_loader():
    """Get the singleton VSphereOptimizedLoader instance."""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = VSphereOptimizedLoader()
    return _loader_instance

def get_vsphere_resources(use_cache=True, force_refresh=False, target_datacenters=None):
    """Convenience function to get resources using the singleton loader."""
    loader = get_loader()
    return loader.get_vsphere_resources(
        use_cache=use_cache,
        force_refresh=force_refresh,
        target_datacenters=target_datacenters,
        resource_limits={
            'resource_pools': 20,  # Reduced limits for better performance
            'datastores': 20,
            'networks': 20,
            'templates': 10
        }
    )

def get_minimal_vsphere_resources(use_cache=True, target_datacenters=None):
    """
    Get only the top 10 resources from each category for initial display.
    
    Args:
        use_cache: Whether to use cached data if available
        target_datacenters: List of datacenter names to target (limits scope)
        
    Returns:
        dict: Dictionary with limited resource pools, datastores, networks, and templates
    """
    loader = get_loader()
    
    # Very small limits for fast initial loading
    minimal_limits = {
        'resource_pools': 10,
        'datastores': 10,
        'networks': 10,
        'templates': 10
    }
    
    # Try to get resources from cache first
    if use_cache:
        # Check if cache exists for all resource types
        resource_types = ['resource_pools', 'datastores', 'networks', 'templates']
        cached_resources = {}
        all_cached = True
        
        for resource_type in resource_types:
            if loader._is_cache_valid(resource_type):
                # Load from cache but only take the top N
                full_resources = loader._load_cache(resource_type)
                if full_resources:
                    cached_resources[resource_type] = full_resources[:minimal_limits[resource_type]]
                else:
                    all_cached = False
                    break
            else:
                all_cached = False
                break
        
        if all_cached:
            logger.info("Using cached vSphere resources (minimal set)")
            return cached_resources
    
    # If cache not available, get minimal resources directly
    logger.info("Fetching minimal set of vSphere resources")
    return loader.get_vsphere_resources(
        use_cache=use_cache,
        force_refresh=False,
        target_datacenters=target_datacenters,
        resource_limits=minimal_limits
    )

def get_default_resources():
    """Get default resources when vSphere connection fails."""
    # Default resource IDs
    DEFAULT_RESOURCE_POOL_ID = os.environ.get('RESOURCE_POOL_ID', 'resgroup-9814670')
    DEFAULT_DEV_RESOURCE_POOL_ID = os.environ.get('DEV_RESOURCE_POOL_ID', 'resgroup-3310245')
    DEFAULT_DATASTORE_ID = os.environ.get('DATASTORE_ID', 'datastore-4395110')
    DEFAULT_NETWORK_ID_PROD = os.environ.get('NETWORK_ID_PROD', 'dvportgroup-4545393')
    DEFAULT_NETWORK_ID_DEV = os.environ.get('NETWORK_ID_DEV', 'dvportgroup-4545393')
    DEFAULT_TEMPLATE_UUID = os.environ.get('TEMPLATE_UUID', 'vm-11682491')
    
    resource_pools = [{
        'name': 'Default Production Resource Pool',
        'id': DEFAULT_RESOURCE_POOL_ID,
        'type': 'ResourcePool',
        'is_preferred': True
    }, {
        'name': 'Default Development Resource Pool',
        'id': DEFAULT_DEV_RESOURCE_POOL_ID,
        'type': 'ResourcePool',
        'is_preferred': False
    }]
    
    datastores = [{
        'name': 'Default Datastore',
        'id': DEFAULT_DATASTORE_ID,
        'type': 'Datastore',
        'free_gb': 1000,
        'capacity': 2000 * (1024**3),
        'free_space': 1000 * (1024**3),
        'is_preferred': True
    }]
    
    networks = [{
        'name': 'Default Production Network',
        'id': DEFAULT_NETWORK_ID_PROD,
        'type': 'Network',
        'is_preferred': True
    }, {
        'name': 'Default Development Network',
        'id': DEFAULT_NETWORK_ID_DEV,
        'type': 'Network',
        'is_preferred': False
    }]
    
    templates = [{
        'name': 'RHEL 9 Template',
        'id': DEFAULT_TEMPLATE_UUID,
        'type': 'VirtualMachine',
        'is_template': True,
        'is_preferred': True
    }]
    
    return {
        'resource_pools': resource_pools,
        'datastores': datastores,
        'networks': networks,
        'templates': templates
    }

# Testing functions
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Test the loader
    print("Testing optimized vSphere loader...")
    
    # You can specify target datacenters to limit the scope
    target_dcs = ["ebdc-npk8s"]  # Replace with your actual datacenter names
    
    # Start time measurement
    start_time = time.time()
    
    # Get resources
    resources = get_vsphere_resources(
        use_cache=True,
        force_refresh=False,
        target_datacenters=target_dcs
    )
    
    # Print results
    total_time = time.time() - start_time
    print(f"\nRetrieved all resources in {total_time:.2f} seconds")
    
    print(f"\nResource Pools: {len(resources['resource_pools'])}")
    for rp in resources['resource_pools'][:3]:  # Show first 3
        print(f" - {rp['name']} (ID: {rp['id']})")
    
    print(f"\nDatastores: {len(resources['datastores'])}")
    for ds in resources['datastores'][:3]:
        print(f" - {ds['name']} (ID: {ds['id']})")
    
    print(f"\nNetworks: {len(resources['networks'])}")
    for net in resources['networks'][:3]:
        print(f" - {net['name']} (ID: {net['id']})")
    
    print(f"\nTemplates: {len(resources['templates'])}")
    for tpl in resources['templates'][:3]:
        print(f" - {tpl['name']} (ID: {tpl['id']})")
