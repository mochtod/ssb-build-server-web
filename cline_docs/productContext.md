# Product Context: SSB Build Server Web

## Why This Project Exists

The SSB Build Server Web application exists to provide a user-friendly web interface for provisioning RHEL9 virtual machines in the CH Robinson infrastructure. It serves as a bridge between end users who need to create VMs and the underlying infrastructure automation tools (Terraform, Atlantis, and VMware vSphere).

## Problems It Solves

1. **Simplifies VM Provisioning**: Abstracts the complexity of Terraform configurations and VMware vSphere operations behind a simple web interface.

2. **Standardizes VM Creation**: Ensures all VMs are created following company standards and naming conventions.

3. **Enforces Approval Workflows**: Implements a structured approval process where administrators must review and approve VM configurations before they can be built.

4. **Centralized Management**: Provides a single platform for tracking VM configurations, build status, and history.

5. **Self-Service Capabilities**: Allows users with appropriate permissions to initiate VM creation without requiring direct access to infrastructure tools.

6. **Audit Trail**: Maintains records of who created VMs, when they were approved, and by whom.

## How It Should Work

### User Workflow

1. **Authentication**: Users log in with their credentials (username/password).

2. **VM Configuration**: Users specify VM details through a form interface:
   - Server environment (development, integration, training, production)
   - Application name (3-5 characters)
   - VM specifications (CPU, memory, disk size)
   - Additional storage requirements

3. **Configuration Review**: The system generates a Terraform configuration based on user inputs and displays it for review.

4. **Plan Generation**: Users can initiate a Terraform plan through Atlantis to validate their configuration.

5. **Approval Process**: Administrators review and approve/reject VM configurations.

6. **VM Provisioning**: Approved configurations are submitted to Atlantis, which applies the Terraform configuration to create VMs in VMware vSphere.

7. **Build Receipt**: Users receive confirmation of successful VM creation with details about the new VM(s).

### System Workflow

1. **Web Interface**: Flask-based web application provides the user interface.

2. **Configuration Generation**: The application generates Terraform module files based on user inputs.

3. **Atlantis Integration**: The application communicates with Atlantis API to:
   - Submit Terraform plans for validation
   - Apply approved configurations to create VMs

4. **VMware Integration**: Terraform (via Atlantis) communicates with VMware vSphere to provision the actual VMs.

5. **IP Management**: The system integrates with NetBox to allocate IP addresses for new VMs.

6. **Persistent Storage**: Configurations are stored as JSON files and Terraform files for future reference.

## Current Status

The front-end web interface is functioning correctly, but there is an issue with generating the proper Terraform module files that Atlantis can read and action on. This is a critical gap that needs to be addressed to make the application fully functional.
