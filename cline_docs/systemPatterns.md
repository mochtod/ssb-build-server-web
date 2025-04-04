# System Patterns: SSB Build Server Web

## Architecture Overview

The SSB Build Server Web application follows a layered architecture pattern with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                      Web Application                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Presentation│  │  Business   │  │      Data           │  │
│  │    Layer    │◄─┤    Logic    │◄─┤     Access          │  │
│  │  (Flask UI) │  │    Layer    │  │     Layer           │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└───────────┬─────────────────────────────────────┬───────────┘
            │                                     │
            ▼                                     ▼
┌───────────────────────┐             ┌─────────────────────────┐
│    File System        │             │     External Systems     │
│  ┌─────────────────┐  │             │  ┌──────────────────┐   │
│  │ Configuration   │  │             │  │     Atlantis     │   │
│  │     Files       │  │             │  │    (Terraform)   │   │
│  └─────────────────┘  │             │  └──────────────────┘   │
│  ┌─────────────────┐  │             │  ┌──────────────────┐   │
│  │   Terraform     │  │             │  │     VMware       │   │
│  │     Files       │  │             │  │     vSphere      │   │
│  └─────────────────┘  │             │  └──────────────────┘   │
└───────────────────────┘             └─────────────────────────┘
```

## Key Technical Decisions

### 1. Flask Web Framework
- **Decision**: Use Flask as the web framework
- **Rationale**: Lightweight, flexible, and well-suited for small to medium applications
- **Implementation**: The application is built around Flask routes and templates

### 2. File-Based Storage
- **Decision**: Use JSON files for configuration storage instead of a database
- **Rationale**: Simplifies deployment and aligns with Terraform's file-based approach
- **Implementation**: Configurations are stored in the `configs/` directory as JSON files

### 3. Terraform for Infrastructure as Code
- **Decision**: Use Terraform to define VM infrastructure
- **Rationale**: Industry standard for infrastructure as code with strong VMware support
- **Implementation**: Generate Terraform files based on user inputs

### 4. Atlantis for Terraform Workflow
- **Decision**: Use Atlantis to manage Terraform workflows
- **Rationale**: Provides plan/apply capabilities with approval workflows
- **Implementation**: Communicate with Atlantis API for plan and apply operations

### 5. Docker Containerization
- **Decision**: Package the application as a Docker container
- **Rationale**: Ensures consistent deployment across environments
- **Implementation**: Dockerfile and docker-compose.yml for building and running the application

### 6. Role-Based Access Control
- **Decision**: Implement simple role-based access control
- **Rationale**: Different users need different permissions (admin vs. builder)
- **Implementation**: User roles stored in users.json with role-checking decorators

## Design Patterns

### 1. Model-View-Controller (MVC)
- **Model**: JSON configuration files and Terraform files
- **View**: Jinja2 templates in the templates/ directory
- **Controller**: Flask routes in app.py

### 2. Decorator Pattern
- Used for authentication and role-based access control
- Implemented with Flask's `@wraps` decorator

### 3. Factory Pattern
- Used for generating Terraform configurations based on user inputs
- The `generate_terraform_config()` function acts as a factory for Terraform files

### 4. Template Method Pattern
- Used in the HTML templates with Jinja2 inheritance
- Base templates define the structure, child templates provide specific implementations

### 5. Facade Pattern
- The application acts as a facade over complex Terraform and VMware operations
- Simplifies VM provisioning for end users

## Code Organization

### Main Application Structure
```
ssb-build-server-web-1/
├── app.py                 # Main application file with Flask routes
├── docker-compose.yml     # Docker Compose configuration
├── Dockerfile             # Docker build instructions
├── requirements.txt       # Python dependencies
├── users.json             # User authentication data
├── configs/               # VM configuration storage
├── terraform/             # Generated Terraform files
├── static/                # Static assets (CSS, JS)
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── script.js
└── templates/             # HTML templates
    ├── admin_users.html
    ├── build_receipt.html
    ├── config.html
    ├── configs.html
    ├── index.html
    ├── login.html
    └── plan.html
```

### VM Workspace Structure
```
rhel9-vm-workspace/
├── atlantis.cfg           # Atlantis configuration
├── backend.tf             # Terraform backend configuration
├── data.tf                # Data sources and local variables
├── fetch_next_ip.py       # IP address allocation script
├── machine_inputs.tfvars  # Example VM input variables
├── machine.tf             # VM resource definitions
├── providers.tf           # Provider configurations
├── README.md              # Documentation
└── tfvars.tf              # Variable definitions
```

## Data Flow

### VM Creation Workflow
1. User submits VM configuration through web form
2. Application validates inputs and generates a unique request ID
3. Configuration is saved as a JSON file in the configs/ directory
4. Terraform files are generated in the terraform/ directory
5. User initiates a Terraform plan through Atlantis
6. Administrator approves the plan
7. User applies the approved plan to create the VM
8. Build receipt is generated and displayed to the user

### Authentication Flow
1. User submits login credentials
2. Application checks credentials against users.json
3. If valid, user session is created with role information
4. Role-based access control restricts actions based on user role

## Error Handling

1. **Form Validation**: Client-side and server-side validation for user inputs
2. **Flash Messages**: Used to display success and error messages to users
3. **Try-Except Blocks**: Used around critical operations to catch and handle exceptions
4. **Status Tracking**: VM configurations track status (pending, planning, completed, failed)

## Integration Patterns

### Atlantis Integration
- **API-Based**: Uses HTTP requests to communicate with Atlantis API
- **Asynchronous**: Plans and applies are initiated and then polled for completion
- **Containerized Setup**: Atlantis can be run in a Docker container without GitHub integration
  - Direct API calls to Atlantis server
  - Local Terraform execution without Git repository
  - Configuration through environment variables and config files

### VMware Integration
- **Indirect**: Terraform communicates with VMware vSphere
- **Provider-Based**: Uses the Terraform vSphere provider

### NetBox Integration
- **Script-Based**: Uses the fetch_next_ip.py script to allocate IP addresses
- **API-Based**: Script communicates with NetBox API

## Improvement Opportunities

1. **Terraform Module Generation**: Fix the issue with generating proper Terraform module files
2. **Database Storage**: Replace file-based storage with a database for better scalability
3. **Secure Authentication**: Implement proper password hashing and secure authentication
4. **API Documentation**: Create OpenAPI/Swagger documentation for the API endpoints
5. **Automated Testing**: Implement unit and integration tests
6. **CI/CD Pipeline**: Set up continuous integration and deployment
