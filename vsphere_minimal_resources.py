#!/usr/bin/env python3
"""
Minimal vSphere Resource Retrieval Script for SSB Build Server Web.

This memory-optimized script retrieves only the minimum required vSphere resources
needed for VM location when creating a VM with the Terraform vSphere provider:
1. resource_pool_id
2. datastore_id
3. network_id
4. template_uuid

This version includes memory optimizations like data pruning, compression, 
and streaming results to reduce peak memory usage.

Usage:
    python vsphere_minimal_resources.py [--datacenter DATACENTER_NAME]
"""
import os
import sys
import argparse
import ssl
import json
import time
import gzip
import gc
from datetime import datetime
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Generator, Iterator

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

# Memory optimization settings
COMPRESS_RESULTS = os.environ.get('VSPHERE_COMPRESS_RESULTS', 'true').lower() == 'true'
ENABLE_STREAMING = os.environ.get('VSPHERE_ENABLE_STREAMING', 'true').lower() == 'true'
BATCH_SIZE = int(os.environ.get('VSPHERE_BATCH_SIZE', '50'))
EXPLICIT_GC = os.environ.get('VSPHERE_EXPLICIT_GC', 'true').lower() == 'true'

# Only keep these essential attributes to reduce memory usage
ESSENTIAL_ATTRIBUTES = {
    'resource_pools': ['name', 'id'],
    'datastores': ['name', 'id', 'free_gb', 'capacity', 'free_space'],
    'networks': ['name', 'id'],
    'templates': ['name', 'id', 'uuid', 'is_template']
}

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def prune_resource_attributes(resource: Dict[str, Any], resource_type: str) -> Dict[str, Any]:
    """Remove unnecessary attributes from a resource object to save memory."""
    if resource_type not in ESSENTIAL_ATTRIBUTES:
        return resource
        
    essential_attrs = set(ESSENTIAL_ATTRIBUTES[resource_type])
    return {k: v for k, v in resource.items() if k in essential_attrs}

def compress_data(data: Any) -> bytes:
    """Compress data using gzip."""
    if not COMPRESS_RESULTS:
        return json.dumps(data).encode('utf-8')
        
    json_str = json.dumps(data)
    return gzip.compress(json_str.encode('utf-8'))

def decompress_data(compressed_data: bytes) -> Any:
    """Decompress data using gzip."""
    if not COMPRESS_RESULTS:
        return json.loads(compressed_data.decode('utf-8'))
        
    decompressed = gzip.decompress(compressed_data)
    return json.loads(decompressed.decode('utf-8'))

def stream_resources(objects, processor_func, resource_type, batch_size=BATCH_SIZE):
    """Process resources in batches to reduce memory usage."""
    batch = []
    count = 0
    
    for obj in objects:
        batch.append(obj)
        count += 1
        
        if len(batch) >= batch_size:
            processed_batch = processor_func(batch, resource_type)
            yield from processed_batch
            
            # Clear batch and explicitly run garbage collection if needed
            batch = []
            if EXPLICIT_GC:
                gc.collect()
    
    # Process any remaining items in the final batch
    if batch:
        processed_batch = processor_func(batch, resource_type)
        yield from processed_batch

def process_batch(batch, resource_type):
    """Process a batch of resources, applying pruning to each item."""
    processed = []
    for item in batch:
        processed_item = get_basic_resource_info(resource_type, item)
        pruned_item = prune_resource_attributes(processed_item, resource_type)
        processed.append(pruned_item)
    return processed

def get_args():
    """Get command line arguments"""
    parser = argparse.ArgumentParser(description='Retrieve minimum required vSphere resource IDs')
    parser.add_argument('--server', help='vSphere server hostname or IP')
    parser.add_argument('--user', help='vSphere username')
    parser.add_argument('--password', help='vSphere password')
    parser.add_argument('--datacenter', help='Datacenter name to search within')
    parser.add_argument('--no-cache', action='store_true', help='Bypass cache and force retrieval from vSphere')
    parser.add_argument('--output', help='Output file path (default: vsphere_minimal_resources.json)')
    parser.add_argument('--memory-stats', action='store_true', help='Display memory usage statistics')
    args = parser.parse_args()
    
    # Get credentials from args or environment variables
    args.server = args.server or os.environ.get('VSPHERE_SERVER')
    args.user = args.user or os.environ.get('VSPHERE_USER')
    args.password = args.password or os.environ.get('VSPHERE_PASSWORD')
    
    return args

def measure_memory_usage():
    """Measure and return current memory usage of the process."""
    import psutil
    import os
    
    try:
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        return {
            'rss': mem_info.rss,  # Resident Set Size
            'rss_mb': round(mem_info.rss / (1024 * 1024), 2),
            'vms': mem_info.vms,  # Virtual Memory Size
            'vms_mb': round(mem_info.vms / (1024 * 1024), 2)
        }
    except Exception as e:
        logger.warning(f"Unable to measure memory usage: {e}")
        return None

def connect_to_vsphere(server, username, password):
    """Connect to vSphere server"""
    try:
        # Create SSL context
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.verify_mode = ssl.CERT_NONE  # Disable certificate verification
        
        logger.info(f"Connecting to vSphere server: {server}")
        
        # Set socket timeout to avoid hanging indefinitely
        import socket
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(30)  # 30 second timeout
        
        try:
            # Attempt connection
            service_instance = connect.SmartConnect(
                host=server,
                user=username,
                pwd=password,
                sslContext=context
            )
        finally:
            # Restore original timeout
            socket.setdefaulttimeout(old_timeout)
        
        if not service_instance:
            logger.error("Failed to connect to vSphere server")
            return None
        
        logger.info("Successfully connected to vSphere server")
        return service_instance
        
    except Exception as e:
        logger.error(f"Error connecting to vSphere server: {str(e)}")
        return None

def get_obj(content, vimtype, name=None):
    """Get vSphere object by type and name with controlled memory usage"""
    container = content.viewManager.CreateContainerView(
        content.rootFolder, vimtype, True)
    
    try:
        if name:
            # If searching for a specific name, iterate without loading all objects into memory
            for obj in container.view:
                if obj.name == name:
                    return obj
            return None
        else:
            # If memory usage is a concern, use a generator
            if ENABLE_STREAMING:
                obj_list = list(container.view)
            else:
                obj_list = container.view
            return obj_list
    finally:
        # Always destroy the container view to free resources
        container.Destroy()

def get_all_obj(content, vimtype, folder=None, recurse=True):
    """Get all vSphere objects of a specified type with memory efficiency"""
    if not folder:
        folder = content.rootFolder
    
    container = content.viewManager.CreateContainerView(folder, vimtype, recurse)
    
    try:
        # Return objects as list or generator based on memory optimization settings
        if ENABLE_STREAMING:
            # Create a separate list to avoid memory leak from container view reference
            result = list(container.view)
            return result
        else:
            return container.view
    finally:
        # Always destroy the container view to free resources
        container.Destroy()

def get_basic_resource_info(obj_type, obj):
    """Get only the minimal required information about a vSphere resource"""
    info = {
        'name': obj.name,
        'id': str(obj._moId)
    }
    
    # Add type-specific attributes
    if obj_type == 'templates' and hasattr(obj, 'config') and obj.config:
        info['uuid'] = getattr(obj.config, 'uuid', None)
        info['is_template'] = True
    elif obj_type == 'datastores' and hasattr(obj, 'summary'):
        summary = obj.summary
        if hasattr(summary, 'capacity'):
            info['capacity'] = summary.capacity
        if hasattr(summary, 'freeSpace'):
            info['free_space'] = summary.freeSpace
            info['free_gb'] = round(summary.freeSpace / (1024**3), 2)
    
    return info

def get_minimal_resource_pools(content, datacenter=None):
    """Get minimal resource pool information using streaming for memory efficiency"""
    logger.info("Retrieving resource pools...")
    start_time = time.time()
    
    if datacenter:
        folder = datacenter.hostFolder
    else:
        folder = content.rootFolder
    
    resource_pools = get_all_obj(content, [vim.ResourcePool], folder)
    
    if ENABLE_STREAMING:
        # Process in batches when streaming is enabled
        result = list(stream_resources(resource_pools, process_batch, 'resource_pools'))
    else:
        # Traditional processing when streaming is disabled
        result = []
        for rp in resource_pools:
            info = get_basic_resource_info('resource_pools', rp)
            pruned_info = prune_resource_attributes(info, 'resource_pools')
            result.append(pruned_info)
    
    logger.info(f"Retrieved {len(result)} resource pools in {time.time() - start_time:.2f} seconds")
    return result

def get_minimal_datastores(content, datacenter=None):
    """Get minimal datastore information using streaming for memory efficiency"""
    logger.info("Retrieving datastores...")
    start_time = time.time()
    
    if datacenter:
        folder = datacenter.datastoreFolder
    else:
        folder = content.rootFolder
    
    datastores = get_all_obj(content, [vim.Datastore], folder)
    
    if ENABLE_STREAMING:
        # Process in batches when streaming is enabled
        result = list(stream_resources(datastores, process_batch, 'datastores'))
    else:
        # Traditional processing when streaming is disabled
        result = []
        for ds in datastores:
            info = get_basic_resource_info('datastores', ds)
            pruned_info = prune_resource_attributes(info, 'datastores')
            result.append(pruned_info)
    
    logger.info(f"Retrieved {len(result)} datastores in {time.time() - start_time:.2f} seconds")
    return result

def get_minimal_networks(content, datacenter=None):
    """Get minimal network information using streaming for memory efficiency"""
    logger.info("Retrieving networks...")
    start_time = time.time()
    
    if datacenter:
        folder = datacenter.networkFolder
    else:
        folder = content.rootFolder
    
    networks = get_all_obj(content, [vim.Network], folder)
    
    if ENABLE_STREAMING:
        # Process in batches when streaming is enabled
        result = list(stream_resources(networks, process_batch, 'networks'))
    else:
        # Traditional processing when streaming is disabled
        result = []
        for net in networks:
            info = get_basic_resource_info('networks', net)
            pruned_info = prune_resource_attributes(info, 'networks')
            result.append(pruned_info)
    
    logger.info(f"Retrieved {len(result)} networks in {time.time() - start_time:.2f} seconds")
    return result

def get_minimal_templates(content, datacenter=None):
    """Get minimal VM template information using streaming for memory efficiency"""
    logger.info("Retrieving VM templates...")
    start_time = time.time()
    
    if datacenter:
        folder = datacenter.vmFolder
    else:
        folder = content.rootFolder
    
    vms = get_all_obj(content, [vim.VirtualMachine], folder)
    
    # Pre-filter for templates to reduce processing overhead
    templates = []
    for vm in vms:
        try:
            if vm.config and vm.config.template:
                templates.append(vm)
        except Exception as e:
            # Skip problematic VMs
            logger.debug(f"Error checking template status for VM: {str(e)}")
    
    # Process templates using streaming or traditional method
    if ENABLE_STREAMING:
        # Process in batches when streaming is enabled
        result = list(stream_resources(templates, process_batch, 'templates'))
    else:
        # Traditional processing when streaming is disabled
        result = []
        for vm in templates:
            info = get_basic_resource_info('templates', vm)
            pruned_info = prune_resource_attributes(info, 'templates')
            result.append(pruned_info)
    
    logger.info(f"Retrieved {len(result)} VM templates in {time.time() - start_time:.2f} seconds")
    return result

# Apply cache decorator if available
if CACHE_AVAILABLE:
    get_minimal_resource_pools = cached_resource_fetcher('resource_pools')(get_minimal_resource_pools)
    get_minimal_datastores = cached_resource_fetcher('datastores')(get_minimal_datastores)
    get_minimal_networks = cached_resource_fetcher('networks')(get_minimal_networks)
    get_minimal_templates = cached_resource_fetcher('templates')(get_minimal_templates)

def log_memory_usage_statistics():
    """Log detailed memory usage statistics"""
    memory_stats = measure_memory_usage()
    if memory_stats:
        logger.info(f"Memory usage - RSS: {memory_stats['rss_mb']} MB, VMS: {memory_stats['vms_mb']} MB")
    
    # Force garbage collection to get accurate stats
    if EXPLICIT_GC:
        collected = gc.collect()
        logger.debug(f"Garbage collector: collected {collected} objects")
        
        # Log memory after GC
        memory_stats_after_gc = measure_memory_usage()
        if memory_stats_after_gc:
            logger.info(f"Memory after GC - RSS: {memory_stats_after_gc['rss_mb']} MB, VMS: {memory_stats_after_gc['vms_mb']} MB")

def main():
    args = get_args()
    
    if not args.server or not args.user or not args.password:
        logger.error("vSphere connection information is incomplete")
        logger.error("Please provide --server, --user, and --password arguments or set")
        logger.error("VSPHERE_SERVER, VSPHERE_USER, and VSPHERE_PASSWORD environment variables")
        sys.exit(1)
    
    # Log memory usage if requested
    if args.memory_stats:
        try:
            import psutil
            log_memory_usage_statistics()
        except ImportError:
            logger.warning("psutil module not available for memory statistics. Install with: pip install psutil")
    
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
            
            # Optionally compress output
            if COMPRESS_RESULTS:
                # Store compressed data
                with open(output_file + '.gz', 'wb') as f:
                    f.write(compress_data(resources))
                logger.info(f"Compressed resource information saved to {output_file}.gz")
                
                # Also provide uncompressed for user convenience
                with open(output_file, 'w') as f:
                    json.dump(resources, f, indent=2)
            else:
                # Store uncompressed
                with open(output_file, 'w') as f:
                    json.dump(resources, f, indent=2)
            
            print_resource_env_entries(resources)
            logger.info(f"Cached resource information saved to {output_file}")
            
            # Log memory usage after cache retrieval
            if args.memory_stats:
                log_memory_usage_statistics()
                
            return
    
    # If cache is not valid or not available, retrieve from vSphere
    service_instance = connect_to_vsphere(args.server, args.user, args.password)
    if not service_instance:
        sys.exit(1)
    
    try:
        # Log memory usage before main processing
        if args.memory_stats:
            logger.info("Memory usage before retrieving vSphere resources:")
            log_memory_usage_statistics()
            
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
            
            # Run garbage collection after each major resource retrieval if enabled
            if EXPLICIT_GC:
                gc.collect()
                
            # Get datastores
            stores = get_minimal_datastores(content, dc, use_cache=use_cache, force_refresh=args.no_cache if use_cache else False)
            resources['Datastores'].extend(stores)
            
            # Run garbage collection after each major resource retrieval if enabled
            if EXPLICIT_GC:
                gc.collect()
                
            # Get networks
            nets = get_minimal_networks(content, dc, use_cache=use_cache, force_refresh=args.no_cache if use_cache else False)
            resources['Networks'].extend(nets)
            
            # Run garbage collection after each major resource retrieval if enabled
            if EXPLICIT_GC:
                gc.collect()
                
            # Get VM templates
            templates = get_minimal_templates(content, dc, use_cache=use_cache, force_refresh=args.no_cache if use_cache else False)
            resources['Templates'].extend(templates)
            
            # Log memory usage after processing a datacenter if requested
            if args.memory_stats:
                logger.info(f"Memory usage after processing datacenter {dc.name}:")
                log_memory_usage_statistics()
        
        total_time = time.time() - start_time
        logger.info(f"Retrieved all resources in {total_time:.2f} seconds")
        
        # Output resource information as a JSON file
        output_file = args.output or 'vsphere_minimal_resources.json'
        
        # Optionally compress output
        if COMPRESS_RESULTS:
            # Store compressed data
            with open(output_file + '.gz', 'wb') as f:
                f.write(compress_data(resources))
            logger.info(f"Compressed resource information saved to {output_file}.gz")
            
            # Also provide uncompressed for user convenience
            with open(output_file, 'w') as f:
                json.dump(resources, f, indent=2)
        else:
            # Store uncompressed
            with open(output_file, 'w') as f:
                json.dump(resources, f, indent=2)
        
        print_resource_env_entries(resources)
        logger.info(f"Resource information saved to {output_file}")
        
        # Log final memory usage if requested
        if args.memory_stats:
            logger.info("Final memory usage:")
            log_memory_usage_statistics()
            
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
