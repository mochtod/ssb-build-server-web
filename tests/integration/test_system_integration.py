#!/usr/bin/env python3
"""
System Integration Test Module

This module provides comprehensive tests for integration points between different 
components of the SSB Build Server application, including:
- vSphere connectivity and resource retrieval
- Atlantis connectivity and API operations
- NetBox connectivity and IP allocation
- Container service health
- Terraform validation
- End-to-end workflow testing
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
from vsphere_utils import test_vsphere_connection
from atlantis_api import test_atlantis_connection, check_atlantis_health
from netbox_api import test_netbox_connection
from container_discovery import check_all_services_health, get_atlantis_url
from terraform_validator import validate_terraform_files

class TestEnvironment(unittest.TestCase):
    """Test environment and service connectivity."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        # Record start time
        cls.start_time = datetime.now()
        logger.info(f"Starting environment tests at {cls.start_time}")
        
        # Load environment variables from .env file if available
        cls.load_env()
        
        # Initialize test results
        cls.test_results = {
            'vsphere': {},
            'atlantis': {},
            'netbox': {},
            'container_health': {},
            'terraform': {}
        }
    
    @classmethod
    def load_env(cls):
        """Load environment variables from .env file."""
        env_file = os.environ.get('ENV_FILE', '.env')
        if not os.path.exists(env_file):
            logger.warning(f"Environment file {env_file} not found")
            return
        
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    if '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
            
            logger.info(f"Loaded environment variables from {env_file}")
        except Exception as e:
            logger.error(f"Error loading environment file: {str(e)}")
    
    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        # Record end time
        end_time = datetime.now()
        duration = (end_time - cls.start_time).total_seconds()
        logger.info(f"Completed environment tests in {duration:.2f} seconds")
        
        # Write test results to file
        try:
            results_file = os.environ.get('TEST_RESULTS_FILE', 'integration_test_results.json')
            with open(results_file, 'w') as f:
                json.dump({
                    'start_time': cls.start_time.isoformat(),
                    'end_time': end_time.isoformat(),
                    'duration_seconds': duration,
                    'results': cls.test_results
                }, f, indent=2)
            
            logger.info(f"Test results written to {results_file}")
        except Exception as e:
            logger.error(f"Error writing test results: {str(e)}")
    
    def test_001_vsphere_connection(self):
        """Test connection to vSphere."""
        logger.info("Testing vSphere connection...")
        
        # Get vSphere credentials from environment
        vsphere_server = os.environ.get('VSPHERE_SERVER', '')
        vsphere_user = os.environ.get('VSPHERE_USER', '')
        vsphere_password = os.environ.get('VSPHERE_PASSWORD', '')
        
        # Skip test if credentials are missing
        if not (vsphere_server and vsphere_user and vsphere_password):
            self.skipTest("vSphere credentials not configured")
        
        # Test connection
        result = test_vsphere_connection(
            server=vsphere_server,
            username=vsphere_user,
            password=vsphere_password
        )
        
        # Store result
        self.__class__.test_results['vsphere'] = result
        
        # Assert
        self.assertTrue(result.get('success'), f"vSphere connection failed: {result.get('message')}")
        self.assertIn('details', result, "vSphere connection details missing")
        
        # Log success
        logger.info(f"vSphere connection successful: {result.get('details', {}).get('version', 'unknown')} - " +
                   f"{len(result.get('details', {}).get('datacenters', []))} datacenters")
    
    def test_002_atlantis_connection(self):
        """Test connection to Atlantis."""
        logger.info("Testing Atlantis connection...")
        
        # Test connection
        result = test_atlantis_connection()
        
        # Store result
        self.__class__.test_results['atlantis'] = result
        
        # Assert
        self.assertTrue(result.get('success'), f"Atlantis connection failed: {result.get('message')}")
        
        # Log success
        logger.info(f"Atlantis connection successful at {result.get('details', {}).get('url', 'unknown')}")
    
    def test_003_netbox_connection(self):
        """Test connection to NetBox."""
        logger.info("Testing NetBox connection...")
        
        # Get NetBox URL from environment
        netbox_url = os.environ.get('NETBOX_URL', '')
        
        # Test connection
        result = test_netbox_connection()
        
        # Store result
        self.__class__.test_results['netbox'] = result
        
        # Assert if NetBox URL is configured
        if not netbox_url:
            logger.warning("NetBox URL not configured, skipping assertions")
        else:
            self.assertTrue(result.get('success'), f"NetBox connection failed: {result.get('message')}")
            
            # Log success
            if result.get('success'):
                logger.info(f"NetBox connection successful: {result.get('details', {}).get('version', 'unknown')}")
            else:
                logger.warning(f"NetBox connection failed: {result.get('message')}")
    
    def test_004_container_health(self):
        """Test health of container services."""
        logger.info("Testing container health...")
        
        # Check all services
        result = check_all_services_health()
        
        # Store result
        self.__class__.test_results['container_health'] = result
        
        # Assert web service health
        if 'web' in result:
            self.assertTrue(
                result['web'].get('healthy', False), 
                f"Web service unhealthy: {result['web'].get('error', 'Unknown error')}"
            )
        
        # Assert Atlantis service health if Atlantis URL is configured
        atlantis_url = get_atlantis_url()
        if atlantis_url and 'atlantis' in result:
            self.assertTrue(
                result['atlantis'].get('healthy', False),
                f"Atlantis service unhealthy: {result['atlantis'].get('error', 'Unknown error')}"
            )
        
        # Log results
        for service, health in result.items():
            if health.get('healthy', False):
                logger.info(f"Service {service} is healthy at {health.get('url', 'unknown')}")
            else:
                logger.warning(f"Service {service} is unhealthy: {health.get('error', 'Unknown error')}")


class TestTerraformIntegration(unittest.TestCase):
    """Test Terraform validation and integration."""
    
    def test_001_terraform_validation(self):
        """Test Terraform validation."""
        logger.info("Testing Terraform validation...")
        
        # Find test Terraform directory
        tf_dirs = ['test-tf', 'terraform-test', 'vm-workspace']
        tf_dir = None
        
        for dir_name in tf_dirs:
            if os.path.exists(dir_name) and os.path.isdir(dir_name):
                tf_dir = dir_name
                break
        
        if not tf_dir:
            self.skipTest("No test Terraform directory found")
        
        # Validate Terraform files
        is_valid = validate_terraform_files(tf_dir)
        
        # Assert
        self.assertTrue(is_valid, f"Terraform validation failed for directory {tf_dir}")
        
        # Log success
        logger.info(f"Terraform validation successful for directory {tf_dir}")
    
    def test_002_terraform_atlantis_integration(self):
        """Test Terraform and Atlantis integration."""
        logger.info("Testing Terraform and Atlantis integration...")
        
        # Check if Atlantis is healthy
        if not check_atlantis_health():
            self.skipTest("Atlantis is not healthy or not configured")
        
        # Find test Terraform directory
        tf_dirs = ['test-tf', 'terraform-test', 'vm-workspace']
        tf_dir = None
        
        for dir_name in tf_dirs:
            if os.path.exists(dir_name) and os.path.isdir(dir_name):
                tf_dir = dir_name
                break
        
        if not tf_dir:
            self.skipTest("No test Terraform directory found")
        
        # Test Terraform validation
        is_valid = validate_terraform_files(tf_dir)
        self.assertTrue(is_valid, "Terraform files validation failed")
        
        # For a complete test we would invoke Atlantis API here
        # This would require a full end-to-end test flow
        # For now, we'll just verify the prerequisites are met
        logger.info("Terraform and Atlantis integration prerequisites met")


class TestVSphereResources(unittest.TestCase):
    """Test VSphere resource retrieval."""
    
    def test_001_optimized_resources(self):
        """Test optimized VSphere resource retrieval."""
        logger.info("Testing optimized VSphere resource retrieval...")
        
        try:
            import vsphere_optimized_loader
            
            # Get resources
            start_time = time.time()
            resources = vsphere_optimized_loader.get_vsphere_resources(
                use_cache=True, 
                force_refresh=False
            )
            duration = time.time() - start_time
            
            # Validate resources
            self.assertIsNotNone(resources, "VSphere resources should not be None")
            self.assertIn('resource_pools', resources, "Resource pools should be included")
            self.assertIn('datastores', resources, "Datastores should be included")
            self.assertIn('networks', resources, "Networks should be included")
            self.assertIn('templates', resources, "Templates should be included")
            
            # Log results
            logger.info(f"Successfully retrieved VSphere resources in {duration:.2f} seconds:")
            logger.info(f"  Resource Pools: {len(resources.get('resource_pools', []))}")
            logger.info(f"  Datastores: {len(resources.get('datastores', []))}")
            logger.info(f"  Networks: {len(resources.get('networks', []))}")
            logger.info(f"  Templates: {len(resources.get('templates', []))}")
            
        except Exception as e:
            logger.error(f"Error testing VSphere resources: {str(e)}")
            self.fail(f"VSphere resource test failed: {str(e)}")
    
    def test_002_hierarchical_resources(self):
        """Test hierarchical VSphere resource retrieval."""
        logger.info("Testing hierarchical VSphere resource retrieval...")
        
        try:
            import vsphere_hierarchical_loader
            
            # Get loader
            loader = vsphere_hierarchical_loader.get_loader()
            
            # Get datacenters
            start_time = time.time()
            datacenters = loader.get_datacenters(force_load=False)
            dc_duration = time.time() - start_time
            
            self.assertTrue(len(datacenters) > 0, "Should retrieve at least one datacenter")
            logger.info(f"Retrieved {len(datacenters)} datacenters in {dc_duration:.2f} seconds")
            
            if not datacenters:
                self.skipTest("No datacenters found")
                return
            
            # Get clusters for first datacenter
            dc_name = datacenters[0]['name']
            start_time = time.time()
            clusters = loader.get_clusters(dc_name, force_load=False)
            cluster_duration = time.time() - start_time
            
            self.assertTrue(len(clusters) > 0, f"Should retrieve at least one cluster for datacenter {dc_name}")
            logger.info(f"Retrieved {len(clusters)} clusters for datacenter {dc_name} in {cluster_duration:.2f} seconds")
            
            if not clusters:
                self.skipTest("No clusters found")
                return
            
            # Get resources for first cluster
            cluster = clusters[0]
            start_time = time.time()
            resources = loader.get_resources(cluster['id'], cluster['name'], force_load=False)
            resource_duration = time.time() - start_time
            
            self.assertIsNotNone(resources, "Cluster resources should not be None")
            
            # Log results
            logger.info(f"Retrieved resources for cluster {cluster['name']} in {resource_duration:.2f} seconds:")
            logger.info(f"  Resource Pools: {len(resources.get('resource_pools', []))}")
            logger.info(f"  Datastores: {len(resources.get('datastores', []))}")
            logger.info(f"  Networks: {len(resources.get('networks', []))}")
            logger.info(f"  Templates: {len(resources.get('templates', []))}")
            
        except Exception as e:
            logger.error(f"Error testing hierarchical VSphere resources: {str(e)}")
            self.fail(f"Hierarchical VSphere resource test failed: {str(e)}")


class TestEndToEndWorkflow(unittest.TestCase):
    """Test end-to-end workflow."""
    
    @classmethod
    def setUpClass(cls):
        """Set up end-to-end test."""
        logger.info("Setting up end-to-end workflow test...")
        
        # Verify all required services are available
        cls.all_services_available = True
        cls.service_status = {}
        
        # Check vSphere
        vsphere_result = test_vsphere_connection()
        cls.service_status['vsphere'] = vsphere_result.get('success', False)
        if not cls.service_status['vsphere']:
            logger.warning("vSphere connection failed, end-to-end tests may be limited")
            cls.all_services_available = False
        
        # Check Atlantis
        atlantis_result = test_atlantis_connection()
        cls.service_status['atlantis'] = atlantis_result.get('success', False)
        if not cls.service_status['atlantis']:
            logger.warning("Atlantis connection failed, end-to-end tests may be limited")
            cls.all_services_available = False
        
        # Check NetBox if configured
        if os.environ.get('NETBOX_URL'):
            netbox_result = test_netbox_connection()
            cls.service_status['netbox'] = netbox_result.get('success', False)
            if not cls.service_status['netbox']:
                logger.warning("NetBox connection failed, end-to-end tests may be limited")
                cls.all_services_available = False
    
    def test_001_prerequisites_check(self):
        """Test that prerequisites for end-to-end workflow are met."""
        logger.info("Checking prerequisites for end-to-end workflow...")
        
        # Check if all services are available
        if not self.__class__.all_services_available:
            missing_services = [
                service for service, status in self.__class__.service_status.items() 
                if not status
            ]
            logger.warning(f"End-to-end workflow prerequisites not fully met: missing {', '.join(missing_services)}")
            self.skipTest(f"Missing required services: {', '.join(missing_services)}")
        
        # Log success
        logger.info("All prerequisites for end-to-end workflow are met")
    
    def test_002_basic_workflow(self):
        """Test basic end-to-end workflow."""
        logger.info("Testing basic end-to-end workflow...")
        
        # Check if all services are available
        if not self.__class__.all_services_available:
            self.skipTest("Missing required services for end-to-end test")
        
        # Basic workflow:
        # 1. Verify vSphere resources are available
        # 2. Verify Terraform files can be validated
        # 3. Verify Atlantis is available
        
        # 1. Check vSphere resources
        try:
            import vsphere_optimized_loader
            resources = vsphere_optimized_loader.get_vsphere_resources(use_cache=True)
            
            self.assertTrue(len(resources.get('resource_pools', [])) > 0, "No resource pools available")
            self.assertTrue(len(resources.get('datastores', [])) > 0, "No datastores available")
            self.assertTrue(len(resources.get('networks', [])) > 0, "No networks available")
            
            logger.info("vSphere resources verified")
        except Exception as e:
            logger.error(f"Error verifying vSphere resources: {str(e)}")
            self.fail(f"vSphere resource verification failed: {str(e)}")
        
        # 2. Check Terraform validation
        tf_dirs = ['test-tf', 'terraform-test', 'vm-workspace']
        tf_dir = None
        
        for dir_name in tf_dirs:
            if os.path.exists(dir_name) and os.path.isdir(dir_name):
                tf_dir = dir_name
                break
        
        if not tf_dir:
            self.skipTest("No test Terraform directory found")
        
        is_valid = validate_terraform_files(tf_dir)
        self.assertTrue(is_valid, f"Terraform validation failed for directory {tf_dir}")
        logger.info("Terraform validation verified")
        
        # 3. Check Atlantis health
        self.assertTrue(check_atlantis_health(), "Atlantis should be healthy")
        logger.info("Atlantis health verified")
        
        # Log success
        logger.info("Basic end-to-end workflow verified successfully")


def main():
    """Main entry point for integration tests."""
    # Parse arguments
    import argparse
    parser = argparse.ArgumentParser(description='Run integration tests')
    parser.add_argument('--test', choices=['all', 'environment', 'terraform', 'vsphere', 'workflow'],
                        default='all', help='Which tests to run')
    parser.add_argument('--env-file', help='Path to .env file')
    args = parser.parse_args()
    
    # Set environment file if provided
    if args.env_file:
        os.environ['ENV_FILE'] = args.env_file
    
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add test cases based on argument
    if args.test in ['all', 'environment']:
        suite.addTest(unittest.makeSuite(TestEnvironment))
    
    if args.test in ['all', 'terraform']:
        suite.addTest(unittest.makeSuite(TestTerraformIntegration))
    
    if args.test in ['all', 'vsphere']:
        suite.addTest(unittest.makeSuite(TestVSphereResources))
    
    if args.test in ['all', 'workflow']:
        suite.addTest(unittest.makeSuite(TestEndToEndWorkflow))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return appropriate exit code
    sys.exit(0 if result.wasSuccessful() else 1)

if __name__ == '__main__':
    main()
