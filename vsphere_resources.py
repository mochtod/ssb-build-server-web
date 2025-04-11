"""
Helper module for retrieving vSphere resources for VM provisioning.
"""
import os
import ssl
import logging
import json
from datetime import datetime
from pyVim import connect
from pyVmomi import vim
from urllib.error import URLError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cache for vSphere resources to avoid repeated API calls
RESOURCE_CACHE = {
    'timestamp': None,
    'resource_pools': [],
    'datastores': [],
    'networks': [],
    'templates': [],
    'cache_duration': 3600  # Cache validity in seconds (1 hour)
}

# Default resource IDs from environment variables
DEFAULT_RESOURCE_POOL_ID = os.environ.get('RESOURCE_POOL_ID', 'resgroup-9814670')
DEFAULT_DEV_RESOURCE_POOL_ID = os.environ.get('DEV_RESOURCE_POOL_ID', 'resgroup-3310245')
DEFAULT_DATASTORE_ID = os.environ.get('DATASTORE_ID', 'datastore-4395110')
DEFAULT_NETWORK_ID_PROD = os.environ.get('NETWORK_ID_PROD', 'dvportgroup-4545393')
DEFAULT_NETWORK_ID_DEV = os.environ.get('NETWORK_ID_DEV', 'dvportgroup-4545393')
DEFAULT_TEMPLATE_UUID = os.environ.get('TEMPLATE_UUID', 'vm-11682491')

def connect_to_vsphere():
    """Connect to vSphere server using environment variables"""
    server = os.environ.get('VSPHERE_SERVER')
    username = os.environ.get('VSPHERE_USER')
    password = os.environ.get('VSPHERE_PASSWORD')
    
    if not (server and username and password):
        logger.warning("Missing vSphere connection details in environment variables")
        return None
    
    try:
        # Create SSL context
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.verify_mode = ssl.CERT_NONE  # Disable certificate verification
        
        logger.info(f"Connecting to vSphere server: {server}")
        
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
        logger.error(f"Error connecting to vSphere server: {str(e)}")
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

def cache_is_valid():
    """Check if the current cache is valid"""
    if not RESOURCE_CACHE['timestamp']:
        return False
    
    cache_age = (datetime.now() - RESOURCE_CACHE['timestamp']).total_seconds()
    return cache_age < RESOURCE_CACHE['cache_duration']

def get_vsphere_resources(use_cache=True):
    """
    Get all vSphere resources needed for VM provisioning
    
    Args:
        use_cache: Whether to use cached data if available
        
    Returns:
        dict: Dictionary with resource pools, datastores, networks, and templates
    """
    # Return cached data if valid and requested
    if use_cache and cache_is_valid():
        logger.info(f"Using cached vSphere resources (last updated: {RESOURCE_CACHE['timestamp']})")
        return {
            'resource_pools': RESOURCE_CACHE['resource_pools'],
            'datastores': RESOURCE_CACHE['datastores'],
            'networks': RESOURCE_CACHE['networks'],
            'templates': RESOURCE_CACHE['templates']
        }
    
    logger.info("Fetching vSphere resources")
    
    service_instance = connect_to_vsphere()
    if not service_instance:
        logger.warning("Using default values for vSphere resources")
        return get_default_resources()
    
    content = service_instance.RetrieveContent()
    
    # Dictionary to store all resources
    resources = {
        'resource_pools': [],
        'datastores': [],
        'networks': [],
        'templates': []
    }
    
    try:
        # Get all datacenters to search in
        datacenters = get_all_obj(content, [vim.Datacenter])
        
        for dc in datacenters:
            # Get resource pools
            resource_pools = get_all_obj(content, [vim.ResourcePool], dc.hostFolder)
            for rp in resource_pools:
                info = get_resource_info('ResourcePool', rp, [DEFAULT_RESOURCE_POOL_ID, DEFAULT_DEV_RESOURCE_POOL_ID])
                resources['resource_pools'].append(info)
            
            # Get datastores
            datastores = get_all_obj(content, [vim.Datastore], dc.datastoreFolder)
            for ds in datastores:
                info = get_resource_info('Datastore', ds, [DEFAULT_DATASTORE_ID])
                resources['datastores'].append(info)
            
            # Get networks
            networks = get_all_obj(content, [vim.Network], dc.networkFolder)
            for net in networks:
                info = get_resource_info('Network', net, [DEFAULT_NETWORK_ID_PROD, DEFAULT_NETWORK_ID_DEV])
                resources['networks'].append(info)
            
            # Get VM templates
            vms = get_all_obj(content, [vim.VirtualMachine], dc.vmFolder)
            templates = [vm for vm in vms if vm.config and vm.config.template]
            for template in templates:
                info = get_resource_info('VirtualMachine', template, [DEFAULT_TEMPLATE_UUID])
                if info.get('is_template', False):
                    resources['templates'].append(info)
        
        # Update cache
        RESOURCE_CACHE['timestamp'] = datetime.now()
        RESOURCE_CACHE['resource_pools'] = resources['resource_pools']
        RESOURCE_CACHE['datastores'] = resources['datastores']
        RESOURCE_CACHE['networks'] = resources['networks']
        RESOURCE_CACHE['templates'] = resources['templates']
        
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
