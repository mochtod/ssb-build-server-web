#!/usr/bin/env python3
"""
Test Runner

This script provides a unified interface for running all or selected tests
from the organized test structure.
"""
import os
import sys
import unittest
import argparse
import logging
import importlib
import time
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def discover_and_run_tests(test_type=None, verbosity=2):
    """Discover and run tests based on the specified type."""
    start_time = time.time()
    logger.info(f"Starting test discovery for type: {test_type or 'all'}")
    
    # Get the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Determine test directory based on test type
    if test_type and test_type != 'all':
        test_dir = os.path.join(script_dir, test_type)
        if not os.path.isdir(test_dir):
            logger.error(f"Test directory not found: {test_dir}")
            return False
        pattern = f"test_*.py"
    else:
        test_dir = script_dir
        pattern = "test_*.py"
    
    # Discover tests
    loader = unittest.defaultTestLoader
    try:
        if test_type and test_type != 'all':
            # For specific test types, discover tests in their directory
            test_suite = loader.discover(test_dir, pattern=pattern)
        else:
            # For 'all', create a suite with tests from each subdirectory
            test_suite = unittest.TestSuite()
            
            # Get all subdirectories that might contain tests
            for subdir in ['unit', 'integration', 'performance', 'atlantis', 'payload']:
                subdir_path = os.path.join(script_dir, subdir)
                if os.path.isdir(subdir_path):
                    sub_suite = loader.discover(subdir_path, pattern=pattern)
                    test_suite.addTest(sub_suite)
        
        # Count tests
        test_count = test_suite.countTestCases()
        logger.info(f"Discovered {test_count} tests")
        
        if test_count == 0:
            logger.warning(f"No tests found for type: {test_type or 'all'}")
            return True  # Return success but with warning
        
        # Run tests
        runner = unittest.TextTestRunner(verbosity=verbosity)
        result = runner.run(test_suite)
        
        # Calculate and log results
        duration = time.time() - start_time
        success_count = test_count - len(result.errors) - len(result.failures)
        logger.info(f"Test Results: {success_count}/{test_count} passed ({duration:.2f} seconds)")
        
        if result.wasSuccessful():
            logger.info("All tests passed successfully")
            return True
        else:
            logger.error(f"Some tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
            return False
            
    except Exception as e:
        logger.error(f"Error running tests: {str(e)}")
        return False

def run_specific_test(test_path, verbosity=2):
    """Run a specific test file."""
    start_time = time.time()
    logger.info(f"Running specific test: {test_path}")
    
    try:
        # Check if the file exists
        if not os.path.isfile(test_path):
            logger.error(f"Test file not found: {test_path}")
            return False
        
        # Get directory and module name
        directory = os.path.dirname(test_path)
        module_name = os.path.basename(test_path)
        if module_name.endswith('.py'):
            module_name = module_name[:-3]  # Remove .py extension
        
        # Add directory to path if not already there
        if directory and directory not in sys.path:
            sys.path.insert(0, directory)
        
        # Load the module
        module = importlib.import_module(module_name)
        
        # Find and run tests
        loader = unittest.defaultTestLoader
        test_suite = loader.loadTestsFromModule(module)
        
        # Count tests
        test_count = test_suite.countTestCases()
        logger.info(f"Found {test_count} tests in {test_path}")
        
        if test_count == 0:
            logger.warning(f"No tests found in: {test_path}")
            return True  # Return success but with warning
        
        # Run tests
        runner = unittest.TextTestRunner(verbosity=verbosity)
        result = runner.run(test_suite)
        
        # Calculate and log results
        duration = time.time() - start_time
        success_count = test_count - len(result.errors) - len(result.failures)
        logger.info(f"Test Results: {success_count}/{test_count} passed ({duration:.2f} seconds)")
        
        if result.wasSuccessful():
            logger.info("All tests passed successfully")
            return True
        else:
            logger.error(f"Some tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
            return False
            
    except Exception as e:
        logger.error(f"Error running test: {str(e)}")
        return False

def clean_backups():
    """Clean up backup files from the project."""
    extensions = ['.bak', '.original', '.new', '.fixed']
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    count = 0
    for root, dirs, files in os.walk(script_dir):
        for file in files:
            for ext in extensions:
                if file.endswith(ext):
                    try:
                        path = os.path.join(root, file)
                        os.remove(path)
                        logger.info(f"Removed backup file: {path}")
                        count += 1
                        break
                    except Exception as e:
                        logger.error(f"Error removing {file}: {str(e)}")
    
    logger.info(f"Cleaned up {count} backup files")
    return count

def main():
    """Main entry point for test runner."""
    parser = argparse.ArgumentParser(description='Run tests for the SSB Build Server')
    
    # Test selection arguments
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--all', action='store_true', help='Run all tests')
    group.add_argument('--unit', action='store_true', help='Run unit tests')
    group.add_argument('--integration', action='store_true', help='Run integration tests')
    group.add_argument('--performance', action='store_true', help='Run performance tests')
    group.add_argument('--atlantis', action='store_true', help='Run Atlantis API tests')
    group.add_argument('--payload', action='store_true', help='Run payload tests')
    group.add_argument('--file', help='Run a specific test file')
    
    # Additional options
    parser.add_argument('--clean', action='store_true', help='Clean up backup files')
    parser.add_argument('-v', '--verbose', action='store_true', help='Increase output verbosity')
    
    args = parser.parse_args()
    
    # Set verbosity level
    verbosity = 2
    if args.verbose:
        verbosity = 3
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Clean up backup files if requested
    if args.clean:
        clean_backups()
        if not (args.all or args.unit or args.integration or 
                args.performance or args.atlantis or args.payload or args.file):
            return 0  # Exit if only cleaning was requested
    
    # Determine which tests to run
    success = True
    
    if args.file:
        # Run a specific test file
        success = run_specific_test(args.file, verbosity)
    elif args.unit:
        success = discover_and_run_tests('unit', verbosity)
    elif args.integration:
        success = discover_and_run_tests('integration', verbosity)
    elif args.performance:
        success = discover_and_run_tests('performance', verbosity)
    elif args.atlantis:
        success = discover_and_run_tests('atlantis', verbosity)
    elif args.payload:
        success = discover_and_run_tests('payload', verbosity)
    else:
        # Default: run all tests
        success = discover_and_run_tests(None, verbosity)
    
    # Return appropriate exit code
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
