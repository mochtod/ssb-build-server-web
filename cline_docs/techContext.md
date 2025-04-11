# Technical Context: SSB Build Server Web

## Technologies Used

### Web Application
- **Python 3.11**: Core programming language
- **Flask 2.3.3**: Web framework for the application
- **Werkzeug 2.3.7**: WSGI utility library for Flask
- **Gunicorn 21.2.0**: WSGI HTTP server for running the Flask application
- **Jinja2**: Template engine (included with Flask)
- **bcrypt 4.0.1**: Password hashing library for user authentication

### Infrastructure Automation
- **Terraform**: Infrastructure as Code (IaC) tool for provisioning VMs
- **Atlantis**: Terraform workflow automation tool
- **GitPython 3.1.37**: Git integration for version control
- **Requests 2.31.0**: HTTP library for API communication

### Containerization
- **Docker**: Container platform for application deployment
- **Docker Compose**: Multi-container Docker application orchestration

### Frontend
- **HTML/CSS/JavaScript**: Standard web technologies for the user interface
- **Custom CSS**: Styling for the application interface

### Data Storage
- **JSON Files**: Used for storing configuration data and user information

### External Systems
- **VMware vSphere**: Virtualization platform where VMs are provisioned
- **NetBox**: IP address management system
- **Vault**: Secret management for credentials (referenced in the VM workspace)

## Development Setup

### Local Development Environment
1. **Clone the Repository**:
   ```
   git clone <repository-url>
   cd ssb-build-server-web-1
   ```

2. **Install Dependencies**:
   ```
   pip install -r requirements.txt
   ```

3. **Environment Variables**:
   - `FLASK_SECRET_KEY`: Secret key for Flask sessions
   - `CONFIG_DIR`: Directory for storing configuration files
   - `TERRAFORM_DIR`: Directory for storing Terraform files
   - `USERS_FILE`: Path to the users.json file
   - `ATLANTIS_URL`: URL for the Atlantis server
   - `ATLANTIS_TOKEN`: Authentication token for Atlantis API

4. **Run the Application**:
   ```
   flask run
   ```

### Docker Deployment
1. **Build and Run with Docker Compose**:
   ```
   docker-compose up -d
   ```

2. **Access the Application**:
   - The application will be available at http://localhost:5150

## Technical Constraints

### Security Considerations
1. **Authentication**: Username/password authentication is implemented using bcrypt password hashing for secure storage of credentials in the users.json file.

2. **Role-Based Access Control**: Two roles are defined:
   - `admin`: Can approve/reject VM configurations and manage users
   - `builder`: Can create VM configurations and build approved VMs

3. **Environment Separation**: The application distinguishes between production and non-production environments, with different server prefixes.

### Integration Points
1. **Atlantis API**: The application communicates with Atlantis for Terraform plan and apply operations.
   - For containerized setup without GitHub:
     - Atlantis can be run in a Docker container alongside the web application
     - Direct API calls to Atlantis server without Git repository integration
     - Configuration through environment variables and config files
     - All Terraform execution occurs within the Atlantis container with fallback mechanisms for API issues

2. **NetBox API**: Used indirectly through the fetch_next_ip.py script to allocate IP addresses.

3. **VMware vSphere**: Terraform communicates with vSphere to provision VMs.

4. **Vault**: Used for storing sensitive credentials (referenced in the VM workspace).

### File System Structure
1. **Configuration Storage**:
   - `configs/`: Stores JSON configuration files for VM requests
   - `terraform/`: Stores generated Terraform files

2. **Web Application**:
   - `static/`: Static assets (CSS, JavaScript)
   - `templates/`: HTML templates
   - `app.py`: Main application file

### VM Workspace Structure
The VM workspace (rhel9-vm-workspace) contains the Terraform configurations that define how VMs are provisioned:

1. **Core Files**:
   - `machine.tf`: Defines the VM resources and module
   - `providers.tf`: Configures the vSphere and Vault providers
   - `data.tf`: Defines data sources and local variables
   - `backend.tf`: Configures the Atlantis backend
   - `tfvars.tf`: Defines input variables

2. **Supporting Files**:
   - `fetch_next_ip.py`: Python script for IP address allocation
   - `machine_inputs.tfvars`: Example input variables for VM creation

## Known Technical Limitations

1. **NetBox Integration**: IP address allocation through NetBox is not yet fully implemented.

2. **CI/CD Pipeline**: No automated testing or deployment pipeline is configured.

3. **Error Handling**: Limited error handling for API communication failures.

4. **Scalability**: The application uses file-based storage, which may not scale well for large numbers of configurations.

5. **Testing**: No automated tests are currently implemented.
