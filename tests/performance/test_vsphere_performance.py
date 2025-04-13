#!/usr/bin/env python3
"""
VSphere Performance Tests

This module contains all performance tests for vSphere operations, including:
- Resource retrieval performance
- Memory optimization
- Caching performance
"""
import os
import sys
import time
import logging
import argparse
import gc

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available. Install with: pip install psutil")

def measure_memory():
    """Measure current memory usage."""
    if not PSUTIL_AVAILABLE:
        return {"error": "psutil not available"}
        
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return {
        'rss': mem_info.rss,
        'rss_mb': round(mem_info.rss / (1024 * 1024), 2),
        'vms': mem_info.vms,
        'vms_mb': round(mem_info.vms / (1024 * 1024), 2)
    }

def test_hierarchical_loader_performance():
    """Test the performance of the hierarchical loader."""
    logger.info("Testing hierarchical loader performance...")
    
    # Get the loader
    import vsphere_hierarchical_loader
    loader = vsphere_hierarchical_loader.get_loader()
    
    # Test getting datacenters
    start_time = time.time()
    datacenters = loader.get_datacenters(force_load=True)
    dc_time = time.time() - start_time
    logger.info(f"Time to load {len(datacenters)} datacenters: {dc_time:.2f} seconds")
    
    if not datacenters:
        logger.warning("No datacenters found, aborting test")
        return
    
    # Test getting clusters for the first datacenter
    dc_name = datacenters[0]['name']
    start_time = time.time()
    clusters = loader.get_clusters(dc_name, force_load=True)
    cluster_time = time.time() - start_time
    logger.info(f"Time to load {len(clusters)} clusters for {dc_name}: {cluster_time:.2f} seconds")
    
    if not clusters:
        logger.warning("No clusters found, aborting test")
        return
    
    # Test getting resources for the first cluster
    cluster_id = clusters[0]['id']
    cluster_name = clusters[0]['name']
    start_time = time.time()
    resources = loader.get_resources(cluster_id, cluster_name, force_load=True)
    resources_time = time.time() - start_time
    
    # Log the results
    logger.info(f"Time to load resources for cluster {cluster_name}: {resources_time:.2f} seconds")
    logger.info(f"Resources loaded:")
    logger.info(f"  Datastores: {len(resources.get('datastores', []))}")
    logger.info(f"  Networks: {len(resources.get('networks', []))}")
    logger.info(f"  Resource Pools: {len(resources.get('resource_pools', []))}")
    logger.info(f"  Templates: {len(resources.get('templates', []))}")
    
    # Test performance with Redis cache (second run should be faster)
    logger.info("\nTesting cache performance (second run)...")
    start_time = time.time()
    resources = loader.get_resources(cluster_id, cluster_name, force_load=False)
    cached_time = time.time() - start_time
    logger.info(f"Time to load resources from cache: {cached_time:.2f} seconds")
    logger.info(f"Performance improvement: {resources_time/cached_time:.1f}x faster with cache")
    
    return {
        'datacenters_time': dc_time,
        'clusters_time': cluster_time,
        'resources_time': resources_time,
        'cached_time': cached_time,
        'cache_improvement': resources_time/cached_time
    }

def test_optimized_loader_performance():
    """Test the performance of the optimized loader."""
    logger.info("Testing optimized loader performance...")
    
    # Get resources using optimized loader
    import vsphere_optimized_loader
    
    start_time = time.time()
    resources = vsphere_optimized_loader.get_vsphere_resources(use_cache=False, force_refresh=True)
    first_run_time = time.time() - start_time
    
    logger.info(f"Time to load all resources (first run): {first_run_time:.2f} seconds")
    logger.info(f"Resources loaded:")
    logger.info(f"  Datastores: {len(resources.get('datastores', []))}")
    logger.info(f"  Networks: {len(resources.get('networks', []))}")
    logger.info(f"  Resource Pools: {len(resources.get('resource_pools', []))}")
    logger.info(f"  Templates: {len(resources.get('templates', []))}")
    
    # Test with cache
    logger.info("\nTesting cache performance (second run)...")
    start_time = time.time()
    resources = vsphere_optimized_loader.get_vsphere_resources(use_cache=True, force_refresh=False)
    cached_time = time.time() - start_time
    logger.info(f"Time to load resources from cache: {cached_time:.2f} seconds")
    logger.info(f"Performance improvement: {first_run_time/cached_time:.1f}x faster with cache")
    
    return {
        'first_run_time': first_run_time,
        'cached_time': cached_time,
        'cache_improvement': first_run_time/cached_time
    }

def test_memory_optimization(quick_test=False):
    """Test vSphere resource retrieval with different optimization settings."""
    if not PSUTIL_AVAILABLE:
        logger.error("Memory optimization tests require psutil. Install with: pip install psutil")
        return None
    
    logger.info("Testing memory optimization configurations...")
    
    # Options to test
    test_scenarios = [
        {
            "name": "Baseline (No Optimizations)",
            "env": {
                "VSPHERE_ENABLE_STREAMING": "false",
                "VSPHERE_COMPRESS_RESULTS": "false",
                "VSPHERE_EXPLICIT_GC": "false",
                "VSPHERE_DATA_PRUNING": "false"
            }
        },
        {
            "name": "Full Optimization",
            "env": {
                "VSPHERE_ENABLE_STREAMING": "true",
                "VSPHERE_COMPRESS_RESULTS": "true",
                "VSPHERE_EXPLICIT_GC": "true",
                "VSPHERE_DATA_PRUNING": "true"
            }
        }
    ]
    
    if not quick_test:
        # Add individual optimization tests
        test_scenarios.extend([
            {
                "name": "With Data Pruning Only",
                "env": {
                    "VSPHERE_ENABLE_STREAMING": "false", 
                    "VSPHERE_COMPRESS_RESULTS": "false",
                    "VSPHERE_EXPLICIT_GC": "false",
                    "VSPHERE_DATA_PRUNING": "true"
                }
            },
            {
                "name": "With Streaming Only",
                "env": {
                    "VSPHERE_ENABLE_STREAMING": "true",
                    "VSPHERE_COMPRESS_RESULTS": "false",
                    "VSPHERE_EXPLICIT_GC": "false",
                    "VSPHERE_DATA_PRUNING": "false"
                }
            },
            {
                "name": "With Explicit GC Only",
                "env": {
                    "VSPHERE_ENABLE_STREAMING": "false",
                    "VSPHERE_COMPRESS_RESULTS": "false", 
                    "VSPHERE_EXPLICIT_GC": "true",
                    "VSPHERE_DATA_PRUNING": "false"
                }
            },
            {
                "name": "With Compression Only",
                "env": {
                    "VSPHERE_ENABLE_STREAMING": "false",
                    "VSPHERE_COMPRESS_RESULTS": "true",
                    "VSPHERE_EXPLICIT_GC": "false",
                    "VSPHERE_DATA_PRUNING": "false"
                }
            }
        ])
    
    results = []
    
    for scenario in test_scenarios:
        logger.info(f"Testing scenario: {scenario['name']}")
        
        # Set environment variables for this test
        original_env = {}
        for key, value in scenario['env'].items():
            original_env[key] = os.environ.get(key)
            os.environ[key] = value
        
        try:
            # Force garbage collection before each test
            gc.collect()
            
            # Measure initial memory
            initial_memory = measure_memory()
            start_time = time.time()
            
            # Run the test
            import vsphere_minimal_resources
            vsphere_minimal_resources.main()
            
            # Measure final memory and time
            end_time = time.time()
            gc.collect()  # Force GC to get consistent measurements
            final_memory = measure_memory()
            
            # Calculate differences
            time_taken = end_time - start_time
            memory_diff = final_memory['rss_mb'] - initial_memory['rss_mb']
            
            # Record results
            results.append({
                'scenario': scenario['name'],
                'initial_memory_mb': initial_memory['rss_mb'],
                'peak_memory_mb': final_memory['rss_mb'],
                'memory_diff_mb': memory_diff,
                'time_seconds': round(time_taken, 2)
            })
            
            logger.info(f"Completed {scenario['name']}: {memory_diff} MB change, took {time_taken:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Error in {scenario['name']}: {str(e)}")
            results.append({
                'scenario': scenario['name'],
                'error': str(e)
            })
        finally:
            # Restore original environment
            for key, value in original_env.items():
                if value is None:
                    del os.environ[key]
                else:
                    os.environ[key] = value
                    
        # Wait a bit between tests to let system stabilize
        time.sleep(2)
    
    return results

def print_memory_results(results):
    """Print memory optimization results in a formatted table."""
    if not results:
        logger.error("No results to display")
        return
        
    # Print header
    print("\n===== MEMORY OPTIMIZATION TEST RESULTS =====\n")
    print(f"{'Scenario':<35} {'Initial (MB)':<15} {'Peak (MB)':<15} {'Change (MB)':<15} {'Time (s)':<10}")
    print("-" * 90)
    
    # Print rows
    for result in results:
        if 'error' in result:
            print(f"{result['scenario']:<35} ERROR: {result['error']}")
        else:
            print(f"{result['scenario']:<35} {result['initial_memory_mb']:<15.2f} "
                  f"{result['peak_memory_mb']:<15.2f} {result['memory_diff_mb']:<15.2f} "
                  f"{result['time_seconds']:<10.2f}")
    
    print("\n" + "=" * 90 + "\n")
    
    # Find best result for memory usage
    min_memory = min((r for r in results if 'peak_memory_mb' in r), key=lambda x: x['peak_memory_mb'])
    print(f"Best memory efficiency: {min_memory['scenario']} with peak usage of {min_memory['peak_memory_mb']:.2f} MB")
    
    # Find best result for speed
    min_time = min((r for r in results if 'time_seconds' in r), key=lambda x: x['time_seconds'])
    print(f"Fastest execution: {min_time['scenario']} at {min_time['time_seconds']:.2f} seconds")
    
    # Calculate improvement percentage
    if len(results) >= 2:
        baseline = next((r for r in results if r['scenario'] == "Baseline (No Optimizations)"), None)
        optimized = next((r for r in results if r['scenario'] == "Full Optimization"), None)
        
        if baseline and optimized and 'peak_memory_mb' in baseline and 'peak_memory_mb' in optimized:
            memory_improvement = (1 - (optimized['peak_memory_mb'] / baseline['peak_memory_mb'])) * 100
            time_improvement = (1 - (optimized['time_seconds'] / baseline['time_seconds'])) * 100
            
            print(f"\nFull optimization reduces memory usage by {memory_improvement:.1f}% and execution time by {time_improvement:.1f}%")

def compare_loader_performance():
    """Compare the performance of different loader implementations."""
    logger.info("Comparing performance between different loaders...")
    
    # Test the hierarchical loader
    import vsphere_hierarchical_loader
    logger.info("Testing hierarchical loader...")
    start_time = time.time()
    loader = vsphere_hierarchical_loader.get_loader()
    datacenters = loader.get_datacenters(force_load=True)
    if datacenters:
        dc_name = datacenters[0]['name']
        clusters = loader.get_clusters(dc_name, force_load=True)
        if clusters:
            resources = loader.get_resources(clusters[0]['id'], clusters[0]['name'], force_load=True)
    hierarchical_time = time.time() - start_time
    
    # Test the optimized loader
    import vsphere_optimized_loader
    logger.info("Testing optimized loader...")
    start_time = time.time()
    resources = vsphere_optimized_loader.get_vsphere_resources(use_cache=False, force_refresh=True)
    optimized_time = time.time() - start_time
    
    # Test the minimal resources loader
    import vsphere_minimal_resources
    logger.info("Testing minimal resources loader...")
    start_time = time.time()
    vsphere_minimal_resources.main()
    minimal_time = time.time() - start_time
    
    # Print comparison
    print("\n===== LOADER PERFORMANCE COMPARISON =====\n")
    print(f"Hierarchical Loader: {hierarchical_time:.2f} seconds")
    print(f"Optimized Loader: {optimized_time:.2f} seconds")
    print(f"Minimal Resources Loader: {minimal_time:.2f} seconds")
    
    fastest = min([
        ("Hierarchical", hierarchical_time),
        ("Optimized", optimized_time),
        ("Minimal", minimal_time)
    ], key=lambda x: x[1])
    
    print(f"\nFastest loader: {fastest[0]} ({fastest[1]:.2f} seconds)")
    
    return {
        'hierarchical': hierarchical_time,
        'optimized': optimized_time,
        'minimal': minimal_time
    }

def main():
    """Main entry point for the performance tests."""
    parser = argparse.ArgumentParser(description='VSphere Performance Tests')
    parser.add_argument('--test', choices=['all', 'hierarchical', 'optimized', 'memory', 'compare'], 
                        default='all', help='Which test to run')
    parser.add_argument('--quick', action='store_true', help='Run tests in quick mode (fewer iterations)')
    args = parser.parse_args()
    
    # Header
    print("\n===== VSPHERE PERFORMANCE TESTS =====\n")
    
    test = args.test.lower()
    
    if test in ['all', 'hierarchical']:
        print("\n----- Hierarchical Loader Performance -----\n")
        test_hierarchical_loader_performance()
    
    if test in ['all', 'optimized']:
        print("\n----- Optimized Loader Performance -----\n")
        test_optimized_loader_performance()
    
    if test in ['all', 'memory']:
        if not PSUTIL_AVAILABLE:
            print("\nWARNING: Memory tests require psutil package. Install with: pip install psutil")
        else:
            print("\n----- Memory Optimization Tests -----\n")
            results = test_memory_optimization(args.quick)
            print_memory_results(results)
    
    if test in ['all', 'compare']:
        print("\n----- Loader Comparison Tests -----\n")
        compare_loader_performance()
    
    print("\n===== TEST COMPLETE =====\n")

if __name__ == "__main__":
    main()
