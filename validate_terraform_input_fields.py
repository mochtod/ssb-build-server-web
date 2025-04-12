#!/usr/bin/env python3
"""
Validation script to ensure createVM input fields match the tfvars file
and machine.tf variables for Atlantis compatibility.

This script compares:
1. The web app's generated terraform.tfvars
2. The variables declared in tfvars.tf
3. The expected variables used in machine.tf

It reports any discrepancies that might cause Atlantis plan/apply to fail.
"""
import os
import json
import re
import argparse
import logging
import hcl2

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_variables_from_tf(tf_file):
    """
    Extract variable declarations from a Terraform file.
    
    Args:
        tf_file (str): Path to the Terraform file
        
    Returns:
        dict: Dictionary of variable names and their attributes
    """
    try:
        with open(tf_file, 'r') as f:
            content = f.read()
            
        # Use hcl2 to parse the Terraform file
        try:
            parsed = hcl2.load(open(tf_file))
            variables = {}
            
            # Extract variable declarations
            if 'variable' in parsed:
                for var_name, var_attrs in parsed['variable'].items():
                    variables[var_name] = var_attrs
                    
            return variables
        except Exception as e:
            # Fallback to regex if HCL parsing fails
            logger.warning(f"HCL parsing failed, using regex fallback: {str(e)}")
            
            # Extract variable names using regex
            var_pattern = r'variable\s+"([^"]+)"\s+\{[^}]*\}'
            variables = {}
            
            for match in re.finditer(var_pattern, content):
                var_name = match.group(1)
                var_block = match.group(0)
                
                # Extract type if present
                type_match = re.search(r'type\s+=\s+([^\n]+)', var_block)
                var_type = type_match.group(1).strip() if type_match else "unknown"
                
                # Extract default if present
                default_match = re.search(r'default\s+=\s+([^\n]+)', var_block)
                default = default_match.group(1).strip() if default_match else None
                
                variables[var_name] = {
                    "type": var_type,
                    "default": default
                }
                
            return variables
    except Exception as e:
        logger.error(f"Error extracting variables from {tf_file}: {str(e)}")
        return {}

def extract_variables_from_tfvars(tfvars_file):
    """
    Extract variables from a Terraform tfvars file.
    
    Args:
        tfvars_file (str): Path to the tfvars file
        
    Returns:
        dict: Dictionary of variable names and their values
    """
    try:
        with open(tfvars_file, 'r') as f:
            content = f.read()
            
        # Try parsing as HCL
        try:
            parsed = hcl2.load(open(tfvars_file))
            return parsed
        except Exception:
            # Fallback to regex if HCL parsing fails
            logger.warning(f"HCL parsing failed for {tfvars_file}, using regex fallback")
            
            variables = {}
            # Match lines like: name = "value" or name = 123
            var_pattern = r'^\s*([a-zA-Z0-9_]+)\s*=\s*(.+)\s*$'
            
            for line in content.split('\n'):
                match = re.match(var_pattern, line)
                if match:
                    var_name = match.group(1)
                    var_value = match.group(2).strip()
                    
                    # Clean up strings
                    if var_value.startswith('"') and var_value.endswith('"'):
                        var_value = var_value[1:-1]
                    # Try to convert to number if possible
                    elif var_value.isdigit():
                        var_value = int(var_value)
                        
                    variables[var_name] = var_value
                    
            return variables
    except Exception as e:
        logger.error(f"Error extracting variables from {tfvars_file}: {str(e)}")
        return {}

def extract_required_variables_from_machine_tf(machine_tf_file):
    """
    Extract variables used in the machine.tf file.
    
    Args:
        machine_tf_file (str): Path to the machine.tf file
        
    Returns:
        set: Set of variable names used in machine.tf
    """
    try:
        with open(machine_tf_file, 'r') as f:
            content = f.read()
            
        # Pattern to find variable references like var.name
        var_pattern = r'var\.([a-zA-Z0-9_]+)'
        var_matches = re.findall(var_pattern, content)
        
        # Return unique set of variable names
        return set(var_matches)
    except Exception as e:
        logger.error(f"Error extracting used variables from {machine_tf_file}: {str(e)}")
        return set()

def validate_generated_tfvars_against_expected(generated_vars, expected_vars):
    """
    Validate that the generated tfvars contains all required variables.
    
    Args:
        generated_vars (dict): Variables from generated tfvars
        expected_vars (dict): Variables expected from tfvars.tf
        
    Returns:
        tuple: (bool, list) - (is_valid, missing_vars)
    """
    missing_vars = []
    
    for var_name, var_attrs in expected_vars.items():
        # Skip variables with defaults as they're not strictly required
        if 'default' in var_attrs and var_attrs['default'] is not None:
            continue
            
        # Check if required variable is present in generated vars
        if var_name not in generated_vars:
            missing_vars.append(var_name)
    
    is_valid = len(missing_vars) == 0
    return is_valid, missing_vars

def validate_all_used_vars_are_declared(used_vars, declared_vars):
    """
    Validate that all variables used in machine.tf are declared.
    
    Args:
        used_vars (set): Variables used in machine.tf
        declared_vars (dict): Variables declared in tfvars.tf
        
    Returns:
        tuple: (bool, list) - (is_valid, undeclared_vars)
    """
    undeclared_vars = []
    
    for var in used_vars:
        if var not in declared_vars:
            undeclared_vars.append(var)
    
    is_valid = len(undeclared_vars) == 0
    return is_valid, undeclared_vars

def validate_type_compatibility(generated_vars, expected_vars):
    """
    Validate type compatibility between generated and expected variables.
    
    Args:
        generated_vars (dict): Variables from generated tfvars
        expected_vars (dict): Variables expected from tfvars.tf
        
    Returns:
        tuple: (bool, dict) - (is_valid, type_issues)
    """
    type_issues = {}
    
    for var_name, var_value in generated_vars.items():
        if var_name in expected_vars:
            expected_type = expected_vars[var_name].get('type', '')
            
            # Check if string value is provided for number type
            if 'number' in expected_type and isinstance(var_value, str) and not var_value.isdigit():
                type_issues[var_name] = f"Expected number, got string: '{var_value}'"
                
            # Check if non-list value is provided for list type
            elif 'list' in expected_type and not isinstance(var_value, list):
                type_issues[var_name] = f"Expected list, got {type(var_value).__name__}: {var_value}"
    
    is_valid = len(type_issues) == 0
    return is_valid, type_issues

def main():
    parser = argparse.ArgumentParser(description='Validate Terraform files compatibility with Atlantis')
    parser.add_argument('--generated-tf-dir', required=True, help='Directory containing the generated Terraform files')
    parser.add_argument('--reference-tf-dir', required=True, help='Directory containing the reference Terraform files')
    args = parser.parse_args()
    
    # Define file paths
    generated_tfvars = os.path.join(args.generated_tf_dir, 'terraform.tfvars')
    generated_machine_tf = os.path.join(args.generated_tf_dir, 'machine.tf')
    reference_tfvars_tf = os.path.join(args.reference_tf_dir, 'tfvars.tf')
    reference_machine_tf = os.path.join(args.reference_tf_dir, 'machine.tf')
    
    # Check if all files exist
    missing_files = []
    for file_path in [generated_tfvars, generated_machine_tf, reference_tfvars_tf, reference_machine_tf]:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        logger.error(f"Missing files: {', '.join(missing_files)}")
        return 1
    
    # Extract variables from files
    logger.info("Extracting variables from files...")
    generated_vars = extract_variables_from_tfvars(generated_tfvars)
    expected_vars = extract_variables_from_tf(reference_tfvars_tf)
    used_vars = extract_required_variables_from_machine_tf(reference_machine_tf)
    
    logger.info(f"Found {len(generated_vars)} variables in generated tfvars")
    logger.info(f"Found {len(expected_vars)} variables in reference tfvars.tf")
    logger.info(f"Found {len(used_vars)} variables used in reference machine.tf")
    
    # Perform validations
    all_valid = True
    
    # 1. Check if all required variables are present
    is_valid, missing_vars = validate_generated_tfvars_against_expected(generated_vars, expected_vars)
    if not is_valid:
        all_valid = False
        logger.warning(f"Missing required variables in generated tfvars: {', '.join(missing_vars)}")
    else:
        logger.info("✓ All required variables are present in generated tfvars")
    
    # 2. Check if all used variables are declared
    is_valid, undeclared_vars = validate_all_used_vars_are_declared(used_vars, expected_vars)
    if not is_valid:
        all_valid = False
        logger.warning(f"Variables used in machine.tf but not declared: {', '.join(undeclared_vars)}")
    else:
        logger.info("✓ All variables used in machine.tf are properly declared")
    
    # 3. Check type compatibility
    is_valid, type_issues = validate_type_compatibility(generated_vars, expected_vars)
    if not is_valid:
        all_valid = False
        logger.warning("Type compatibility issues:")
        for var_name, issue in type_issues.items():
            logger.warning(f"  - {var_name}: {issue}")
    else:
        logger.info("✓ All variable types are compatible")
    
    # Print summary
    if all_valid:
        logger.info("✅ All validations passed! The generated Terraform files should be compatible with Atlantis.")
        return 0
    else:
        logger.warning("⚠️ Validation issues detected. The generated Terraform files may cause issues with Atlantis.")
        return 1

if __name__ == "__main__":
    main()
