# VM Workspace

This directory contains the Terraform configurations for VM provisioning in the SSB Build Server Web application.

## Files

- **machine.tf**: Defines the VM resources and module
- **providers.tf**: Configures the vSphere and Vault providers
- **data.tf**: Defines data sources and local variables
- **backend.tf**: Configures the Atlantis backend
- **tfvars.tf**: Defines input variables
- **machine_inputs.tfvars**: Example input variables for VM creation
- **fetch_next_ip.py**: Python script for IP address allocation

## Integration with Web Application

The web application generates Terraform files based on user input and stores them in the `terraform` directory. These files reference the configurations in this directory.

## Terraform Workflow

1. The web application generates a `machine.tf` file and a `terraform.tfvars` file based on user input
2. Atlantis runs a Terraform plan using these files
3. After approval, Atlantis applies the plan to create the VMs in VMware vSphere

## Configuration

### VMware vSphere

The Terraform configurations use the VMware vSphere provider to create virtual machines. The following variables need to be configured:

- `vsphere_user`: vSphere username
- `vsphere_password`: vSphere password
- `vsphere_server`: vSphere server address

### NetBox Integration

The `fetch_next_ip.py` script is used to allocate IP addresses from NetBox. It requires:

- `netbox_token`: Authentication token for NetBox API

## Customization

To customize the VM configurations, modify the following files:

- **machine.tf**: Update the VM resource definitions
- **machine_inputs.tfvars**: Update the default input values
