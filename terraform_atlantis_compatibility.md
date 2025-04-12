# Ensuring VM Input Fields Match Terraform Variables

## Overview

This document describes the critical relationship between the VM creation form in the web application and the Terraform variables required by Atlantis. It explains how we've ensured compatibility and what to check when making future changes.

## Problem Addressed

The web application collects VM configuration information through input fields and uses this to generate Terraform files that Atlantis then processes. A mismatch between the collected inputs and required Terraform variables can cause Atlantis plan or apply operations to fail.

Specific issues that have been addressed:

1. Missing variables in the generated terraform.tfvars file
2. Type mismatches between form inputs and expected Terraform variable types
3. Inconsistent naming between web form fields and Terraform variables

## Implementation Details

### 1. Complete Variable Generation

The `generate_variables_file()` function in `vsphere_resource_functions.py` has been updated to:

- Include ALL variables defined in `tfvars.tf`
- Pull values from environment variables where appropriate
- Use sensible defaults for variables not directly captured in the web form

### 2. Validation Script

A new script `validate_terraform_input_fields.py` has been added to:

- Extract variables from the generated terraform.tfvars file
- Compare them against the variable declarations in tfvars.tf
- Check that all variables used in machine.tf are properly defined
- Validate type compatibility between generated and expected variables

### 3. Testing Tool

`test_terraform_generation.py` provides an easy way to:

- Generate test Terraform files based on a sample VM configuration
- Run validation against the reference Terraform files
- Report any discrepancies

## Variable Mapping Reference

The file `terraform_variable_mapping.md` provides a detailed mapping between:

- Web form input fields
- Generated terraform.tfvars variables
- Expected variable declarations in tfvars.tf
- Variables used in machine.tf

This mapping should be consulted when making changes to the web form or Terraform files.

## Best Practices for Future Development

1. **When Adding New Web Form Fields:**
   - Add corresponding variables to the `generate_variables_file()` function
   - Document the mapping in `terraform_variable_mapping.md`
   - Run the test script to validate compatibility

2. **When Updating Terraform Files:**
   - Update the corresponding parts of `generate_terraform_config()`
   - Ensure new variables are included in `generate_variables_file()`
   - Run the validation script to detect any discrepancies

3. **Before Testing with Atlantis:**
   - Run `python test_terraform_generation.py` to verify compatibility
   - Fix any reported issues before proceeding

## Troubleshooting

### Common Issues:

1. **Atlantis plan fails with "Required variable not set" error:**
   - Check that all required variables are included in the generated terraform.tfvars file
   - Verify that environment variables for sensitive values are properly set

2. **Type compatibility errors:**
   - Ensure number values aren't being passed as strings
   - Check that list variables are properly formatted

3. **Variable name mismatches:**
   - Confirm variable names in generated files match those expected in tfvars.tf

### Debugging Steps:

1. Generate sample Terraform files using the test script
2. Compare the generated terraform.tfvars with the reference machine_inputs.tfvars
3. Check if all variables used in machine.tf are properly defined
4. Run the validation script to identify specific issues

## Conclusion

By ensuring that the web form input fields correctly map to the expected Terraform variables, we've improved the reliability of the VM creation process through Atlantis. The added validation and testing tools provide safeguards against future compatibility issues.
