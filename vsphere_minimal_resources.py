#!/usr/bin/env python3
"""
Minimal vSphere Resource Retrieval Script for SSB Build Server Web.

This optimized script retrieves only the minimum required vSphere resources
needed for VM location when creating a VM with the Terraform vSphere provider:
1. resource_pool_id
2. datastore_id
3. network_id
4. template_uuid

Usage:
    python vsphere_minimal_resources.py [--datacenter DATACENTER_NAME]
"""
import os
import sys
import argparse
import ssl
import json
import time
from datetime import datetime
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    from pyVim import connect
    from pyVmomi import vim
except ImportError:
    print("Required packages not installed. Run: pip install pyVmomi")
    sys.exit(1)

try:
    from vsphere_cache import vsphere_cache, cached_resource_fetcher
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    print("Cache module not available. Results won't be cached.")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_args():
    """Get command line arguments"""
    parser = argparse.ArgumentParser(description='Retrieve minimum required vSphere resource IDs')
    parser.add_argument('--server', help='vSphere server hostname or IP')
    parser.add_argument('--user', help='vSphere username')
    parser.add_argument('--password', help='vSphere password')
    parser.add_argument('--datacenter', help='Datacenter name to search within')
    parser.add_argument('--no-cache', action='store_true', help='Bypass cache and force retrieval from vSphere')
    parser.add_argument('--output', help='Output file path (default: vsphere_minimal_resources.json)')
    args = parser.parse_args()
    
    # Get credentials from args or environment variables
    args.server = args.server or os.environ.get('VSPHERE_SERVER')
    args.user = args.user or os.environ.get('VSPHERE_USER')
    args.password = args.password or os.environ.get('VSPHERE_PASSWORD')
    
    return args

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

def get_basic_resource_info(obj_type, obj):
    """Get only the minimal required information about a vSphere resource"""
    return {
        'name': obj.name,
        'id': str(obj._moId)
    }

def get_minimal_resource_pools(content, datacenter=None):
    """Get minimal resource pool information"""
    logger.info("Retrieving resource pools...")
    start_time = time.time()
    
    if datacenter:
        folder = datacenter.hostFolder
    else:
        folder = content.rootFolder
    
    resource_pools = get_all_obj(content, [vim.ResourcePool], folder)
    
    result = []
    for rp in resource_pools:
        result.append(get_basic_resource_info('ResourcePool', rp))
    
    logger.info(f"Retrieved {len(result)} resource pools in {time.time() - start_time:.2f} seconds")
    return result

def get_minimal_datastores(content, datacenter=None):
    """Get minimal datastore information"""
    logger.info("Retrieving datastores...")
    start_time = time.time()
    
    if datacenter:
        folder = datacenter.datastoreFolder
    else:
        folder = content.rootFolder
    
    datastores = get_all_obj(content, [vim.Datastore], folder)
    
    result = []
    for ds in datastores:
        result.append(get_basic_resource_info('Datastore', ds))
    
    logger.info(f"Retrieved {len(result)} datastores in {time.time() - start_time:.2f} seconds")
    return result

def get_minimal_networks(content, datacenter=None):
    """Get minimal network information"""
    logger.info("Retrieving networks...")
    start_time = time.time()
    
    if datacenter:
        folder = datacenter.networkFolder
    else:
        folder = content.rootFolder
    
    networks = get_all_obj(content, [vim.Network], folder)
    
    result = []
    for net in networks:
        result.append(get_basic_resource_info('Network', net))
    
    logger.info(f"Retrieved {len(result)} networks in {time.time() - start_time:.2f} seconds")
    return result

def get_minimal_templates(content, datacenter=None):
    """Get minimal VM template information"""
    logger.info("Retrieving VM templates...")
    start_time = time.time()
    
    if datacenter:
        folder = datacenter.vmFolder
    else:
        folder = content.rootFolder
    
    vms = get_all_obj(content, [vim.VirtualMachine], folder)
    
    result = []
    for vm in vms:
        if vm.config and vm.config.template:
            template_info = get_basic_resource_info('VirtualMachine', vm)
            template_info['is_template'] = True
            template_info['uuid'] = vm.config.uuid
            result.append(template_info)
    
    logger.info(f"Retrieved {len(result)} VM templates in {time.time() - start_time:.2f} seconds")
    return result

# Apply cache decorator if available
if CACHE_AVAILABLE:
    get_minimal_resource_pools = cached_resource_fetcher('resource_pools')(get_minimal_resource_pools)
    get_minimal_datastores = cached_resource_fetcher('datastores')(get_minimal_datastores)
    get_minimal_networks = cached_resource_fetcher('networks')(get_minimal_networks)
    get_minimal_templates = cached_resource_fetcher('templates')(get_minimal_templates)

def main():
    args = get_args()
    
    if not args.server or not args.user or not args.password:
        logger.error("vSphere connection information is incomplete")
        logger.error("Please provide --server, --user, and --password arguments or set")
        logger.error("VSPHERE_SERVER, VSPHERE_USER, and VSPHERE_PASSWORD environment variables")
        sys.exit(1)
    
    # Check if cache should be used
    use_cache = CACHE_AVAILABLE and not args.no_cache
    
    # Check if we can use the cache for all resources
    if use_cache:
        cache_valid = all([
            vsphere_cache.is_cache_valid('resource_pools'),
            vsphere_cache.is_cache_valid('datastores'),
            vsphere_cache.is_cache_valid('networks'),
            vsphere_cache.is_cache_valid('templates')
        ])
        
        if cache_valid:
            logger.info("Using cached vSphere resources")
            resources = {
                'ResourcePools': vsphere_cache.get_cached_resources('resource_pools'),
                'Datastores': vsphere_cache.get_cached_resources('datastores'),
                'Networks': vsphere_cache.get_cached_resources('networks'),
                'Templates': vsphere_cache.get_cached_resources('templates')
            }
            
            output_file = args.output or 'vsphere_minimal_resources.json'
            with open(output_file, 'w') as f:
                json.dump(resources, f, indent=2)
            
            print_resource_env_entries(resources)
            logger.info(f"Cached resource information saved to {output_file}")
            return
    
    # If cache is not valid or not available, retrieve from vSphere
    service_instance = connect_to_vsphere(args.server, args.user, args.password)
    if not service_instance:
        sys.exit(1)
    
    try:
        content = service_instance.RetrieveContent()
        
        # Get all datacenters
        datacenters = get_obj(content, [vim.Datacenter])
        logger.info(f"Found {len(datacenters)} datacenters")
        
        # Filter by specified datacenter if provided
        if args.datacenter:
            datacenters = [dc for dc in datacenters if dc.name == args.datacenter]
            if not datacenters:
                logger.error(f"Datacenter '{args.datacenter}' not found")
                connect.Disconnect(service_instance)
                sys.exit(1)
        
        # Dictionary to store all resources
        start_time = time.time()
        resources = {
            'ResourcePools': [],
            'Datastores': [],
            'Networks': [],
            'Templates': []
        }
        
        # Iterate through datacenters to find resources
        for dc in datacenters:
            logger.info(f"Exploring datacenter: {dc.name}")
            
            # Get resource pools (force_refresh=True if no_cache was specified)
            pools = get_minimal_resource_pools(content, dc, use_cache=use_cache, force_refresh=args.no_cache if use_cache else False)
            resources['ResourcePools'].extend(pools)
            
            # Get datastores
            stores = get_minimal_datastores(content, dc, use_cache=use_cache, force_refresh=args.no_cache if use_cache else False)
            resources['Datastores'].extend(stores)
            
            # Get networks
            nets = get_minimal_networks(content, dc, use_cache=use_cache, force_refresh=args.no_cache if use_cache else False)
            resources['Networks'].extend(nets)
            
            # Get VM templates
            templates = get_minimal_templates(content, dc, use_cache=use_cache, force_refresh=args.no_cache if use_cache else False)
            resources['Templates'].extend(templates)
        
        total_time = time.time() - start_time
        logger.info(f"Retrieved all resources in {total_time:.2f} seconds")
        
        # Output resource information as a JSON file
        output_file = args.output or 'vsphere_minimal_resources.json'
        with open(output_file, 'w') as f:
            json.dump(resources, f, indent=2)
        
        print_resource_env_entries(resources)
        logger.info(f"Resource information saved to {output_file}")
        
    except Exception as e:
        logger.error(f"Error retrieving vSphere resources: {str(e)}")
    finally:
        connect.Disconnect(service_instance)

def print_resource_env_entries(resources):
    """Print resource IDs formatted for environment variables"""
    print("\n=== Minimum Required vSphere Resource IDs ===\n")
    
    # Resource Pool (pick a suitable one)
    if resources['ResourcePools']:
        prod_pools = [rp for rp in resources['ResourcePools'] if 'prod' in rp['name'].lower()]
        if prod_pools:
            prod_pool = prod_pools[0]
            print(f"RESOURCE_POOL_ID={prod_pool['id']}  # {prod_pool['name']}")
        else:
            print(f"RESOURCE_POOL_ID={resources['ResourcePools'][0]['id']}  # {resources['ResourcePools'][0]['name']}")
    
    # Datastore (pick the first one)
    if resources['Datastores']:
        datastore = resources['Datastores'][0]
        print(f"DATASTORE_ID={datastore['id']}  # {datastore['name']}")
    
    # Network (pick a suitable one)
    if resources['Networks']:
        prod_nets = [net for net in resources['Networks'] if 'prod' in net['name'].lower()]
        if prod_nets:
            prod_net = prod_nets[0]
            print(f"NETWORK_ID={prod_net['id']}  # {prod_net['name']}")
        else:
            print(f"NETWORK_ID={resources['Networks'][0]['id']}  # {resources['Networks'][0]['name']}")
    
    # VM Template (pick RHEL9 if available)
    if resources['Templates']:
        rhel9_templates = [tpl for tpl in resources['Templates'] if 'rhel9' in tpl['name'].lower()]
        if rhel9_templates:
            template = rhel9_templates[0]
            print(f"TEMPLATE_UUID={template['id']}  # {template['name']}")
        else:
            template = resources['Templates'][0]
            print(f"TEMPLATE_UUID={template['id']}  # {template['name']}")
    
    print("\nNOTE: These are the minimum required values for VM location when creating a VM with the Terraform vSphere provider.")

if __name__ == "__main__":
    main()
