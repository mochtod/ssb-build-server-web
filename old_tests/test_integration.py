#!/usr/bin/env python3
"""
Integration Test Module

This module provides tests for integration points between different components
of the SSB Build Server application, including vSphere, Atlantis, and NetBox
connectivity.
"""
import os
import unittest
import json
import logging
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import application modules
from vsphere_utils import test_vsphere_connection
from atlantis_api import test_atlantis_connection
from netbox_api import test_netbox_connection
from container_discovery import check_all_services_health, get_atlantis_url
from terraform_validator import validate_terraform_files

class IntegrationTest(unittest.TestCase):
    """Test integration points between different components."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        # Record start time
        cls.start_time = datetime.now()
        logger.info(f"Starting integration tests at {cls.start_time}")
        
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
        logger.info(f"Completed integration tests in {duration:.2f} seconds")
        
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
        logger.info(f"vSphere connection successful: {result.get('details', {}).get('version', 'unknown')} - {len(result.get('details', {}).get('datacenters', []))} datacenters")
    
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
        
        # Test connection
        result = test_netbox_connection()
        
        # Store result
        self.__class__.test_results['netbox'] = result
        
        # Assert if NetBox URL is configured
        netbox_url = os.environ.get('NETBOX_URL', '')
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
    
    def test_005_terraform_validation(self):
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
        result = {
            'directory': tf_dir,
            'valid': validate_terraform_files(tf_dir)
        }
        
        # Store result
        self.__class__.test_results['terraform'] = result
        
        # Assert
        self.assertTrue(result['valid'], f"Terraform validation failed for directory {tf_dir}")
        
        # Log success
        logger.info(f"Terraform validation successful for directory {tf_dir}")
    
    def test_006_end_to_end_integration(self):
        """Test end-to-end integration."""
        logger.info("Testing end-to-end integration...")
        
        # Check if previous tests passed
        vsphere_ok = self.__class__.test_results.get('vsphere', {}).get('success', False)
        atlantis_ok = self.__class__.test_results.get('atlantis', {}).get('success', False)
        terraform_ok = self.__class__.test_results.get('terraform', {}).get('valid', False)
        
        # Skip if any of the required components is not working
        if not (vsphere_ok and atlantis_ok and terraform_ok):
            self.skipTest("Required components not working: " + 
                         ('' if vsphere_ok else 'vSphere ') +
                         ('' if atlantis_ok else 'Atlantis ') +
                         ('' if terraform_ok else 'Terraform'))
        
        # Log success of integration test
        logger.info("All required components are working, end-to-end integration is possible")
        
        # This is just a check that the prerequisites are met
        # The actual end-to-end test would be more complex and is out of scope for this test
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()
