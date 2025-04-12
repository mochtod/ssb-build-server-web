#!/usr/bin/env python3
"""
Test suite to verify that the VM creation form inputs match Terraform variables
for Atlantis compatibility.

This script:
1. Installs any required dependencies
2. Generates test Terraform configurations
3. Validates them against reference files
4. Provides a comprehensive test report
"""
import os
import sys
import subprocess
import logging
import argparse
import tempfile
import json
import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('atlantis_compatibility_test.log')
    ]
)
logger = logging.getLogger(__name__)

def install_dependencies():
    """Install required dependencies for the validation scripts."""
    logger.info("Installing dependencies...")
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "validation_requirements.txt"
        ])
        logger.info("Dependencies installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install dependencies: {str(e)}")
        return False

def run_generation_test(reference_dir):
    """Run the Terraform generation test."""
    logger.info("Running Terraform generation test...")
    
    try:
        # Import only when needed to avoid import errors
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
        # Try to import and run the test script
        try:
            from test_terraform_generation import main as generation_test
            result = generation_test()
            return result == 0
        except ImportError:
            logger.error("Could not import test_terraform_generation.py")
            return False
    except Exception as e:
        logger.error(f"Error running Terraform generation test: {str(e)}")
        return False

def run_direct_validation(reference_dir, output_file=None):
    """Run direct validation between web form fields and Terraform variables."""
    logger.info("Validating input field mappings...")
    
    try:
        # Create a temporary directory for test output
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test VM configuration
            from vsphere_resource_functions import generate_variables_file, generate_terraform_config
            from test_terraform_generation import create_test_vm_config, setup_env_variables
            
            # Set up environment variables
            setup_env_variables()
            
            # Create test config
            config = create_test_vm_config()
            
            # Generate terraform files
            variables_file = os.path.join(temp_dir, 'terraform.tfvars')
            generate_variables_file(variables_file, config)
            
            machine_tf = generate_terraform_config(config)
            machine_tf_file = os.path.join(temp_dir, 'machine.tf')
            with open(machine_tf_file, 'w') as f:
                f.write(machine_tf)
            
            # Run validation
            from validate_terraform_input_fields import (
                extract_variables_from_tf,
                extract_variables_from_tfvars,
                extract_required_variables_from_machine_tf,
                validate_generated_tfvars_against_expected,
                validate_all_used_vars_are_declared,
                validate_type_compatibility
            )
            
            reference_tfvars_tf = os.path.join(reference_dir, 'tfvars.tf')
            reference_machine_tf = os.path.join(reference_dir, 'machine.tf')
            
            if not os.path.exists(reference_tfvars_tf) or not os.path.exists(reference_machine_tf):
                logger.error(f"Reference files not found in {reference_dir}")
                return False
            
            # Extract variables
            generated_vars = extract_variables_from_tfvars(variables_file)
            expected_vars = extract_variables_from_tf(reference_tfvars_tf)
            used_vars = extract_required_variables_from_machine_tf(reference_machine_tf)
            
            # Perform validations
            is_valid_vars, missing_vars = validate_generated_tfvars_against_expected(
                generated_vars, expected_vars
            )
            
            is_valid_used, undeclared_vars = validate_all_used_vars_are_declared(
                used_vars, expected_vars
            )
            
            is_valid_types, type_issues = validate_type_compatibility(
                generated_vars, expected_vars
            )
            
            all_valid = is_valid_vars and is_valid_used and is_valid_types
            
            # Prepare results
            validation_results = {
                "timestamp": datetime.datetime.now().isoformat(),
                "valid": all_valid,
                "variables": {
                    "valid": is_valid_vars,
                    "missing_vars": missing_vars
                },
                "declarations": {
                    "valid": is_valid_used,
                    "undeclared_vars": list(undeclared_vars)
                },
                "types": {
                    "valid": is_valid_types,
                    "type_issues": {k: v for k, v in type_issues.items()}
                },
                "generated_vars": list(generated_vars.keys()),
                "expected_vars": list(expected_vars.keys()),
                "used_vars": list(used_vars)
            }
            
            # Write validation results to file if specified
            if output_file:
                with open(output_file, 'w') as f:
                    json.dump(validation_results, f, indent=2)
                logger.info(f"Validation results written to {output_file}")
            
            # Log results
            if all_valid:
                logger.info("✅ All validations passed!")
            else:
                logger.warning("❌ Validation issues detected:")
                
                if not is_valid_vars:
                    logger.warning(f"- Missing required variables: {', '.join(missing_vars)}")
                
                if not is_valid_used:
                    logger.warning(f"- Variables used but not declared: {', '.join(undeclared_vars)}")
                
                if not is_valid_types:
                    logger.warning("- Type compatibility issues:")
                    for var_name, issue in type_issues.items():
                        logger.warning(f"  - {var_name}: {issue}")
            
            return all_valid
    except Exception as e:
        logger.error(f"Error running direct validation: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Test suite for VM input field to Terraform variable mapping'
    )
    parser.add_argument(
        '--reference-dir', 
        default='vm-workspace',
        help='Directory containing reference Terraform files (default: vm-workspace)'
    )
    parser.add_argument(
        '--output-file',
        help='File to write validation results to'
    )
    parser.add_argument(
        '--skip-deps',
        action='store_true',
        help='Skip dependency installation'
    )
    args = parser.parse_args()
    
    logger.info("=== Atlantis Compatibility Test Suite ===")
    logger.info(f"Started at: {datetime.datetime.now().isoformat()}")
    
    # Install dependencies if not skipped
    if not args.skip_deps:
        if not install_dependencies():
            logger.error("Failed to install dependencies. Exiting.")
            return 1
    
    # Run the generation test
    if not run_generation_test(args.reference_dir):
        logger.error("Terraform generation test failed. See log for details.")
        return 1
    
    # Run direct validation
    if not run_direct_validation(args.reference_dir, args.output_file):
        logger.error("Direct validation failed. See log for details.")
        return 1
    
    logger.info("✅ All tests passed! The VM input fields should now be compatible with Terraform variables.")
    logger.info("To verify in production:")
    logger.info("1. Create a VM using the web form")
    logger.info("2. Check that Atlantis plans and applies the configuration successfully")
    logger.info("3. If issues persist, run validation against the generated files")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
