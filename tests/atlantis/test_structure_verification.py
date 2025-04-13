#!/usr/bin/env python3
"""
Test Terraform Structure Verification

This test suite verifies that the structure verification functionality
correctly identifies and fixes missing configuration files in Terraform directories.
"""

import os
import sys
import unittest
import tempfile
import shutil
from unittest import mock

# Add the parent directory to sys.path to allow importing the target module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Import the module to test
from terraform.ensure_config_structure import (
    copy_template_if_missing,
    ensure_config_structure,
    process_directory
)

class TestTerraformStructureVerification(unittest.TestCase):
    """Test cases for Terraform structure verification."""

    def setUp(self):
        """Set up a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a temporary templates directory
        self.templates_dir = os.path.join(self.temp_dir, 'terraform', 'templates')
        os.makedirs(self.templates_dir, exist_ok=True)
        
        # Create test template files
        with open(os.path.join(self.templates_dir, 'providers.tf.template'), 'w') as f:
            f.write('# Test providers template')
        
        with open(os.path.join(self.templates_dir, 'variables.tf.template'), 'w') as f:
            f.write('# Test variables template')

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_copy_template_if_missing(self):
        """Test copying a template when the target file is missing."""
        # Create a test directory
        test_dir = os.path.join(self.temp_dir, 'test_dir')
        os.makedirs(test_dir, exist_ok=True)
        
        # Mock the templates directory path
        with mock.patch('os.path.dirname') as mock_dirname:
            mock_dirname.return_value = self.temp_dir
            
            # Test copying a template that exists
            result = copy_template_if_missing(test_dir, 'providers.tf.template', 'providers.tf')
            self.assertTrue(result)
            self.assertTrue(os.path.exists(os.path.join(test_dir, 'providers.tf')))
            
            # Test copying a template that doesn't exist
            result = copy_template_if_missing(test_dir, 'nonexistent.tf.template', 'nonexistent.tf')
            self.assertFalse(result)
            self.assertFalse(os.path.exists(os.path.join(test_dir, 'nonexistent.tf')))
            
            # Test copying a template when the target already exists
            result = copy_template_if_missing(test_dir, 'providers.tf.template', 'providers.tf')
            self.assertFalse(result)  # Should return False as file already exists

    def test_ensure_config_structure(self):
        """Test ensuring the proper Terraform configuration structure."""
        # Create a test Terraform directory
        tf_dir = os.path.join(self.temp_dir, 'terraform_dir')
        os.makedirs(tf_dir, exist_ok=True)
        
        # Create a machine.tf file
        with open(os.path.join(tf_dir, 'machine.tf'), 'w') as f:
            f.write('# Test machine.tf file')
        
        # Mock the templates directory path
        with mock.patch('os.path.dirname') as mock_dirname:
            mock_dirname.return_value = self.temp_dir
            
            # Test ensuring config structure
            result = ensure_config_structure(tf_dir)
            self.assertTrue(result)
            
            # Verify files were created
            self.assertTrue(os.path.exists(os.path.join(tf_dir, 'providers.tf')))
            self.assertTrue(os.path.exists(os.path.join(tf_dir, 'variables.tf')))
            
            # Verify warning was logged for missing tfvars (but not a failure)
            self.assertFalse(os.path.exists(os.path.join(tf_dir, 'terraform.tfvars')))

    def test_process_directory(self):
        """Test processing a Terraform directory."""
        # Create a test Terraform directory
        tf_dir = os.path.join(self.temp_dir, 'terraform_dir')
        os.makedirs(tf_dir, exist_ok=True)
        
        # Create a machine.tf file
        with open(os.path.join(tf_dir, 'machine.tf'), 'w') as f:
            f.write('# Test machine.tf file')
        
        # Mock the templates directory path
        with mock.patch('os.path.dirname') as mock_dirname:
            mock_dirname.return_value = self.temp_dir
            
            # Test processing directory
            result = process_directory(tf_dir)
            self.assertTrue(result)
            
            # Verify files were created
            self.assertTrue(os.path.exists(os.path.join(tf_dir, 'providers.tf')))
            self.assertTrue(os.path.exists(os.path.join(tf_dir, 'variables.tf')))
            
            # Create a non-Terraform directory
            non_tf_dir = os.path.join(self.temp_dir, 'non_tf_dir')
            os.makedirs(non_tf_dir, exist_ok=True)
            
            # Test processing a non-Terraform directory
            result = process_directory(non_tf_dir)
            self.assertTrue(result)  # Should be true as it's not a Terraform directory

    def test_missing_main_file(self):
        """Test processing a directory without a main Terraform file."""
        # Create a test Terraform directory
        tf_dir = os.path.join(self.temp_dir, 'incomplete_dir')
        os.makedirs(tf_dir, exist_ok=True)
        
        # Create a providers.tf file but no main.tf or machine.tf
        with open(os.path.join(tf_dir, 'providers.tf'), 'w') as f:
            f.write('# Test providers.tf file')
        
        # Mock the templates directory path
        with mock.patch('os.path.dirname') as mock_dirname:
            mock_dirname.return_value = self.temp_dir
            
            # Test processing a directory missing main files
            result = ensure_config_structure(tf_dir)
            self.assertFalse(result)  # Should fail because no main.tf or machine.tf
            
    def test_tfvars_alternatives(self):
        """Test recognizing alternative tfvars files."""
        # Create a test Terraform directory with machine_inputs.tfvars
        tf_dir = os.path.join(self.temp_dir, 'machine_inputs_dir')
        os.makedirs(tf_dir, exist_ok=True)
        
        # Create a machine.tf file and machine_inputs.tfvars
        with open(os.path.join(tf_dir, 'machine.tf'), 'w') as f:
            f.write('# Test machine.tf file')
            
        with open(os.path.join(tf_dir, 'machine_inputs.tfvars'), 'w') as f:
            f.write('# Test machine_inputs.tfvars file')
        
        # Mock the templates directory path
        with mock.patch('os.path.dirname') as mock_dirname:
            mock_dirname.return_value = self.temp_dir
            
            # Process the directory - should succeed without warnings about tfvars
            with self.assertLogs(level='INFO') as log:
                result = ensure_config_structure(tf_dir)
                self.assertTrue(result)
                # Check that there are no warnings about missing tfvars
                self.assertFalse(any('tfvars not found' in log_message for log_message in log.output))

if __name__ == '__main__':
    unittest.main()
