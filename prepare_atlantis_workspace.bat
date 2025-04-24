@echo off
REM prepare_atlantis_workspace.bat
REM Script to prepare a local VM workspace for Atlantis to use on Windows

set WORKSPACE_DIR=vm-workspace
set TERRAFORM_DIR=terraform

echo Ensuring %WORKSPACE_DIR% directory exists...
if not exist "%WORKSPACE_DIR%" mkdir "%WORKSPACE_DIR%"

echo Copying Terraform files for Atlantis to use...
if not exist "%WORKSPACE_DIR%\machine.tf" (
    echo Copying machine.tf template to workspace...
    if exist "%TERRAFORM_DIR%\templates\machine.tf" (
        copy "%TERRAFORM_DIR%\templates\machine.tf" "%WORKSPACE_DIR%\"
    ) else (
        echo WARNING: No machine.tf template found - VM creation may fail
    )
)

REM Create a default machine_inputs.tfvars file if it doesn't exist
if not exist "%WORKSPACE_DIR%\machine_inputs.tfvars" (
    echo Creating default machine_inputs.tfvars file...
    (
        echo # Default machine inputs - will be populated during build process
        echo name             = "lin2dv2-ssb"
        echo num_cpus         = 2
        echo memory           = 4096
        echo disk_size        = 50
        echo guest_id         = "rhel9_64Guest"
        echo adapter_type     = "vmxnet3"
        echo time_zone        = "UTC"
        echo quantity         = 1
        echo start_number     = 10001
        echo dns_servers      = ["8.8.8.8", "8.8.4.4"]
        echo.
        echo # These values will be populated from vSphere during the Terraform plan phase
        echo resource_pool_id = "^<resource_pool_id^>"
        echo datastore_id     = "^<datastore_id^>"
        echo network_id       = "^<network_id^>"
        echo template_uuid    = "^<template_uuid^>"
        echo ipv4_address     = "^<ipv4_address^>"
        echo ipv4_netmask     = 24
        echo ipv4_gateway     = "^<ipv4_gateway^>"
        echo.
        echo # Additional disk configuration
        echo additional_disks = []
    ) > "%WORKSPACE_DIR%\machine_inputs.tfvars"
)

REM Create a terraform.tfvars file with default values for testing
if not exist "%WORKSPACE_DIR%\terraform.tfvars" (
    echo Creating terraform.tfvars with default values...
    (
        echo # Default Terraform variables
        echo environment = "development"
    ) > "%WORKSPACE_DIR%\terraform.tfvars"
)

echo Local VM workspace is ready for Atlantis!
echo To test Atlantis with this workspace, run: docker-compose up -d