#!/usr/bin/env python3
"""
Compare performance between original vSphere resource retrieval and optimized minimal approach.

This script measures and compares the performance of:
1. Original get_vsphere_resources.py script
2. New vsphere_minimal_resources.py script
3. Cached resource retrieval 

Usage:
    python compare_vsphere_performance.py [--trials TRIALS]
"""
import os
import sys
import time
import json
import argparse
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import utility modules
try:
    from vsphere_location_utils import get_vm_location_resources, verify_vm_location_resources
    UTILS_AVAILABLE = True
except ImportError:
    UTILS_AVAILABLE = False
    logger.warning("vsphere_location_utils.py not found, some tests will be skipped.")

def get_args():
    """Get command line arguments"""
    parser = argparse.ArgumentParser(description='Compare vSphere resource retrieval performance')
    parser.add_argument('--trials', type=int, default=3, help='Number of trials for each test')
    parser.add_argument('--no-clear-cache', action='store_true', help='Do not clear cache between trials')
    args = parser.parse_args()
    return args

def run_original_script() -> Tuple[float, Dict]:
    """Run the original vSphere resource script and measure performance"""
    logger.info("Running original get_vsphere_resources.py...")
    start_time = time.time()
    
    # Run the script using subprocess
    result = subprocess.run(
        [sys.executable, 'get_vsphere_resources.py'],
        capture_output=True,
        text=True
    )
    
    duration = time.time() - start_time
    
    # Check for errors
    if result.returncode != 0:
        logger.error(f"Error running get_vsphere_resources.py: {result.stderr}")
        return duration, None
    
    # Load the output file
    try:
        with open('vsphere_resources.json', 'r') as f:
            data = json.load(f)
            resources_count = sum(len(data.get(k, [])) for k in data.keys())
            logger.info(f"Retrieved {resources_count} total resources in {duration:.2f} seconds")
            return duration, data
    except Exception as e:
        logger.error(f"Error reading vsphere_resources.json: {str(e)}")
        return duration, None

def run_minimal_script() -> Tuple[float, Dict]:
    """Run the minimal vSphere resource script and measure performance"""
    logger.info("Running optimized vsphere_minimal_resources.py...")
    start_time = time.time()
    
    # Run the script using subprocess
    result = subprocess.run(
        [sys.executable, 'vsphere_minimal_resources.py'],
        capture_output=True,
        text=True
    )
    
    duration = time.time() - start_time
    
    # Check for errors
    if result.returncode != 0:
        logger.error(f"Error running vsphere_minimal_resources.py: {result.stderr}")
        return duration, None
    
    # Load the output file
    try:
        with open('vsphere_minimal_resources.json', 'r') as f:
            data = json.load(f)
            resources_count = sum(len(data.get(k, [])) for k in data.keys())
            logger.info(f"Retrieved {resources_count} total resources in {duration:.2f} seconds")
            return duration, data
    except Exception as e:
        logger.error(f"Error reading vsphere_minimal_resources.json: {str(e)}")
        return duration, None

def run_minimal_script_with_cache() -> Tuple[float, Dict]:
    """Run the minimal vSphere resource script with cache and measure performance"""
    logger.info("Running optimized script with cache...")
    start_time = time.time()
    
    # Run the script using subprocess
    result = subprocess.run(
        [sys.executable, 'vsphere_minimal_resources.py'],
        capture_output=True,
        text=True
    )
    
    duration = time.time() - start_time
    
    # Check for errors
    if result.returncode != 0:
        logger.error(f"Error running vsphere_minimal_resources.py with cache: {result.stderr}")
        return duration, None
    
    # Load the output file
    try:
        with open('vsphere_minimal_resources.json', 'r') as f:
            data = json.load(f)
            resources_count = sum(len(data.get(k, [])) for k in data.keys())
            logger.info(f"Retrieved {resources_count} total resources from cache in {duration:.2f} seconds")
            return duration, data
    except Exception as e:
        logger.error(f"Error reading vsphere_minimal_resources.json: {str(e)}")
        return duration, None

def run_location_utils() -> Tuple[float, Dict]:
    """Run the location utils and measure performance"""
    if not UTILS_AVAILABLE:
        logger.warning("Skipping location utils test (module not available)")
        return 0, None
    
    logger.info("Running vsphere_location_utils...")
    start_time = time.time()
    
    # Get VM location resources
    resources = get_vm_location_resources()
    valid, message = verify_vm_location_resources(resources)
    
    duration = time.time() - start_time
    
    if valid:
        logger.info(f"Retrieved and validated VM location resources in {duration:.2f} seconds")
        return duration, resources
    else:
        logger.warning(f"VM location resources validation failed: {message}")
        return duration, resources

def clear_cache():
    """Clear the vSphere cache"""
    logger.info("Clearing vSphere cache...")
    
    # Try to clear cache using vsphere_cache.py
    try:
        result = subprocess.run(
            [sys.executable, 'vsphere_cache.py', '--clear'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info("Cache cleared successfully")
        else:
            logger.warning(f"Error clearing cache: {result.stderr}")
            
            # Fallback to removing cache files directly
            for file_path in ['vsphere_resources.json', 'vsphere_minimal_resources.json']:
                if Path(file_path).exists():
                    os.rename(file_path, f"{file_path}.bak")
                    logger.info(f"Renamed {file_path} to {file_path}.bak")
                    
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")

def print_file_size_comparison():
    """Print file size comparison between the original and minimal resource files"""
    print("\n=== File Size Comparison ===\n")
    
    original_size = Path('vsphere_resources.json').stat().st_size if Path('vsphere_resources.json').exists() else 0
    minimal_size = Path('vsphere_minimal_resources.json').stat().st_size if Path('vsphere_minimal_resources.json').exists() else 0
    
    original_kb = original_size / 1024
    minimal_kb = minimal_size / 1024
    
    print(f"Original resource file:  {original_kb:.2f} KB")
    print(f"Minimal resource file:   {minimal_kb:.2f} KB")
    
    if original_size > 0 and minimal_size > 0:
        size_reduction = (original_size - minimal_size) / original_size * 100
        print(f"Size reduction:          {size_reduction:.2f}%")

def print_summary(results):
    """Print performance summary"""
    print("\n=== Performance Summary ===\n")
    print("Method                       | Avg Time (s) | Improvement")
    print("-----------------------------+-------------+------------")
    
    baseline = results.get('original', {}).get('avg_time', 0)
    if baseline > 0:
        for method, data in results.items():
            avg_time = data.get('avg_time', 0)
            if avg_time > 0:
                improvement = (baseline - avg_time) / baseline * 100 if method != 'original' else 0
                print(f"{method.ljust(28)} | {avg_time:11.2f} | {improvement:10.2f}%")
    else:
        for method, data in results.items():
            avg_time = data.get('avg_time', 0)
            print(f"{method.ljust(28)} | {avg_time:11.2f} | N/A")

def main():
    args = get_args()
    
    # Ensure required scripts are available
    if not Path('get_vsphere_resources.py').exists():
        logger.error("Original script get_vsphere_resources.py not found")
        return
    
    if not Path('vsphere_minimal_resources.py').exists():
        logger.error("Minimal script vsphere_minimal_resources.py not found")
        return
    
    # Track results
    results = {
        'original': {'times': [], 'avg_time': 0},
        'minimal': {'times': [], 'avg_time': 0},
        'minimal_cached': {'times': [], 'avg_time': 0},
        'location_utils': {'times': [], 'avg_time': 0}
    }
    
    # Run trials
    for trial in range(1, args.trials + 1):
        print(f"\n=== Trial {trial}/{args.trials} ===\n")
        
        # Clear cache before tests if specified
        if not args.no_clear_cache:
            clear_cache()
        
        # Run original script
        duration, _ = run_original_script()
        results['original']['times'].append(duration)
        
        # Run minimal script
        duration, _ = run_minimal_script()
        results['minimal']['times'].append(duration)
        
        # Run minimal script with cache (should be faster)
        duration, _ = run_minimal_script_with_cache()
        results['minimal_cached']['times'].append(duration)
        
        # Run location utils
        duration, _ = run_location_utils()
        results['location_utils']['times'].append(duration)
    
    # Calculate averages
    for method in results:
        times = results[method]['times']
        if times:
            results[method]['avg_time'] = sum(times) / len(times)
    
    # Print file size comparison
    print_file_size_comparison()
    
    # Print summary
    print_summary(results)
    
    print("\nPerformance testing completed!")

if __name__ == "__main__":
    main()
