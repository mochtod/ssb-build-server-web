# Atlantis Containerized Setup

## Overview

This document outlines how to set up Atlantis in a containerized environment with GitHub integration for the SSB Build Server Web application. This setup allows Terraform operations to be executed through the Atlantis API with GitHub repository integration.

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
      - ATLANTIS_API_SECRET=${ATLANTIS_TOKEN:-your-atlantis-api-secret}
      - ATLANTIS_GH_USER=${GITHUB_USER:-your-github-username}
      - ATLANTIS_GH_TOKEN=${GITHUB_TOKEN:-your-github-personal-access-token}
    command: ["server", "--disable-repo-locking", "--repo-config=/etc/atlantis/repo-config.yaml", "--atlantis-url=http://atlantis:4141", "--gh-user=${GITHUB_USER}", "--gh-token=${GITHUB_TOKEN}"]
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

## GitHub Integration

### GitHub Credentials

Atlantis requires GitHub credentials to function properly. The current setup supports real GitHub integration through environment variables:

```
# GitHub integration for Atlantis
GITHUB_USER=your-github-username
GITHUB_TOKEN=your-github-personal-access-token
GH_WEBHOOK_SECRET=your-webhook-secret
```

In the docker-compose.yml file, these variables are referenced:

```yaml
environment:
  # GitHub repository configuration
  - ATLANTIS_REPO_ALLOWLIST=github.com/${GITHUB_USER:-your-username}/*
  # GitHub authentication
  - ATLANTIS_GH_USER=${GITHUB_USER:-your-github-username}
  - ATLANTIS_GH_TOKEN=${GITHUB_TOKEN:-your-github-personal-access-token}
  # GitHub webhook configuration
  - ATLANTIS_GH_WEBHOOK_SECRET=${GH_WEBHOOK_SECRET:-your-webhook-secret}
```

GitHub credentials require the following permissions:
- `repo` scope (full control of private repositories)
- If you're using GitHub organizations, it will also need the `read:org` scope

For detailed instructions on:
1. Creating a Personal Access Token (PAT): See `github-pat-setup.md`
2. Setting up webhooks: See `github-webhook-setup.md`

### Repository Configuration

Ensure that the `ATLANTIS_REPO_ALLOWLIST` environment variable includes the repositories you want Atlantis to work with. You can use wildcards, for example:
- `github.com/myorg/*` - All repositories in the myorg organization
- `github.com/myuser/myrepo` - A specific repository

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

2. **GitHub Token**: The GitHub token should have the minimum required permissions and be kept secure. Never commit the token to version control.

3. **Network Isolation**: The Atlantis container should only be accessible from the web application, not exposed to the internet.

4. **Volume Permissions**: Ensure proper permissions on shared volumes.

5. **Environment Variables**: Store sensitive credentials in the `.env` file which should be excluded from version control via `.gitignore`.

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

2. **GitHub Authentication Issues**:
   - Verify the GitHub username and token are correct
   - Check that the token has the required permissions
   - Ensure the token has not expired
   - Verify the repository is included in the ATLANTIS_REPO_ALLOWLIST

3. **Terraform Execution Errors**:
   - Check Atlantis logs for Terraform errors
   - Verify the generated Terraform files are valid
   - Ensure all required variables are provided

4. **Permission Issues**:
   - Check volume mount permissions
   - Ensure Atlantis has access to the Terraform files
   - Verify GitHub token has appropriate repository access
