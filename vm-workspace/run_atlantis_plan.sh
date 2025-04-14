#!/bin/bash
# Script to run Atlantis plan on the vm-workspace directory
# This script simulates the Atlantis plan workflow for testing

# Set environment variables for Terraform
export VSPHERE_USER=your-vsphere-username
export VSPHERE_PASSWORD=your-vsphere-password
export VSPHERE_SERVER=virtualcenter.example.com
export NETBOX_TOKEN=your-netbox-token
export NETBOX_URL=https://netbox.example.com/api

# Navigate to the workspace directory
cd "$(dirname "$0")"

# Optional: Clean any previous state
rm -rf .terraform .terraform.lock.hcl terraform.tfstate*

# Initialize Terraform
echo "Initializing Terraform..."
terraform init

# Run Terraform plan with the machine inputs file
echo "Running Terraform plan with machine_inputs.tfvars..."
terraform plan -var-file=machine_inputs.tfvars -out=terraform.tfplan

# Show the plan in readable format
echo "Plan details:"
terraform show terraform.tfplan
