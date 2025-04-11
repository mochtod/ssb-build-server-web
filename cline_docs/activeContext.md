# Active Context: SSB Build Server Web

## Current Focus

The current focus is on testing and validating the end-to-end workflow with the combined repository structure. We have successfully combined the SSB Build Server Web application and the VM workspace into a single repository with a containerized Atlantis setup.

## Recent Changes

- Implemented vSphere resource optimization to improve VM provisioning performance
- Memory bank initialization for the project
- Documentation of the web application and VM workspace structure
- Implementation of the complete `generate_terraform_config()` function
- Implementation of the `generate_variables_file()` function
- Update of Atlantis integration functions for containerized setup
- Creation of detailed documentation for containerized Atlantis setup
- Combination of the SSB Build Server Web and VM workspace repositories
- Configuration of Docker Compose for the combined setup
- Added GitHub integration for Atlantis in docker-compose.yml and .env
- Updated Atlantis configuration to use dummy GitHub credentials for testing
- Implemented graceful fallback mechanism for handling Atlantis API issues
- Created multiple test scripts to diagnose and resolve API formatting problems
- Added simulation capability for plan and apply operations when API fails
- Created UI testing framework for automated workflow validation
- Added an admin settings page for environment variable management
- Implemented secure password hashing system with bcrypt for user authentication
- Enhanced Atlantis integration with direct VM provisioning fallback
- Created a unified base template for consistent layout and navigation
- Added connection testing functionality for external services
- Implemented an end-to-end test script for workflow validation

## Current State

The application is in a mostly functional state:

1. **Working Components**:
   - User authentication and role-based access control
   - Web interface for VM configuration
   - Configuration storage as JSON files
   - Terraform module generation
   - Atlantis API integration with graceful error handling for API issues
   - Fallback simulation mechanism for plan and apply operations
   - Optimized vSphere resource retrieval for improved performance

2. **Pending Components**:
   - End-to-end validation in production environment
   - NetBox integration for IP address allocation
   - Security improvements for password storage
   - Comprehensive automated testing

## Next Steps

1. **Complete End-to-End Testing**:
   - Run automated UI tests to verify workflow functionality
   - Validate fallback mechanism in different failure scenarios
   - Test simulated operations with admin approval workflow
   - Test vSphere resource optimization in production environment

2. **Production Environment Integration**:
   - Set up production instance of Atlantis
   - Configure real GitHub repository for production use
   - Test VM provisioning in staging environment

3. **Implement NetBox Integration**:
   - Update the fetch_next_ip.py script
   - Integrate with the VM provisioning workflow

4. **Improve Security**:
   - Implement password hashing
   - Secure sensitive information in configurations

5. **Add Automated Testing**:
   - Create unit tests for key functions
   - Set up integration tests for the workflow

## Technical Considerations

1. **Terraform Format Compatibility**:
   - The generated Terraform files must match the expected format in the rhel9-vm-workspace
   - Pay attention to variable names, resource types, and module structure

2. **Atlantis API Integration**:
   - Ensure proper authentication and request formatting for Atlantis API calls
   - Handle asynchronous nature of plan and apply operations

3. **Security**:
   - Protect sensitive information in generated Terraform files
   - Ensure proper access controls for VM provisioning

## Dependencies

1. **External Systems**:
   - Atlantis server availability and configuration
   - VMware vSphere environment access
   - NetBox for IP address allocation

2. **Internal Components**:
   - Flask web application functionality
   - File system access for configuration and Terraform files
   - User authentication and authorization

## Required Configuration Variables

### Web Application Environment Variables
1. **FLASK_SECRET_KEY**: Secret key for Flask sessions (e.g., "change_this_to_a_random_secure_key")
2. **CONFIG_DIR**: Directory for storing configuration files (default: "/app/configs")
3. **TERRAFORM_DIR**: Directory for storing Terraform files (default: "/app/terraform")
4. **USERS_FILE**: Path to the users.json file (default: "/app/users.json")
5. **DEBUG**: Enable debug mode (default: "True")
6. **ATLANTIS_URL**: URL for the Atlantis server (e.g., "http://atlantis:4141" for containerized setup)
7. **ATLANTIS_TOKEN**: Authentication token for Atlantis API
8. **TIMEOUT**: Timeout value in seconds (default: 120)
9. **GIT_REPO_URL**: URL for the Git repository (not needed for containerized Atlantis without GitHub)
10. **GIT_USERNAME**: Git username (not needed for containerized Atlantis without GitHub)
11. **GIT_TOKEN**: Git access token (not needed for containerized Atlantis without GitHub)

### VMware vSphere Variables
1. **vsphere_user**: vSphere username
2. **vsphere_password**: vSphere password
3. **vsphere_server**: vSphere server address
4. **resource_pool_id**: ID of the resource pool for VM creation
5. **datastore_id**: ID of the datastore for VM storage
6. **network_id**: ID of the network for VM networking
7. **template_uuid**: UUID of the VM template to clone

### NetBox Variables
1. **netbox_token**: Authentication token for NetBox API

### Atlantis Configuration
For containerized Atlantis setup with GitHub integration:
1. **ATLANTIS_PORT**: Port for Atlantis server (default: 4141)
2. **ATLANTIS_CONFIG**: Path to Atlantis configuration file
3. **ATLANTIS_REPO_ALLOWLIST**: List of allowed repositories (can be set to "*" for all)
4. **ATLANTIS_REPO_CONFIG**: Path to repository configuration file
5. **GITHUB_USER**: GitHub username for Atlantis integration
6. **GITHUB_TOKEN**: GitHub personal access token with repo scope for Atlantis integration

## Risks and Mitigations

1. **Risk**: Generated Terraform files may not be compatible with Atlantis
   - **Mitigation**: Test with sample files from the rhel9-vm-workspace as templates

2. **Risk**: API communication failures with Atlantis
   - **Mitigation**: Implemented robust error handling with simulation fallback
   - **Status**: Addressed with the new graceful fallback mechanism

3. **Risk**: Security vulnerabilities in VM provisioning
   - **Mitigation**: Enforce strict validation and approval workflows
