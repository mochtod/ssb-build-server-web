#!/usr/bin/env python3
"""
Script to retrieve vSphere resource IDs needed for VM provisioning.
This script retrieves resource pools, datastores, networks and templates from vSphere.

Usage:
    python get_vsphere_resources.py [--datacenter DATACENTER_NAME]
"""
import os
import sys
import argparse
import ssl
import json
from pyVim import connect
from pyVmomi import vim
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_args():
    """Get command line arguments"""
    parser = argparse.ArgumentParser(description='Retrieve vSphere resource IDs')
    parser.add_argument('--server', help='vSphere server hostname or IP')
    parser.add_argument('--user', help='vSphere username')
    parser.add_argument('--password', help='vSphere password')
    parser.add_argument('--datacenter', help='Datacenter name to search within')
    args = parser.parse_args()
    
    # Get credentials from args or environment variables
    args.server = args.server or os.environ.get('VSPHERE_SERVER')
    args.user = args.user or os.environ.get('VSPHERE_USER')
    args.password = args.password or os.environ.get('VSPHERE_PASSWORD')
    
    return args

def get_obj(content, vimtype, name=None):
    """Get vSphere object by type and name"""
    container = content.viewManager.CreateContainerView(
        content.rootFolder, vimtype, True)
    obj_list = container.view
    container.Destroy()
    
    if name:
        for obj in obj_list:
            if obj.name == name:
                return obj
    
    return obj_list

def get_all_obj(content, vimtype, folder=None, recurse=True):
    """Get all vSphere objects of a specified type"""
    if not folder:
        folder = content.rootFolder
    
    container = content.viewManager.CreateContainerView(folder, vimtype, recurse)
    obj_list = container.view
    container.Destroy()
    return obj_list

def connect_to_vsphere(server, username, password):
    """Connect to vSphere server"""
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

def get_resource_info(obj_type, obj):
    """Get basic information about a vSphere resource"""
    info = {
        'name': obj.name,
        'id': str(obj._moId),
        'type': obj_type
    }
    
    # Add type-specific information
    if obj_type == 'ResourcePool':
        if hasattr(obj, 'parent') and obj.parent:
            info['parent'] = obj.parent.name
        if hasattr(obj, 'summary'):
            info['cpu'] = {
                'limit': obj.summary.config.cpuAllocation.limit,
                'reservation': obj.summary.config.cpuAllocation.reservation,
                'shares': obj.summary.config.cpuAllocation.shares.shares
            }
            info['memory'] = {
                'limit': obj.summary.config.memoryAllocation.limit,
                'reservation': obj.summary.config.memoryAllocation.reservation,
                'shares': obj.summary.config.memoryAllocation.shares.shares
            }
    
    elif obj_type == 'Datastore':
        if hasattr(obj, 'summary'):
            summary = obj.summary
            info['capacity'] = summary.capacity
            info['free_space'] = summary.freeSpace
            info['type'] = summary.type
            info['accessible'] = summary.accessible
    
    elif obj_type == 'Network':
        if isinstance(obj, vim.DistributedVirtualPortgroup):
            info['network_type'] = 'dvPortgroup'
            info['vlan_id'] = obj.config.defaultPortConfig.vlan.vlanId if hasattr(obj.config.defaultPortConfig, 'vlan') else None
            info['dvs_name'] = obj.config.distributedVirtualSwitch.name if hasattr(obj.config, 'distributedVirtualSwitch') else None
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

def format_env_file_entry(resource_type, resource_id, name, description):
    """Format a resource entry for .env file"""
    return f"{resource_type}={resource_id}  # {name} - {description}"

def main():
    args = get_args()
    
    if not args.server or not args.user or not args.password:
        logger.error("vSphere connection information is incomplete")
        logger.error("Please provide --server, --user, and --password arguments or set")
        logger.error("VSPHERE_SERVER, VSPHERE_USER, and VSPHERE_PASSWORD environment variables")
        sys.exit(1)
    
    service_instance = connect_to_vsphere(args.server, args.user, args.password)
    if not service_instance:
        sys.exit(1)
    
    content = service_instance.RetrieveContent()
    
    # Get all datacenters
    datacenters = get_obj(content, [vim.Datacenter])
    print(f"\nFound {len(datacenters)} datacenters:")
    for dc in datacenters:
        print(f" - {dc.name}")
    
    # Filter by specified datacenter if provided
    if args.datacenter:
        datacenters = [dc for dc in datacenters if dc.name == args.datacenter]
        if not datacenters:
            logger.error(f"Datacenter '{args.datacenter}' not found")
            connect.Disconnect(service_instance)
            sys.exit(1)
    
    # Dictionary to store all resources
    resources = {
        'ResourcePools': [],
        'Datastores': [],
        'Networks': [],
        'Templates': []
    }
    
    # Iterate through datacenters to find resources
    for dc in datacenters:
        print(f"\nExploring datacenter: {dc.name}")
        
        # Get resource pools
        resource_pools = get_all_obj(content, [vim.ResourcePool], dc.hostFolder)
        print(f"Found {len(resource_pools)} resource pools:")
        for rp in resource_pools:
            info = get_resource_info('ResourcePool', rp)
            resources['ResourcePools'].append(info)
            print(f" - {rp.name} (ID: {info['id']})")
        
        # Get datastores
        datastores = get_all_obj(content, [vim.Datastore], dc.datastoreFolder)
        print(f"Found {len(datastores)} datastores:")
        for ds in datastores:
            info = get_resource_info('Datastore', ds)
            resources['Datastores'].append(info)
            capacity_gb = round(info.get('capacity', 0) / (1024**3), 2)
            free_gb = round(info.get('free_space', 0) / (1024**3), 2)
            print(f" - {ds.name} (ID: {info['id']}, Type: {info.get('type', 'unknown')}, Capacity: {capacity_gb} GB, Free: {free_gb} GB)")
        
        # Get networks
        networks = get_all_obj(content, [vim.Network], dc.networkFolder)
        print(f"Found {len(networks)} networks:")
        for net in networks:
            info = get_resource_info('Network', net)
            resources['Networks'].append(info)
            net_type = info.get('network_type', 'unknown')
            vlan = info.get('vlan_id', 'N/A')
            print(f" - {net.name} (ID: {info['id']}, Type: {net_type}, VLAN: {vlan})")
        
        # Get VM templates
        vms = get_all_obj(content, [vim.VirtualMachine], dc.vmFolder)
        templates = [vm for vm in vms if vm.config and vm.config.template]
        print(f"Found {len(templates)} VM templates:")
        for template in templates:
            info = get_resource_info('VirtualMachine', template)
            if info.get('is_template', False):
                resources['Templates'].append(info)
                guest_id = info.get('guest_id', 'unknown')
                cpu = info.get('num_cpu', 'unknown')
                memory = info.get('memory_mb', 'unknown')
                print(f" - {template.name} (ID: {info['id']}, Guest OS: {guest_id}, CPU: {cpu}, Memory: {memory} MB)")
    
    # Output environment variable assignments for .env file
    print("\n\n=== .env File Entries ===\n")
    
    # Production Resource Pool (pick a suitable one)
    if resources['ResourcePools']:
        prod_pools = [rp for rp in resources['ResourcePools'] if 'prod' in rp['name'].lower()]
        if prod_pools:
            prod_pool = prod_pools[0]
            print(f"RESOURCE_POOL_ID={prod_pool['id']}  # {prod_pool['name']} - Production resource pool")
        else:
            print(f"RESOURCE_POOL_ID={resources['ResourcePools'][0]['id']}  # {resources['ResourcePools'][0]['name']} - Resource pool")
    
    # Development Resource Pool (pick a suitable one)
    if resources['ResourcePools']:
        dev_pools = [rp for rp in resources['ResourcePools'] if 'dev' in rp['name'].lower() or 'nonprod' in rp['name'].lower()]
        if dev_pools:
            dev_pool = dev_pools[0]
            print(f"DEV_RESOURCE_POOL_ID={dev_pool['id']}  # {dev_pool['name']} - Development resource pool")
        else:
            print(f"DEV_RESOURCE_POOL_ID={resources['ResourcePools'][0]['id']}  # {resources['ResourcePools'][0]['name']} - Resource pool")
    
    # Datastore (pick the one with most free space)
    if resources['Datastores']:
        datastore = max(resources['Datastores'], key=lambda ds: ds.get('free_space', 0))
        print(f"DATASTORE_ID={datastore['id']}  # {datastore['name']} - Datastore with {round(datastore.get('free_space', 0) / (1024**3), 2)} GB free")
    
    # Production Network (pick a suitable one)
    if resources['Networks']:
        prod_nets = [net for net in resources['Networks'] if 'prod' in net['name'].lower()]
        if prod_nets:
            prod_net = prod_nets[0]
            print(f"NETWORK_ID_PROD={prod_net['id']}  # {prod_net['name']} - Production network")
        else:
            print(f"NETWORK_ID_PROD={resources['Networks'][0]['id']}  # {resources['Networks'][0]['name']} - Network")
    
    # Development Network (pick a suitable one)
    if resources['Networks']:
        dev_nets = [net for net in resources['Networks'] if 'dev' in net['name'].lower() or 'nonprod' in net['name'].lower()]
        if dev_nets:
            dev_net = dev_nets[0]
            print(f"NETWORK_ID_DEV={dev_net['id']}  # {dev_net['name']} - Development network")
        else:
            print(f"NETWORK_ID_DEV={resources['Networks'][0]['id']}  # {resources['Networks'][0]['name']} - Network")
    
    # VM Template (pick RHEL9 if available)
    if resources['Templates']:
        rhel9_templates = [tpl for tpl in resources['Templates'] if 'rhel9' in tpl['name'].lower()]
        if rhel9_templates:
            template = rhel9_templates[0]
            print(f"TEMPLATE_UUID={template['id']}  # {template['name']} - RHEL 9 template")
        else:
            template = resources['Templates'][0]
            print(f"TEMPLATE_UUID={template['id']}  # {template['name']} - VM template")
    
    # Write to JSON file for reference
    with open('vsphere_resources.json', 'w') as f:
        json.dump(resources, f, indent=2)
    print(f"\nDetailed resource information saved to vsphere_resources.json")
    
    connect.Disconnect(service_instance)
    print("\nNOTE: Add these lines to your .env file, replacing the placeholders.")

if __name__ == "__main__":
    main()
