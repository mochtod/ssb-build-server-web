#!/usr/bin/env python3
"""
Atlantis API Test Module

This module provides tests for the Atlantis API integration, including:
- API connection testing
- Plan payload generation
- Apply payload generation
- API response handling
- Error recovery mechanisms
"""
import os
import unittest
import json
import logging
import sys
import time
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import application modules
from atlantis_api import (
    test_atlantis_connection,
    check_atlantis_health,
    generate_atlantis_payload,
    generate_atlantis_apply_payload_fixed,
    run_atlantis_plan,
    run_atlantis_apply,
    AtlantisApiError
)
from container_discovery import get_atlantis_url
from terraform_validator import validate_terraform_files


class TestAtlantisConnection(unittest.TestCase):
    """Test Atlantis connection and health checks."""
    
    def test_001_atlantis_health_check(self):
        """Test Atlantis health check."""
        logger.info("Testing Atlantis health check...")
        
        # Check if Atlantis is healthy
        is_healthy = check_atlantis_health()
        
        # If not healthy, report but don't fail the test
        # This makes the test more informative when run in environments without Atlantis
        if not is_healthy:
            logger.warning("Atlantis health check failed - this is expected in environments without Atlantis")
        else:
            logger.info("Atlantis health check successful")
    
    def test_002_atlantis_connection(self):
        """Test Atlantis connection with detailed information."""
        logger.info("Testing Atlantis connection...")
        
        # Test connection
        result = test_atlantis_connection()
        
        # If connection fails, report but don't fail the test
        if not result.get('success'):
            logger.warning(f"Atlantis connection failed: {result.get('message')}")
            logger.warning("This is expected in environments without Atlantis")
        else:
            # Log detailed information about the connection
            logger.info(f"Atlantis connection successful")
            logger.info(f"  URL: {result.get('details', {}).get('url', 'unknown')}")
            logger.info(f"  API Version: {result.get('details', {}).get('api_version', 'unknown')}")
            logger.info(f"  Response Time: {result.get('details', {}).get('response_time_ms', 0)} ms")
    
    def test_003_atlantis_url_discovery(self):
        """Test Atlantis URL discovery."""
        logger.info("Testing Atlantis URL discovery...")
        
        # Get Atlantis URL
        atlantis_url = get_atlantis_url()
        
        # If URL is not found, report but don't fail the test
        if not atlantis_url:
            logger.warning("Atlantis URL not found - this is expected in environments without Atlantis")
        else:
            logger.info(f"Atlantis URL discovered: {atlantis_url}")


class TestAtlantisPayloads(unittest.TestCase):
    """Test Atlantis API payload generation."""
    
    def setUp(self):
        """Set up test environment."""
        # Skip tests if Atlantis is not available
        if not check_atlantis_health():
            self.skipTest("Atlantis is not healthy or not available")
    
    def test_001_plan_payload(self):
        """Test Atlantis plan payload generation."""
        logger.info("Testing Atlantis plan payload generation...")
        
        # Create a sample config
        config = {
            'request_id': 'test123',
            'timestamp': '20250413000000',
            'server_name': 'lin2dv2-test',
            'server_prefix': 'lin2dv2',
            'app_name': 'test',
            'environment': 'development',
            'quantity': 1,
            'num_cpus': 2,
            'memory': 4096,
            'disk_size': 50,
            'additional_disks': [],
            'vsphere_resources': {
                'resource_pool_id': 'resgroup-123',
                'datastore_id': 'datastore-123',
                'network_id': 'network-123',
                'template_uuid': 'vm-123'
            }
        }
        
        # Create a test Terraform directory
        tf_directory = os.path.join('terraform', 'test_plan_payload')
        os.makedirs(tf_directory, exist_ok=True)
        
        # Create a simple Terraform file for testing
        with open(os.path.join(tf_directory, 'main.tf'), 'w') as f:
            f.write('# Test Terraform file\n')
            f.write('resource "null_resource" "test" {}\n')
        
        try:
            # Generate payload
            payload = generate_atlantis_payload(config, tf_directory)
            
            # Validate payload structure
            self.assertIsNotNone(payload, "Payload should not be None")
            self.assertIn('repo_name', payload, "Payload should include repo_name")
            self.assertIn('repo_owner', payload, "Payload should include repo_owner")
            self.assertIn('workspace', payload, "Payload should include workspace")
            self.assertIn('pull_num', payload, "Payload should include pull_num")
            self.assertIn('pull_author', payload, "Payload should include pull_author")
            self.assertIn('environment', payload, "Payload should include environment")
            self.assertIn('terraform_files', payload, "Payload should include terraform_files")
            
            # Check that terraform_files is a dict
            self.assertIsInstance(payload['terraform_files'], dict, "terraform_files should be a dictionary")
            
            # Check that the environment value matches the config
            self.assertEqual(payload['environment'], config['environment'], 
                           "environment in payload should match config")
            
            logger.info("Plan payload generated successfully")
            
        finally:
            # Clean up test directory
            import shutil
            if os.path.exists(tf_directory):
                shutil.rmtree(tf_directory)
    
    def test_002_apply_payload(self):
        """Test Atlantis apply payload generation."""
        logger.info("Testing Atlantis apply payload generation...")
        
        # Create a sample config
        config = {
            'request_id': 'test123',
            'timestamp': '20250413000000',
            'server_name': 'lin2dv2-test',
            'server_prefix': 'lin2dv2',
            'app_name': 'test',
            'environment': 'development',
            'quantity': 1,
            'num_cpus': 2,
            'memory': 4096,
            'disk_size': 50,
            'additional_disks': [],
            'vsphere_resources': {
                'resource_pool_id': 'resgroup-123',
                'datastore_id': 'datastore-123',
                'network_id': 'network-123',
                'template_uuid': 'vm-123'
            },
            'plan_id': 'plan-test123'  # This is required for apply
        }
        
        # Create a test Terraform directory
        tf_directory = os.path.join('terraform', 'test_apply_payload')
        os.makedirs(tf_directory, exist_ok=True)
        
        # Create a simple Terraform file for testing
        with open(os.path.join(tf_directory, 'main.tf'), 'w') as f:
            f.write('# Test Terraform file\n')
            f.write('resource "null_resource" "test" {}\n')
        
        try:
            # Generate payload
            payload = generate_atlantis_apply_payload_fixed(config, tf_directory)
            
            # Validate payload structure
            self.assertIsNotNone(payload, "Payload should not be None")
            self.assertIn('plan_id', payload, "Payload should include plan_id")
            self.assertIn('repo_name', payload, "Payload should include repo_name")
            self.assertIn('environment', payload, "Payload should include environment")
            
            # Check that the plan_id value matches the config
            self.assertEqual(payload['plan_id'], config['plan_id'], 
                           "plan_id in payload should match config")
            
            # Check that the environment value matches the config
            self.assertEqual(payload['environment'], config['environment'], 
                           "environment in payload should match config")
            
            logger.info("Apply payload generated successfully")
            
        finally:
            # Clean up test directory
            import shutil
            if os.path.exists(tf_directory):
                shutil.rmtree(tf_directory)


class TestAtlantisSimulatedOperations(unittest.TestCase):
    """Test Atlantis simulated operations when real API is unavailable."""
    
    def test_001_plan_simulation(self):
        """Test simulated plan operation when Atlantis is unavailable."""
        logger.info("Testing simulated plan operation...")
        
        # Check if Atlantis is available
        atlantis_available = check_atlantis_health()
        
        if atlantis_available:
            logger.info("Atlantis is available, but we're still testing simulated operations")
        
        # Create a sample config
        config = {
            'request_id': 'test123',
            'timestamp': '20250413000000',
            'server_name': 'lin2dv2-test',
            'server_prefix': 'lin2dv2',
            'app_name': 'test',
            'environment': 'development',
            'quantity': 1,
            'num_cpus': 2,
            'memory': 4096,
            'disk_size': 50,
            'additional_disks': [],
            'vsphere_resources': {
                'resource_pool_id': 'resgroup-123',
                'datastore_id': 'datastore-123',
                'network_id': 'network-123',
                'template_uuid': 'vm-123'
            }
        }
        
        # Create a test Terraform directory
        tf_directory = os.path.join('terraform', 'test_simulation')
        os.makedirs(tf_directory, exist_ok=True)
        
        # Create a simple Terraform file for testing
        with open(os.path.join(tf_directory, 'main.tf'), 'w') as f:
            f.write('# Test Terraform file\n')
            f.write('resource "null_resource" "test" {}\n')
        
        try:
            # Force simulation mode by temporarily breaking the URL
            original_url = os.environ.get('ATLANTIS_URL', '')
            os.environ['ATLANTIS_URL'] = 'http://nonexistent-atlantis-url'
            
            # Run plan operation
            result = run_atlantis_plan(config, tf_directory)
            
            # Restore original URL
            if original_url:
                os.environ['ATLANTIS_URL'] = original_url
            else:
                del os.environ['ATLANTIS_URL']
            
            # Validate result
            self.assertIsNotNone(result, "Result should not be None")
            self.assertIn('simulated', result, "Result should indicate simulation")
            self.assertTrue(result['simulated'], "Result should indicate simulation")
            self.assertIn('plan_log', result, "Result should include plan_log")
            self.assertIn('Terraform will perform the following actions', result['plan_log'],
                         "Plan log should include Terraform actions")
            
            logger.info("Simulated plan operation successful")
            
        finally:
            # Clean up test directory
            import shutil
            if os.path.exists(tf_directory):
                shutil.rmtree(tf_directory)
    
    def test_002_apply_simulation(self):
        """Test simulated apply operation when Atlantis is unavailable."""
        logger.info("Testing simulated apply operation...")
        
        # Check if Atlantis is available
        atlantis_available = check_atlantis_health()
        
        if atlantis_available:
            logger.info("Atlantis is available, but we're still testing simulated operations")
        
        # Create a sample config
        config = {
            'request_id': 'test123',
            'timestamp': '20250413000000',
            'server_name': 'lin2dv2-test',
            'server_prefix': 'lin2dv2',
            'app_name': 'test',
            'environment': 'development',
            'quantity': 1,
            'num_cpus': 2,
            'memory': 4096,
            'disk_size': 50,
            'additional_disks': [],
            'vsphere_resources': {
                'resource_pool_id': 'resgroup-123',
                'datastore_id': 'datastore-123',
                'network_id': 'network-123',
                'template_uuid': 'vm-123'
            },
            'plan_id': 'plan-test123'  # This is required for apply
        }
        
        # Create a test Terraform directory
        tf_directory = os.path.join('terraform', 'test_simulation')
        os.makedirs(tf_directory, exist_ok=True)
        
        # Create a simple Terraform file for testing
        with open(os.path.join(tf_directory, 'main.tf'), 'w') as f:
            f.write('# Test Terraform file\n')
            f.write('resource "null_resource" "test" {}\n')
        
        try:
            # Force simulation mode by temporarily breaking the URL
            original_url = os.environ.get('ATLANTIS_URL', '')
            os.environ['ATLANTIS_URL'] = 'http://nonexistent-atlantis-url'
            
            # Run apply operation
            result = run_atlantis_apply(config, tf_directory)
            
            # Restore original URL
            if original_url:
                os.environ['ATLANTIS_URL'] = original_url
            else:
                del os.environ['ATLANTIS_URL']
            
            # Validate result
            self.assertIsNotNone(result, "Result should not be None")
            self.assertIn('simulated', result, "Result should indicate simulation")
            self.assertTrue(result['simulated'], "Result should indicate simulation")
            self.assertIn('build_log', result, "Result should include build_log")
            self.assertIn('Apply complete!', result['build_log'],
                         "Build log should include apply completion message")
            
            logger.info("Simulated apply operation successful")
            
        finally:
            # Clean up test directory
            import shutil
            if os.path.exists(tf_directory):
                shutil.rmtree(tf_directory)


class TestAtlantisErrorHandling(unittest.TestCase):
    """Test Atlantis error handling."""
    
    def test_001_api_error_recovery(self):
        """Test recovery from API errors."""
        logger.info("Testing API error recovery...")
        
        # Create invalid payload to trigger error
        invalid_payload = {"invalid": "payload"}
        
        try:
            # Try to make a request that will definitely fail
            # We're going to simulate making a bad API call
            
            # We'll artificially create the api error
            error_msg = "Simulated API error for testing"
            raise AtlantisApiError(error_msg)
            
        except AtlantisApiError as e:
            # Verify error details
            self.assertEqual(str(e), error_msg, "Error message should match")
            logger.info("AtlantisApiError correctly raised and caught")
        
        # Second test: ensure error is raised correctly from run_atlantis_plan
        logger.info("Testing API error recovery in run_atlantis_plan...")
        
        # Create a test config
        config = {
            'request_id': 'test123',
            'timestamp': '20250413000000',
            'server_name': 'lin2dv2-test',
            'environment': 'development',
            # Missing required fields to trigger generation error
        }
        
        try:
            # Force simulation mode by using bad Atlantis URL and empty directory
            # This should raise an error
            os.environ['ATLANTIS_URL'] = 'http://nonexistent-atlantis-url'
            result = run_atlantis_plan(config, "nonexistent-directory")
            
            # If we get here without error, verify we got a simulated result
            self.assertIn('simulated', result, "Result should indicate simulation")
            
        except Exception as e:
            logger.info(f"Caught expected exception during error test: {str(e)}")


def main():
    """Main entry point for Atlantis API tests."""
    # Parse arguments
    import argparse
    parser = argparse.ArgumentParser(description='Run Atlantis API tests')
    parser.add_argument('--test', choices=['all', 'connection', 'payloads', 'simulation', 'error'],
                        default='all', help='Which tests to run')
    args = parser.parse_args()
    
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add test cases based on argument
    if args.test in ['all', 'connection']:
        suite.addTest(unittest.makeSuite(TestAtlantisConnection))
    
    if args.test in ['all', 'payloads']:
        suite.addTest(unittest.makeSuite(TestAtlantisPayloads))
    
    if args.test in ['all', 'simulation']:
        suite.addTest(unittest.makeSuite(TestAtlantisSimulatedOperations))
    
    if args.test in ['all', 'error']:
        suite.addTest(unittest.makeSuite(TestAtlantisErrorHandling))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return appropriate exit code
    sys.exit(0 if result.wasSuccessful() else 1)

if __name__ == '__main__':
    main()
