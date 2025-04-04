# Atlantis Containerized Setup

## Overview

This document outlines how to set up Atlantis in a containerized environment without GitHub integration, as requested for the SSB Build Server Web application. This setup allows Terraform operations to be executed directly through the Atlantis API without requiring a Git repository.

## Container Configuration

### Docker Compose Configuration

Add the following service to the `docker-compose.yml` file:

```yaml
services:
  # Existing web service...
  
  atlantis:
    image: ghcr.io/runatlantis/atlantis:latest
    ports:
      - "4141:4141"
    environment:
      - ATLANTIS_PORT=4141
      - ATLANTIS_ATLANTIS_URL=http://atlantis:4141
      - ATLANTIS_REPO_ALLOWLIST=*
      - ATLANTIS_ENABLE_POLICY_CHECKS=false
      - ATLANTIS_AUTOPLAN_FILE_LIST=*.tf,*.tfvars
      - ATLANTIS_WRITE_GIT_CREDS=false
      - ATLANTIS_REPO_CONFIG=/etc/atlantis/repo-config.yaml
      - ATLANTIS_API_SECRET=your-atlantis-api-secret
    volumes:
      - ./atlantis-config:/etc/atlantis
      - ./terraform:/terraform
    networks:
      - app-network
```

### Network Configuration

Ensure both the web application and Atlantis are on the same network:

```yaml
networks:
  app-network:
    driver: bridge
```

## Required Files

### Atlantis Configuration Directory

Create a directory for Atlantis configuration:

```
mkdir -p atlantis-config
```

### Repository Configuration File

Create a `repo-config.yaml` file in the `atlantis-config` directory:

```yaml
# atlantis-config/repo-config.yaml
repos:
  - id: /.*/
    apply_requirements: [approved]
    workflow: custom
    allowed_overrides: [workflow]
    allow_custom_workflows: true

workflows:
  custom:
    plan:
      steps:
        - init
        - plan:
            extra_args: ["-var-file=terraform.tfvars"]
    apply:
      steps:
        - apply
```

## Web Application Integration

### Environment Variables

Update the web application's environment variables in `docker-compose.yml`:

```yaml
services:
  web:
    # Existing configuration...
    environment:
      # Existing variables...
      - ATLANTIS_URL=http://atlantis:4141
      - ATLANTIS_TOKEN=your-atlantis-api-secret
```

### API Communication

The web application communicates with Atlantis through its API:

1. **Plan Operation**:
   ```
   POST http://atlantis:4141/api/plan
   ```

2. **Apply Operation**:
   ```
   POST http://atlantis:4141/api/apply
   ```

## Terraform File Generation

The web application needs to generate Terraform files in a format compatible with Atlantis:

1. **Directory Structure**:
   ```
   terraform/
   ├── <request_id>_<timestamp>/
   │   ├── machine.tf
   │   └── terraform.tfvars
   ```

2. **File Format**:
   - `machine.tf`: Contains the VM resource definitions
   - `terraform.tfvars`: Contains the variable values

## Security Considerations

1. **API Secret**: The `ATLANTIS_API_SECRET` should be a strong, randomly generated value.

2. **Network Isolation**: The Atlantis container should only be accessible from the web application, not exposed to the internet.

3. **Volume Permissions**: Ensure proper permissions on shared volumes.

## Operational Workflow

1. **Web Application Flow**:
   - User submits VM configuration
   - Application generates Terraform files
   - Application calls Atlantis API to run plan
   - Admin approves plan
   - Application calls Atlantis API to apply plan

2. **Monitoring**:
   - Atlantis logs can be viewed with `docker-compose logs atlantis`
   - Plan and apply status can be checked through the Atlantis API

## Troubleshooting

1. **API Connection Issues**:
   - Ensure both containers are on the same network
   - Verify the ATLANTIS_URL is correct
   - Check the ATLANTIS_API_SECRET matches

2. **Terraform Execution Errors**:
   - Check Atlantis logs for Terraform errors
   - Verify the generated Terraform files are valid
   - Ensure all required variables are provided

3. **Permission Issues**:
   - Check volume mount permissions
   - Ensure Atlantis has access to the Terraform files
