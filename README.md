# SSB Build Server Web

A web interface for the SSB Build Server. This application allows users to configure and build RHEL9 virtual machines through a user-friendly web interface, with Terraform and Atlantis handling the infrastructure provisioning.

## Project Structure

The repository contains both the web application and the VM workspace components:

```
ssb-build-server-web-1/
├── app.py                 # Main Flask application
├── docker-compose.yml     # Docker Compose configuration
├── Dockerfile             # Docker build instructions for web app
├── requirements.txt       # Python dependencies
├── users.json             # User authentication data
├── configs/               # VM configuration storage
├── terraform/             # Generated Terraform files
├── static/                # Static assets (CSS, JS)
├── templates/             # HTML templates
├── atlantis-config/       # Atlantis configuration files
└── vm-workspace/          # VM workspace Terraform files
```

## Components

### Web Application

The web application provides a user interface for:
- Creating VM configurations
- Reviewing and approving configurations
- Initiating Terraform plans
- Building approved VMs

### Atlantis Server

The Atlantis server handles Terraform workflows:
- Running Terraform plans
- Applying approved plans
- Providing plan and apply logs

### VM Workspace

The VM workspace contains the Terraform configurations for VM provisioning:
- Machine definitions
- Provider configurations
- Data sources
- Variable definitions

## Setup and Deployment

### Prerequisites

- Docker and Docker Compose
- Access to VMware vSphere environment
- NetBox for IP address allocation (optional)

### Configuration

1. **Environment Variables**:
   - Update the environment variables in `docker-compose.yml`
   - Set the `ATLANTIS_TOKEN` to a secure value
   - Configure VMware vSphere credentials

2. **VM Workspace**:
   - Update the VM workspace files in `vm-workspace/` as needed
   - Configure the vSphere provider settings

### Deployment

Run the following command to start the application:

```bash
docker-compose up -d
```

This will start both the web application and the Atlantis server.

### Access

- Web Application: http://localhost:5150
- Atlantis Server: http://localhost:4141

## Usage

1. **Login**:
   - Use the default admin credentials (admin/admin123)
   - Change the password in production

2. **Create VM Configuration**:
   - Fill out the VM configuration form
   - Submit the configuration

3. **Plan**:
   - Initiate a Terraform plan
   - Review the plan output

4. **Approve**:
   - Admin users can approve or reject plans

5. **Build**:
   - Build approved configurations
   - Monitor the build progress

## Development

### Local Development

1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd ssb-build-server-web-1
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Application**:
   ```bash
   flask run
   ```

### Docker Development

1. **Build and Run with Docker Compose**:
   ```bash
   docker-compose up --build
   ```

## Security Considerations

- Change default passwords in production
- Use secure values for all tokens and secrets
- Implement proper access controls
