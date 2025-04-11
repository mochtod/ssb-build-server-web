"""
Helper module for retrieving vSphere resources for VM provisioning.

This module provides functions for retrieving VMware vSphere resources for VM provisioning.
It uses an enhanced caching mechanism to reduce API calls and handle connection issues.
"""
import os
import ssl
import logging
import json
import socket
from datetime import datetime
from pyVim import connect
from pyVmomi import vim
from urllib.error import URLError

# Import configuration modules
try:
    from config import config
    from vsphere_cache import vsphere_cache, cached_resource_fetcher
except ImportError:
    # Fall back to the old way if modules aren't available
    logger.warning("Config or cache modules not available, using environment variables and basic caching")
    config = None
    vsphere_cache = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get default resource IDs from config or environment variables
def get_default_value(key, default_value):
    """Get a configuration value from config module or environment variables."""
    if config:
        return config.get(key, default_value)
    else:
        return os.environ.get(key, default_value)

# Default resource IDs
DEFAULT_RESOURCE_POOL_ID = get_default_value('RESOURCE_POOL_ID', 'resgroup-9814670')
DEFAULT_DEV_RESOURCE_POOL_ID = get_default_value('DEV_RESOURCE_POOL_ID', 'resgroup-3310245')
DEFAULT_DATASTORE_ID = get_default_value('DATASTORE_ID', 'datastore-4395110')
DEFAULT_NETWORK_ID_PROD = get_default_value('NETWORK_ID_PROD', 'dvportgroup-4545393')
DEFAULT_NETWORK_ID_DEV = get_default_value('NETWORK_ID_DEV', 'dvportgroup-4545393')
DEFAULT_TEMPLATE_UUID = get_default_value('TEMPLATE_UUID', 'vm-11682491')

# Default connection parameters
DEFAULT_TIMEOUT = int(get_default_value('VSPHERE_TIMEOUT', '30'))

def connect_to_vsphere(server=None, username=None, password=None, timeout=None):
    """
    Connect to vSphere server
    
    Args:
        server: vSphere server address (default: from config)
        username: vSphere username (default: from config)
        password: vSphere password (default: from config)
        timeout: Connection timeout in seconds (default: from config)
        
    Returns:
        ServiceInstance object or None if connection failed
    """
    # Get connection parameters from config if not provided
    if not server:
        server = get_default_value('VSPHERE_SERVER', None)
    if not username:
        username = get_default_value('VSPHERE_USER', None)
    if not password:
        password = get_default_value('VSPHERE_PASSWORD', None)
    if not timeout:
        timeout = DEFAULT_TIMEOUT
    
    if not (server and username and password):
        logger.warning("Missing vSphere connection details in configuration")
        return None
    
    try:
        # Create SSL context
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.verify_mode = ssl.CERT_NONE  # Disable certificate verification
        
        logger.info(f"Connecting to vSphere server: {server}")
        
        # Set socket timeout
        socket.setdefaulttimeout(timeout)
        
        # Attempt connection
        service_instance = connect.SmartConnect(
            host=server,
            user=username,
            pwd=password,
            sslContext=context
        )
        
        if not service_instance:
            logger.error("Failed to connect to vSphere server")
            return None
        
        logger.info("Successfully connected to vSphere server")
        return service_instance
        
    except Exception as e:
        logger.error(f"Error connecting to vSphere server {server}: {str(e)}")
        return None

def get_all_obj(content, vimtype, folder=None, recurse=True):
    """Get all vSphere objects of a specified type"""
    if not folder:
        folder = content.rootFolder
    
    container = content.viewManager.CreateContainerView(folder, vimtype, recurse)
    obj_list = container.view
    container.Destroy()
    return obj_list

def get_resource_info(obj_type, obj, preferred_ids=None):
    """Get basic information about a vSphere resource"""
    if preferred_ids is None:
        preferred_ids = []
    
    obj_id = str(obj._moId)
    info = {
        'name': obj.name,
        'id': obj_id,
        'type': obj_type,
        'is_preferred': obj_id in preferred_ids
    }
    
    # Add type-specific information
    if obj_type == 'ResourcePool':
        if hasattr(obj, 'parent') and obj.parent:
            info['parent'] = obj.parent.name
    
    elif obj_type == 'Datastore':
        if hasattr(obj, 'summary'):
            summary = obj.summary
            info['capacity'] = summary.capacity if hasattr(summary, 'capacity') else 0
            info['free_space'] = summary.freeSpace if hasattr(summary, 'freeSpace') else 0
            info['free_gb'] = round(info['free_space'] / (1024**3), 2)
            info['type'] = summary.type if hasattr(summary, 'type') else 'unknown'
            info['accessible'] = summary.accessible if hasattr(summary, 'accessible') else False
    
    elif obj_type == 'Network':
        if isinstance(obj, vim.DistributedVirtualPortgroup):
            info['network_type'] = 'dvPortgroup'
            info['vlan_id'] = getattr(obj.config.defaultPortConfig.vlan, 'vlanId', None) if hasattr(obj.config.defaultPortConfig, 'vlan') else None
        else:
            info['network_type'] = 'standard'
    
    elif obj_type == 'VirtualMachine':
        if obj.config and obj.config.template:
            info['is_template'] = True
            if hasattr(obj, 'summary') and hasattr(obj.summary, 'config'):
                info['guest_id'] = obj.summary.config.guestId
                info['num_cpu'] = obj.summary.config.numCpu
                info['memory_mb'] = obj.summary.config.memorySizeMB
    
    return info


# Adding caching decorator if available
if vsphere_cache:
    get_all_resource_pools = cached_resource_fetcher('resource_pools')(get_all_obj)
    get_all_datastores = cached_resource_fetcher('datastores')(get_all_obj)
    get_all_networks = cached_resource_fetcher('networks')(get_all_obj)
    get_all_templates = cached_resource_fetcher('templates')(get_all_obj)
else:
    # For backwards compatibility
    get_all_resource_pools = get_all_obj
    get_all_datastores = get_all_obj
    get_all_networks = get_all_obj
    get_all_templates = get_all_obj

def get_vsphere_resources(use_cache=True, max_items=200, force_refresh=False):
    """
    Get all vSphere resources needed for VM provisioning
        force_refresh: Whether to force refresh the cache
    Args:
        use_cache: Whether to use cached data if available
        max_items: Maximum number of items to retrieve for each resource type
        
    Returns:
        dict: Dictionary with resource pools, datastores, networks, and templates
    """
    # Use the enhanced cache mechanism if available
    if vsphere_cache and use_cache and not force_refresh:
        cached_resources = {
            'resource_pools': vsphere_cache.get_cached_resources('resource_pools'),
            'datastores': vsphere_cache.get_cached_resources('datastores'),
            'networks': vsphere_cache.get_cached_resources('networks'),
            'templates': vsphere_cache.get_cached_resources('templates')
        }
        
        # If all resources are available in cache, return them
        if all(cached_resources.values()):
            logger.info("Using cached vSphere resources")
            return cached_resources
    
    logger.info("Fetching vSphere resources")
    
    # Try to connect with a shorter timeout first
    service_instance = connect_to_vsphere(timeout=DEFAULT_TIMEOUT)
    if not service_instance:
        logger.warning("Using default values for vSphere resources")
        return get_default_resources()
    
    try:
        content = service_instance.RetrieveContent()
        
        # Dictionary to store all resources
        resources = {
            'resource_pools': [],
            'datastores': [],
            'networks': [],
            'templates': []
        }
        
        # Get all datacenters to search in
        datacenters = get_all_obj(content, [vim.Datacenter])
        logger.info(f"Found {len(datacenters)} datacenters")
        
        for dc in datacenters:
            logger.info(f"Processing datacenter: {dc.name}")
            
            # Process resource pools
            try:
                logger.info(f"Fetching resource pools in {dc.name}")
                resource_pools = get_all_obj(content, [vim.ResourcePool], dc.hostFolder)
                logger.info(f"Found {len(resource_pools)} resource pools")
                
                # Limit the number of resource pools to process
                resource_pools = resource_pools[:max_items]
                
                for rp in resource_pools:
                    info = get_resource_info('ResourcePool', rp, [DEFAULT_RESOURCE_POOL_ID, DEFAULT_DEV_RESOURCE_POOL_ID])
                    resources['resource_pools'].append(info)
            except Exception as e:
                logger.warning(f"Error getting resource pools: {str(e)}")
            
            # Process datastores
            try:
                logger.info(f"Fetching datastores in {dc.name}")
                datastores = get_all_obj(content, [vim.Datastore], dc.datastoreFolder)
                logger.info(f"Found {len(datastores)} datastores")
                
                # Limit the number of datastores to process
                datastores = datastores[:max_items]
                
                for ds in datastores:
                    info = get_resource_info('Datastore', ds, [DEFAULT_DATASTORE_ID])
                    resources['datastores'].append(info)
            except Exception as e:
                logger.warning(f"Error getting datastores: {str(e)}")
            
            # Process networks
            try:
                logger.info(f"Fetching networks in {dc.name}")
                networks = get_all_obj(content, [vim.Network], dc.networkFolder)
                logger.info(f"Found {len(networks)} networks")
                
                # Limit the number of networks to process
                networks = networks[:max_items]
                
                for net in networks:
                    info = get_resource_info('Network', net, [DEFAULT_NETWORK_ID_PROD, DEFAULT_NETWORK_ID_DEV])
                    resources['networks'].append(info)
            except Exception as e:
                logger.warning(f"Error getting networks: {str(e)}")
            
            # Process VM templates
            try:
                logger.info(f"Fetching VMs in {dc.name}")
                vms = get_all_obj(content, [vim.VirtualMachine], dc.vmFolder)
                logger.info(f"Found {len(vms)} VMs")
                
                # Filter for templates
                templates = [vm for vm in vms if vm.config and vm.config.template]
                logger.info(f"Found {len(templates)} templates")
                
                # Limit the number of templates to process
                templates = templates[:max_items]
                
                for template in templates:
                    info = get_resource_info('VirtualMachine', template, [DEFAULT_TEMPLATE_UUID])
                    if info.get('is_template', False):
                        resources['templates'].append(info)
            except Exception as e:
                logger.warning(f"Error getting templates: {str(e)}")
        
        # Update the cache if available
        if vsphere_cache and use_cache:
            vsphere_cache.update_cache('resource_pools', resources['resource_pools'])
            vsphere_cache.update_cache('datastores', resources['datastores'])
            vsphere_cache.update_cache('networks', resources['networks'])
            vsphere_cache.update_cache('templates', resources['templates'])
        
        # Disconnect from vSphere
        connect.Disconnect(service_instance)
        
        return resources
    
    except Exception as e:
        logger.exception(f"Error fetching vSphere resources: {str(e)}")
        connect.Disconnect(service_instance)
        return get_default_resources()

def get_default_resources():
    """Get default resources from environment variables"""
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
        'guest_id': 'rhel9_64Guest',
        'is_template': True,
        'is_preferred': True
    }]
    
    return {
        'resource_pools': resource_pools,
        'datastores': datastores,
        'networks': networks,
        'templates': templates
    }

def get_resources_for_environment(environment, resources=None):
    """Get resources appropriate for the specified environment"""
    if resources is None:
        resources = get_vsphere_resources()
    
    # For production environment
    if environment.lower() == 'production':
        # Find resources marked as production or preferred
        resource_pool = next((rp for rp in resources['resource_pools'] 
                             if 'prod' in rp['name'].lower() or rp['is_preferred']), 
                             resources['resource_pools'][0] if resources['resource_pools'] else None)
        
        network = next((net for net in resources['networks'] 
                       if 'prod' in net['name'].lower() or net['is_preferred']), 
                       resources['networks'][0] if resources['networks'] else None)
    else:
        # Find resources marked as development/non-production
        resource_pool = next((rp for rp in resources['resource_pools'] 
                             if 'dev' in rp['name'].lower() or 'nonprod' in rp['name'].lower()), 
                             resources['resource_pools'][0] if resources['resource_pools'] else None)
        
        network = next((net for net in resources['networks'] 
                       if 'dev' in net['name'].lower() or 'nonprod' in net['name'].lower()), 
                       resources['networks'][0] if resources['networks'] else None)
    
    # For any environment, choose datastore with most free space
    datastore = max(resources['datastores'], key=lambda ds: ds.get('free_space', 0)) if resources['datastores'] else None
    
    # Find RHEL9 template if available
    template = next((tpl for tpl in resources['templates'] 
                    if 'rhel9' in tpl['name'].lower()), 
                    resources['templates'][0] if resources['templates'] else None)
    
    return {
        'resource_pool': resource_pool,
        'datastore': datastore,
        'network': network,
        'template': template
    }

# Testing function
if __name__ == "__main__":
    resources = get_vsphere_resources(use_cache=False)
    print("\n=== vSphere Resources ===\n")
    
    print(f"Resource Pools: {len(resources['resource_pools'])}")
    for rp in resources['resource_pools'][:5]:  # Show first 5
        print(f" - {rp['name']} (ID: {rp['id']})")
    
    print(f"\nDatastores: {len(resources['datastores'])}")
    for ds in sorted(resources['datastores'], key=lambda d: d.get('free_space', 0), reverse=True)[:5]:
        free_gb = ds.get('free_gb', 0)
        print(f" - {ds['name']} (ID: {ds['id']}, Free: {free_gb} GB)")
    
    print(f"\nNetworks: {len(resources['networks'])}")
    for net in resources['networks'][:5]:
        print(f" - {net['name']} (ID: {net['id']})")
    
    print(f"\nTemplates: {len(resources['templates'])}")
    for tpl in resources['templates']:
        print(f" - {tpl['name']} (ID: {tpl['id']}, OS: {tpl.get('guest_id', 'unknown')})")
    
    print("\nDefault resources for development environment:")
    dev_resources = get_resources_for_environment('development', resources)
    
    print(f"Resource Pool: {dev_resources['resource_pool']['name']} (ID: {dev_resources['resource_pool']['id']})")
    print(f"Datastore: {dev_resources['datastore']['name']} (ID: {dev_resources['datastore']['id']}, Free: {dev_resources['datastore'].get('free_gb', 0)} GB)")
    print(f"Network: {dev_resources['network']['name']} (ID: {dev_resources['network']['id']})")
    print(f"Template: {dev_resources['template']['name']} (ID: {dev_resources['template']['id']}, OS: {dev_resources['template'].get('guest_id', 'unknown')})")
