#!/usr/bin/env python3
"""
Memory Optimization Test Script

This script measures the memory usage improvements from our optimization efforts.
It compares memory usage before and after the optimizations for vSphere resource retrieval.
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

def test_vsphere_resource_retrieval(config):
    """Test vSphere resource retrieval with different optimization settings."""
    
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
            if config.get('use_minimal'):
                import vsphere_minimal_resources
                vsphere_minimal_resources.main()
            else:
                import vsphere_hierarchical_loader
                loader = vsphere_hierarchical_loader.get_loader()
                datacenters = loader.get_datacenters(force_load=True)
                for dc in datacenters:
                    clusters = loader.get_clusters(dc['name'], force_load=True)
                    if clusters and len(clusters) > 0:
                        loader.get_resources(clusters[0]['id'], force_load=True)
            
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

def print_results(results):
    """Print results in a formatted table."""
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
    min_memory = min(r for r in results if 'peak_memory_mb' in r)
    print(f"Best memory efficiency: {min_memory['scenario']} with peak usage of {min_memory['peak_memory_mb']:.2f} MB")
    
    # Find best result for speed
    min_time = min(r for r in results if 'time_seconds' in r)
    print(f"Fastest execution: {min_time['scenario']} at {min_time['time_seconds']:.2f} seconds")
    
    # Calculate improvement percentage
    if len(results) >= 2:
        baseline = next((r for r in results if r['scenario'] == "Baseline (No Optimizations)"), None)
        optimized = next((r for r in results if r['scenario'] == "Full Optimization"), None)
        
        if baseline and optimized and 'peak_memory_mb' in baseline and 'peak_memory_mb' in optimized:
            memory_improvement = (1 - (optimized['peak_memory_mb'] / baseline['peak_memory_mb'])) * 100
            time_improvement = (1 - (optimized['time_seconds'] / baseline['time_seconds'])) * 100
            
            print(f"\nFull optimization reduces memory usage by {memory_improvement:.1f}% and execution time by {time_improvement:.1f}%")

def main():
    parser = argparse.ArgumentParser(description='Test memory optimization in vSphere resource retrieval')
    parser.add_argument('--minimal', action='store_true', help='Test minimal resources module instead of hierarchical loader')
    parser.add_argument('--quick', action='store_true', help='Run only baseline and full optimization tests')
    args = parser.parse_args()
    
    if not PSUTIL_AVAILABLE:
        logger.error("This test requires the psutil package. Install with: pip install psutil")
        sys.exit(1)
    
    logger.info("Starting memory optimization test")
    
    config = {
        'use_minimal': args.minimal,
        'quick_test': args.quick
    }
    
    try:
        results = test_vsphere_resource_retrieval(config)
        print_results(results)
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
