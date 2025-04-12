# Terraform Variable Mapping

This document maps the variables defined in Terraform files to the input fields from the web application, identifying any gaps or mismatches.

## Variables in tfvars.tf vs Web Form Inputs

| Terraform Variable | Type | Default Value | Web Form Field | Notes |
|-------------------|------|---------------|----------------|-------|
| vsphere_user | string | - | N/A | Set from environment |
| vsphere_password | string | - | N/A | Set from environment |
| vsphere_server | string | - | N/A | Set from environment |
| hostname_prefix | string | - | server_prefix | Combined with app_name |
| server_count | number | - | quantity | |
| netbox_token | string | - | N/A | Set from environment |
| netbox_api_url | string | "https://netbox.chrobinson.com/api" | N/A | Environment variable |
| vault_token | string | "" | N/A | Not used in web app |
| vault_role_id | string | "" | N/A | Not used in web app |
| vault_secret_id | string | "" | N/A | Not used in web app |
| vault_k8s_role | string | "" | N/A | Not used in web app |
| name | string | "rhel9-vm" | server_name | Combined from server_prefix and app_name |
| resource_pool_id | string | - | resource_pool | From vsphere_resources |
| datastore_id | string | - | datastore | From vsphere_resources |
| num_cpus | number | 2 | num_cpus | |
| memory | number | 4096 | memory | |
| guest_id | string | "rhel9_64Guest" | N/A | Hard-coded |
| network_id | string | - | network | From vsphere_resources |
| adapter_type | string | "vmxnet3" | N/A | Hard-coded |
| disk_size | number | 20 | disk_size | |
| template_uuid | string | - | template | From vsphere_resources |
| ipv4_address | string | "192.168.1.100" | N/A | Set via NetBox |
| ipv4_netmask | number | 24 | N/A | Hard-coded |
| ipv4_gateway | string | "192.168.1.1" | N/A | Hard-coded |
| dns_servers | list(string) | ["8.8.8.8", "8.8.4.4"] | N/A | Hard-coded |
| time_zone | string | "UTC" | N/A | Hard-coded |
| start_number | number | 1 | start_number | |
| end_number | number | 100 | N/A | Hard-coded |
| additional_disks | list(object) | [] | additional_disks | Derived from additional_disk_size_N and additional_disk_type_N fields |

## Variables in machine.tf Module

The `machine.tf` file uses the following variables:

1. `quantity` - Derived from web form
2. Module `rhel9_vm` uses variables that match the module's input requirements

## Variables in modules/machine/variables.tf

These variables must be provided to the module:

| Module Variable | Type | Default Value | Source |
|----------------|------|---------------|--------|
| name | string | - | From web form (server_name) |
| resource_pool_id | string | - | From web form (resource_pool) |
| datastore_id | string | - | From web form (datastore) |
| num_cpus | number | 2 | From web form (num_cpus) |
| memory | number | 4096 | From web form (memory) |
| guest_id | string | "rhel9_64Guest" | Hard-coded |
| network_id | string | - | From web form (network) |
| adapter_type | string | "vmxnet3" | Hard-coded |
| disk_size | number | 20 | From web form (disk_size) |
| template_uuid | string | - | From web form (template) |
| ipv4_address | string | - | From NetBox |
| ipv4_netmask | number | 24 | Hard-coded |
| ipv4_gateway | string | - | Hard-coded |
| dns_servers | list(string) | ["8.8.8.8", "8.8.4.4"] | Hard-coded |
| time_zone | string | "UTC" | Hard-coded |

## Web Application Input Fields

The web form collects the following fields:

1. `server_prefix` - Used to form server_name
2. `app_name` - Used to form server_name
3. `quantity` - Number of VMs to create
4. `num_cpus` - CPU count
5. `memory` - Memory in MB
6. `disk_size` - Disk size in GB
7. `cluster` - vSphere cluster
8. `resource_pool` - vSphere resource pool
9. `datastore` - vSphere datastore
10. `network` - vSphere network
11. `template` - vSphere template
12. `additional_disk_size_N` - Additional disk sizes
13. `additional_disk_type_N` - Additional disk types

## Issues and Gaps

1. **Missing variables in web form**:
   - Some variables like `vault_token` are in Terraform but not in the web form (likely by design)
   - IP addressing details are expected to be provided by NetBox

2. **Variable transformations**:
   - `server_name` is formed from `server_prefix` and `app_name`
   - `additional_disks` is derived from multiple form fields

3. **Hard-coded values**:
   - Several variables are hard-coded rather than collected from the web form

## Generated Files in vsphere_resource_functions.py

1. `generate_variables_file()` - Creates terraform.tfvars
2. `generate_terraform_config()` - Creates machine.tf
