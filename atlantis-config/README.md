# Atlantis Configuration

This directory contains configuration files for the Atlantis server, which is used to manage Terraform workflows for VM provisioning.

## Files

- **repo-config.yaml**: Defines the repository configuration and workflows for Atlantis.

## Configuration Details

### Workflows

The configuration defines a custom workflow that includes:

1. **Plan Workflow**:
   - Initialize Terraform
   - Run plan with terraform.tfvars file

2. **Apply Workflow**:
   - Apply the Terraform plan

### Apply Requirements

The configuration requires approval before applying any Terraform plan, which aligns with the web application's approval workflow.

## Integration with Web Application

The Atlantis server is integrated with the SSB Build Server Web application through:

1. **Shared Volumes**:
   - The web application generates Terraform files in the `terraform` directory
   - Atlantis has access to these files through volume mapping

2. **API Communication**:
   - The web application communicates with Atlantis through its API
   - Authentication is handled via the ATLANTIS_TOKEN

## Usage

The Atlantis server is automatically started as part of the Docker Compose setup. No manual configuration is required.
