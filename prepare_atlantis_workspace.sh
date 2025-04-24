#!/bin/bash
# prepare_atlantis_workspace.sh
# Script to prepare a local VM workspace for Atlantis to use

# Set up directory structure for Atlantis
WORKSPACE_DIR="vm-workspace"
TERRAFORM_DIR="terraform"

echo "Ensuring ${WORKSPACE_DIR} directory exists..."
mkdir -p "${WORKSPACE_DIR}"

echo "Copying Terraform files for Atlantis to use..."
if [ ! -f "${WORKSPACE_DIR}/machine.tf" ]; then
    echo "Copying machine.tf template to workspace..."
    if [ -f "${TERRAFORM_DIR}/templates/machine.tf" ]; then
        cp "${TERRAFORM_DIR}/templates/machine.tf" "${WORKSPACE_DIR}/"
    else
        echo "WARNING: No machine.tf template found - VM creation may fail"
    fi
fi

# Create a default machine_inputs.tfvars file if it doesn't exist
if [ ! -f "${WORKSPACE_DIR}/machine_inputs.tfvars" ]; then
    echo "Creating default machine_inputs.tfvars file..."
    cat > "${WORKSPACE_DIR}/machine_inputs.tfvars" << EOF
# Default machine inputs - will be populated during build process
name             = "lin2dv2-ssb"
num_cpus         = 2
memory           = 4096
disk_size        = 50
guest_id         = "rhel9_64Guest"
adapter_type     = "vmxnet3"
time_zone        = "UTC"
quantity         = 1
start_number     = 10001
dns_servers      = ["8.8.8.8", "8.8.4.4"]

# These values will be populated from vSphere during the Terraform plan phase
resource_pool_id = "<resource_pool_id>"
datastore_id     = "<datastore_id>"
network_id       = "<network_id>"
template_uuid    = "<template_uuid>"
ipv4_address     = "<ipv4_address>"
ipv4_netmask     = 24
ipv4_gateway     = "<ipv4_gateway>"

# Additional disk configuration
additional_disks = []
EOF
fi

# Ensure Atlantis can access the local files by setting permissions
echo "Setting proper permissions..."
chmod -R 755 "${WORKSPACE_DIR}"

# Create a terraform.tfvars file with default values for testing
if [ ! -f "${WORKSPACE_DIR}/terraform.tfvars" ]; then
    echo "Creating terraform.tfvars with default values..."
    cat > "${WORKSPACE_DIR}/terraform.tfvars" << EOF
# Default Terraform variables
environment = "development"
EOF
fi

echo "Local VM workspace is ready for Atlantis!"
echo "To test Atlantis with this workspace, run: docker-compose up -d"