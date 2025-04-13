#!/usr/bin/env python3
"""
Measure the performance of the hierarchical loader.
"""
import time
import logging
import vsphere_hierarchical_loader

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')

def test_performance():
    """Test the performance of retrieving resources."""
    
    print("Starting performance test...")
    
    # Get the loader
    loader = vsphere_hierarchical_loader.get_loader()
    
    # Test getting datacenters
    start_time = time.time()
    datacenters = loader.get_datacenters(force_load=True)
    dc_time = time.time() - start_time
    print(f"Time to load {len(datacenters)} datacenters: {dc_time:.2f} seconds")
    
    if not datacenters:
        print("No datacenters found, aborting test")
        return
    
    # Test getting clusters for the first datacenter
    dc_name = datacenters[0]['name']
    start_time = time.time()
    clusters = loader.get_clusters(dc_name, force_load=True)
    cluster_time = time.time() - start_time
    print(f"Time to load {len(clusters)} clusters for {dc_name}: {cluster_time:.2f} seconds")
    
    if not clusters:
        print("No clusters found, aborting test")
        return
    
    # Test getting resources for the first cluster
    cluster_id = clusters[0]['id']
    cluster_name = clusters[0]['name']
    start_time = time.time()
    resources = loader.get_resources(cluster_id, cluster_name, force_load=True)
    resources_time = time.time() - start_time
    
    # Print the results
    print(f"Time to load resources for cluster {cluster_name}: {resources_time:.2f} seconds")
    print(f"Resources loaded:")
    print(f"  Datastores: {len(resources.get('datastores', []))}")
    print(f"  Networks: {len(resources.get('networks', []))}")
    print(f"  Resource Pools: {len(resources.get('resource_pools', []))}")
    print(f"  Templates: {len(resources.get('templates', []))}")
    
    # Test performance with Redis cache (second run should be faster)
    print("\nTesting cache performance (second run)...")
    start_time = time.time()
    resources = loader.get_resources(cluster_id, cluster_name, force_load=False)
    cached_time = time.time() - start_time
    print(f"Time to load resources from cache: {cached_time:.2f} seconds")
    print(f"Performance improvement: {resources_time/cached_time:.1f}x faster with cache")

if __name__ == "__main__":
    test_performance()
