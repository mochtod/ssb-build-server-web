# Atlantis Plan Alignment

This document outlines the changes made to align Terraform variables, machine inputs, and module structure to support proper Atlantis plan execution and VM creation in vSphere.

## Changes Made

### 1. Module Enhancement (modules/machine)

- Added support for `additional_disks` with dynamic block
- Added support for custom `hostname` separated from VM name
- Updated Linux customization options to use custom hostname when provided

### 2. Dynamic Resource Resolution

- Added resource name variables (`datacenter_name`, `datastore_name`, etc.) for lookup
- Implemented data sources to dynamically fetch resources by name
- Made ID variables optional with default = null
- Maintained backward compatibility for direct ID use if needed

### 3. Variable Standardization

- Renamed `quantity` to `server_count` for consistency
- Updated machine_inputs.tfvars to match variables.tf structure
- Added documentation for each variable group
- Ensured all required variables have sensible defaults when possible

### 4. NetBox Integration

- Integrated with existing `fetch_next_ip.py` for dynamic IP allocation
- Used `external` data source to get IPs from NetBox
- Added NetBox configuration variables to machine_inputs.tfvars

### 5. Machine.tf Refactoring

- Eliminated duplicate VM resource definition
- Implemented the module pattern for cleaner code organization
- Added proper count-based VM creation
- Improved naming with prefix-base-number pattern
- Set up proper outputs for module instances

## Usage

To use this terraform configuration:

1. Fill in the actual values in `machine_inputs.tfvars`:
   - Update vSphere resource names (datacenter, datastore, etc.)
   - Configure VM specs as needed (CPUs, memory, disk size)
   - Set up NetBox token and API URL for IP allocation

2. Run Atlantis plan:
   ```
   atlantis plan -d vm-workspace -var-file=machine_inputs.tfvars
   ```

3. Apply the plan to create VMs:
   ```
   atlantis apply -d vm-workspace
   ```

## Benefits

- Cleaner, more maintainable code using modules
- Dynamic resource lookup by name instead of hard-coded IDs
- IP address allocation from NetBox
- Support for additional disks and custom hostnames
- Better integration with Atlantis workflow
