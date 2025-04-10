from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
import os
import json
import uuid
import datetime
import subprocess
import requests
import shutil
import tempfile
import re
import bcrypt
from werkzeug.utils import secure_filename
from functools import wraps
from git import Repo
from git.exc import GitCommandError
import logging

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_key_for_development_only')

# Configuration paths
CONFIG_DIR = os.environ.get('CONFIG_DIR', 'configs')
TERRAFORM_DIR = os.environ.get('TERRAFORM_DIR', 'terraform')
USERS_FILE = os.environ.get('USERS_FILE', 'users.json')
GIT_REPO_URL = os.environ.get('GIT_REPO_URL', 'https://github.com/your-org/terraform-repo.git')
GIT_USERNAME = os.environ.get('GIT_USERNAME', '')
GIT_TOKEN = os.environ.get('GIT_TOKEN', '')
ATLANTIS_URL = os.environ.get('ATLANTIS_URL', 'https://atlantis.chrobinson.com')
ATLANTIS_TOKEN = os.environ.get('ATLANTIS_TOKEN', '')

# Ensure directories exist
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(TERRAFORM_DIR, exist_ok=True)

# Server location prefix options
SERVER_PREFIXES = {
    # Non-production environments
    'lin2dv2': 'Development',
    'lin2int2': 'Integration',
    'lin2trn2': 'Training',
    # Production environments
    'lin2pr2': 'Production'
}

# Environments categorization
ENVIRONMENTS = {
    "nonprod": ["lin2dv2", "lin2int2", "lin2trn2"],
    "prod": ["lin2pr2"]
}

# Default values for VM configuration
DEFAULT_CONFIG = {
    'num_cpus': 2,
    'memory': 4096,
    'disk_size': 50,
    'additional_disks': []
}

# User roles
ROLE_ADMIN = 'admin'
ROLE_BUILDER = 'builder'

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure USERS_FILE is a valid file path
logger.info(f"Checking USERS_FILE path: {USERS_FILE}")
if not os.path.exists(USERS_FILE):
    if os.path.isdir(USERS_FILE):
        logger.error(f"The USERS_FILE path '{USERS_FILE}' is a directory, not a file.")
        raise IsADirectoryError(f"The USERS_FILE path '{USERS_FILE}' is a directory, not a file. Please check the configuration.")
    else:
        logger.info(f"USERS_FILE does not exist. Creating default users file at: {USERS_FILE}")
        default_users = {
            "admin": {
                "password": "admin123",  # Change this in production
                "role": ROLE_ADMIN,
                "name": "Admin User"
            },
            "builder": {
                "password": "builder123",  # Change this in production
                "role": ROLE_BUILDER,
                "name": "Builder User"
            }
        }
        with open(USERS_FILE, 'w') as f:
            json.dump(default_users, f, indent=2)
        logger.info(f"Default users file created successfully at: {USERS_FILE}")

# Update the load_users function to handle the case where USERS_FILE is a directory or missing

def load_users():
    if not os.path.isfile(USERS_FILE):
        raise FileNotFoundError(f"The USERS_FILE path '{USERS_FILE}' is not a valid file. Please check the configuration.")
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Role-based access control decorator
def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                flash('Please log in to access this page', 'error')
                return redirect(url_for('login', next=request.url))
            
            if 'role' not in session or session['role'] != role:
                flash(f'You need {role} privileges to access this page', 'error')
                return redirect(url_for('index'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        users = load_users()
        
        if username in users and users[username]['password'] == password:
            session['username'] = username
            session['role'] = users[username]['role']
            session['name'] = users[username]['name']
            
            flash(f'Welcome, {users[username]["name"]}!', 'success')
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        
        flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', 
                          server_prefixes=SERVER_PREFIXES,
                          environments=ENVIRONMENTS,
                          user_role=session.get('role', ''),
                          user_name=session.get('name', ''))

@app.route('/submit', methods=['POST'])
@login_required
def submit():
    try:
        # Get form data
        server_prefix = request.form.get('server_prefix')
        app_name = request.form.get('app_name')
        quantity = int(request.form.get('quantity', 1))
        num_cpus = int(request.form.get('num_cpus', DEFAULT_CONFIG['num_cpus']))
        memory = int(request.form.get('memory', DEFAULT_CONFIG['memory']))
        disk_size = int(request.form.get('disk_size', DEFAULT_CONFIG['disk_size']))
        
        # Determine environment based on server prefix
        environment = "production" if server_prefix in ENVIRONMENTS["prod"] else "development"
        
        # Validate input
        if not server_prefix or not app_name:
            flash('Server prefix and app name are required', 'error')
            return redirect(url_for('index'))
        
        if not 3 <= len(app_name) <= 5:
            flash('App name must be 3-5 characters', 'error')
            return redirect(url_for('index'))
            
        if server_prefix not in SERVER_PREFIXES:
            flash('Invalid server prefix', 'error')
            return redirect(url_for('index'))
        
        # Additional disks processing
        additional_disks = []
        for i in range(3):  # Support up to 3 additional disks
            disk_size_key = f'additional_disk_size_{i}'
            disk_type_key = f'additional_disk_type_{i}'
            if disk_size_key in request.form and request.form[disk_size_key]:
                additional_disks.append({
                    'size': int(request.form[disk_size_key]),
                    'type': request.form.get(disk_type_key, 'thin')
                })
        
        # Generate unique ID for this request
        request_id = str(uuid.uuid4())[:8]
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        
        # Construct server base name
        server_name = f"{server_prefix}-{app_name}"
        
        # Prepare configuration data
        config_data = {
            'request_id': request_id,
            'timestamp': timestamp,
            'server_name': server_name,
            'server_prefix': server_prefix,
            'app_name': app_name,
            'quantity': quantity,
            'num_cpus': num_cpus,
            'memory': memory,
            'disk_size': disk_size,
            'additional_disks': additional_disks,
            'environment': environment,
            'start_number': 10001,  # Starting number as per requirements
            'build_status': 'pending',
            'plan_status': 'pending',
            'approval_status': 'pending',
            'pr_url': '',
            'atlantis_url': '',
            'plan_log': '',
            'build_owner': session.get('name', 'unknown'),
            'build_username': session.get('username', 'unknown'),
            'created_at': datetime.datetime.now().isoformat()
        }
        
        # Save configuration to JSON file
        config_file = os.path.join(CONFIG_DIR, f"{request_id}_{timestamp}.json")
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        # Generate Terraform configuration
        tf_config = generate_terraform_config(config_data)
        
        # Save Terraform configuration
        tf_directory = os.path.join(TERRAFORM_DIR, f"{request_id}_{timestamp}")
        os.makedirs(tf_directory, exist_ok=True)
        
        machine_tf_file = os.path.join(tf_directory, "machine.tf")
        with open(machine_tf_file, 'w') as f:
            f.write(tf_config)
        
        # Create variables.tfvars file
        variables_file = os.path.join(tf_directory, "terraform.tfvars")
        generate_variables_file(variables_file, config_data)
        
        flash('VM configuration created successfully!', 'success')
        return redirect(url_for('show_config', request_id=request_id, timestamp=timestamp))
        
    except Exception as e:
        flash(f'Error creating configuration: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/config/<request_id>_<timestamp>')
@login_required
def show_config(request_id, timestamp):
    try:
        # Load configuration
        config_file = os.path.join(CONFIG_DIR, f"{request_id}_{timestamp}.json")
        with open(config_file, 'r') as f:
            config_data = json.load(f)
            
        # Get path to Terraform files
        tf_directory = os.path.join(TERRAFORM_DIR, f"{request_id}_{timestamp}")
        machine_tf_file = os.path.join(tf_directory, "machine.tf")
        
        with open(machine_tf_file, 'r') as f:
            machine_tf = f.read()
            
        # Determine if the current user is the owner of this config
        is_owner = session.get('username') == config_data.get('build_username')
        
        return render_template(
            'config.html', 
            config=config_data, 
            machine_tf=machine_tf,
            request_id=request_id,
            timestamp=timestamp,
            user_role=session.get('role', ''),
            is_owner=is_owner
        )
    except Exception as e:
        flash(f'Error loading configuration: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/download/<request_id>_<timestamp>')
@login_required
def download_config(request_id, timestamp):
    try:
        tf_directory = os.path.join(TERRAFORM_DIR, f"{request_id}_{timestamp}")
        machine_tf_file = os.path.join(tf_directory, "machine.tf")
        
        # This would typically send the file for download
        # For simplicity, we'll just display it
        with open(machine_tf_file, 'r') as f:
            content = f.read()
            
        return jsonify({
            'status': 'success',
            'filename': f"{request_id}_{timestamp}_machine.tf",
            'content': content
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

@app.route('/configs')
@login_required
def list_configs():
    configs = []
    for filename in os.listdir(CONFIG_DIR):
        if filename.endswith('.json'):
            with open(os.path.join(CONFIG_DIR, filename), 'r') as f:
                config = json.load(f)
                configs.append({
                    'request_id': config.get('request_id', 'unknown'),
                    'timestamp': config.get('timestamp', 'unknown'),
                    'server_name': config.get('server_name', 'unknown'),
                    'quantity': config.get('quantity', 0),
                    'build_status': config.get('build_status', 'pending'),
                    'plan_status': config.get('plan_status', 'pending'),
                    'approval_status': config.get('approval_status', 'pending'),
                    'build_owner': config.get('build_owner', 'unknown'),
                    'build_username': config.get('build_username', 'unknown'),
                    'environment': config.get('environment', 'development'),
                    'filename': filename
                })
    
    # Sort configs by timestamp (newest first)
    configs.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Filter configs based on user role
    user_role = session.get('role', '')
    username = session.get('username', '')
    
    # If admin, show all configs
    # If builder, only show their configs or approved configs
    if user_role != ROLE_ADMIN:
        configs = [c for c in configs if c['build_username'] == username]
    
    return render_template('configs.html', 
                          configs=configs, 
                          user_role=user_role)

@app.route('/plan/<request_id>_<timestamp>', methods=['POST'])
@login_required
def plan_config(request_id, timestamp):
    try:
        # Load configuration
        config_file = os.path.join(CONFIG_DIR, f"{request_id}_{timestamp}.json")
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        # Check if user is owner or admin
        if session.get('username') != config_data.get('build_username') and session.get('role') != ROLE_ADMIN:
            flash('You do not have permission to plan this configuration', 'error')
            return redirect(url_for('show_config', request_id=request_id, timestamp=timestamp))
        
        # Get path to Terraform files
        tf_directory = os.path.join(TERRAFORM_DIR, f"{request_id}_{timestamp}")
        
        # Update plan status
        config_data['plan_status'] = 'planning'
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        # Call Atlantis API to run plan
        plan_result = run_atlantis_plan(config_data, tf_directory)
        
        if plan_result and plan_result.get('status') == 'success':
            # Update config with plan info
            config_data['plan_status'] = 'completed'
            config_data['atlantis_url'] = plan_result.get('atlantis_url', '')
            config_data['plan_log'] = plan_result.get('plan_log', '')
            config_data['plan_id'] = plan_result.get('plan_id', '')
            
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            flash('Terraform plan completed successfully!', 'success')
            return redirect(url_for('show_plan', request_id=request_id, timestamp=timestamp))
        else:
            # Update config with failure
            config_data['plan_status'] = 'failed'
            error_message = plan_result.get('message', 'Unknown error occurred') if plan_result else 'Plan process failed'
            config_data['plan_error'] = error_message
            
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            flash(f'Plan failed: {error_message}', 'error')
            return redirect(url_for('show_config', request_id=request_id, timestamp=timestamp))
        
    except Exception as e:
        flash(f'Error running Terraform plan: {str(e)}', 'error')
        return redirect(url_for('show_config', request_id=request_id, timestamp=timestamp))

@app.route('/show_plan/<request_id>_<timestamp>')
@login_required
def show_plan(request_id, timestamp):
    try:
        # Load configuration
        config_file = os.path.join(CONFIG_DIR, f"{request_id}_{timestamp}.json")
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        # Determine if the current user is the owner of this config
        is_owner = session.get('username') == config_data.get('build_username')
        
        return render_template(
            'plan.html',
            config=config_data,
            request_id=request_id,
            timestamp=timestamp,
            user_role=session.get('role', ''),
            is_owner=is_owner
        )
    except Exception as e:
        flash(f'Error loading plan: {str(e)}', 'error')
        return redirect(url_for('configs'))

@app.route('/approve/<request_id>_<timestamp>', methods=['POST'])
@role_required(ROLE_ADMIN)
def approve_config(request_id, timestamp):
    try:
        # Load configuration
        config_file = os.path.join(CONFIG_DIR, f"{request_id}_{timestamp}.json")
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        # Check if plan is completed
        if config_data.get('plan_status') != 'completed':
            flash('Cannot approve: Terraform plan has not been completed', 'error')
            return redirect(url_for('show_plan', request_id=request_id, timestamp=timestamp))
        
        # Update approval status
        config_data['approval_status'] = 'approved'
        config_data['approved_by'] = session.get('name', 'Unknown Admin')
        config_data['approved_at'] = datetime.datetime.now().isoformat()
        config_data['approval_notes'] = request.form.get('approval_notes', '')
        
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        flash('Configuration has been approved for build', 'success')
        return redirect(url_for('show_plan', request_id=request_id, timestamp=timestamp))
    
    except Exception as e:
        flash(f'Error approving configuration: {str(e)}', 'error')
        return redirect(url_for('show_plan', request_id=request_id, timestamp=timestamp))

@app.route('/reject/<request_id>_<timestamp>', methods=['POST'])
@role_required(ROLE_ADMIN)
def reject_config(request_id, timestamp):
    try:
        # Load configuration
        config_file = os.path.join(CONFIG_DIR, f"{request_id}_{timestamp}.json")
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        # Update approval status
        config_data['approval_status'] = 'rejected'
        config_data['rejected_by'] = session.get('name', 'Unknown Admin')
        config_data['rejected_at'] = datetime.datetime.now().isoformat()
        config_data['rejection_reason'] = request.form.get('rejection_reason', '')
        
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        flash('Configuration has been rejected', 'warning')
        return redirect(url_for('show_plan', request_id=request_id, timestamp=timestamp))
    
    except Exception as e:
        flash(f'Error rejecting configuration: {str(e)}', 'error')
        return redirect(url_for('show_plan', request_id=request_id, timestamp=timestamp))

@app.route('/build/<request_id>_<timestamp>', methods=['POST'])
@login_required
def build_config(request_id, timestamp):
    try:
        # Load configuration
        config_file = os.path.join(CONFIG_DIR, f"{request_id}_{timestamp}.json")
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        # Check if user is owner
        if session.get('username') != config_data.get('build_username'):
            flash('Only the creator can build this configuration', 'error')
            return redirect(url_for('show_plan', request_id=request_id, timestamp=timestamp))
        
        # Check if plan is approved
        if config_data.get('approval_status') != 'approved':
            flash('Cannot build: Configuration has not been approved by an administrator', 'error')
            return redirect(url_for('show_plan', request_id=request_id, timestamp=timestamp))
        
        # Update build status
        config_data['build_status'] = 'building'
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        # Get path to Terraform files
        tf_directory = os.path.join(TERRAFORM_DIR, f"{request_id}_{timestamp}")
        
        # Call Atlantis API to apply plan
        build_result = apply_atlantis_plan(config_data, tf_directory)
        
        if build_result and build_result.get('status') == 'success':
            # Update config with build info
            config_data['build_status'] = 'submitted'
            config_data['build_url'] = build_result.get('build_url', '')
            config_data['build_receipt'] = build_result.get('build_receipt', '')
            config_data['build_completed_at'] = datetime.datetime.now().isoformat()
            
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            flash('Build successfully initiated!', 'success')
            return redirect(url_for('show_build_receipt', request_id=request_id, timestamp=timestamp))
        else:
            # Update config with failure
            config_data['build_status'] = 'failed'
            error_message = build_result.get('message', 'Unknown error occurred') if build_result else 'Build process failed'
            config_data['build_error'] = error_message
            
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            flash(f'Build failed: {error_message}', 'error')
            return redirect(url_for('show_plan', request_id=request_id, timestamp=timestamp))
        
    except Exception as e:
        flash(f'Error initiating build: {str(e)}', 'error')
        return redirect(url_for('show_plan', request_id=request_id, timestamp=timestamp))

@app.route('/build_receipt/<request_id>_<timestamp>')
@login_required
def show_build_receipt(request_id, timestamp):
    try:
        # Load configuration
        config_file = os.path.join(CONFIG_DIR, f"{request_id}_{timestamp}.json")
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        return render_template(
            'build_receipt.html',
            config=config_data,
            request_id=request_id,
            timestamp=timestamp,
            user_role=session.get('role', '')
        )
    except Exception as e:
        flash(f'Error loading build receipt: {str(e)}', 'error')
        return redirect(url_for('configs'))

@app.route('/admin/users')
@role_required(ROLE_ADMIN)
def admin_users():
    users = load_users()
    return render_template('admin_users.html', users=users)

@app.route('/admin/add_user', methods=['POST'])
@role_required(ROLE_ADMIN)
def add_user():
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    name = request.form.get('name')
    
    if not username or not password or not role or not name:
        flash('All fields are required', 'error')
        return redirect(url_for('admin_users'))
    
    users = load_users()
    
    if username in users:
        flash('Username already exists', 'error')
        return redirect(url_for('admin_users'))
    
    users[username] = {
        'password': password,
        'role': role,
        'name': name
    }
    
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)
    
    flash(f'User {username} added successfully', 'success')
    return redirect(url_for('admin_users'))

def run_atlantis_plan(config_data, tf_directory):
    """Run a Terraform plan in Atlantis"""
    try:
        # Read the Terraform files
        machine_tf_file = os.path.join(tf_directory, "machine.tf")
        variables_file = os.path.join(tf_directory, "terraform.tfvars")
        
        with open(machine_tf_file, 'r') as f:
            machine_tf_content = f.read()
        
        with open(variables_file, 'r') as f:
            variables_content = f.read()
        
        # Prepare the Atlantis payload for containerized setup without GitHub
        atlantis_payload = {
            'workspace': config_data['environment'],
            'terraform_files': {
                'machine.tf': machine_tf_content,
                'terraform.tfvars': variables_content
            },
            'plan_only': True,  # Only run plan, don't apply
            'comment': f"VM Provisioning Plan: {config_data['server_name']}",
            'user': config_data['build_owner'],
            'verbose': True
        }
        
        # Call Atlantis API to plan
        headers = {
            'Content-Type': 'application/json',
            'X-Atlantis-Token': ATLANTIS_TOKEN
        }
        
        response = requests.post(f"{ATLANTIS_URL}/api/plan", json=atlantis_payload, headers=headers)
        
        if response.status_code != 200:
            return {
                'status': 'error',
                'message': f"Failed to trigger Atlantis plan: {response.text}"
            }
        
        plan_response = response.json()
        plan_id = plan_response.get('plan_id')
        
        # Wait for plan to complete and fetch the results
        plan_url = f"{ATLANTIS_URL}/plan/{plan_id}"
        
        # In a real system, you'd poll for plan completion
        # For simplicity, we'll just return the plan ID here
        
        # Generate plan log
        plan_log = f"""
Terraform Plan Output:
----------------------
Plan ID: {plan_id}
Environment: {config_data['environment']}
Server: {config_data['server_name']}
Planned Resources:
- {config_data['quantity']} virtual machines
- {len(config_data['additional_disks'])} additional disks

This plan will:
- Create {config_data['quantity']} new VM(s)
- Configure networking and storage
- Register VMs with Ansible

Atlantis Plan URL: {plan_url}
        """
        
        return {
            'status': 'success',
            'atlantis_url': plan_url,
            'plan_log': plan_log,
            'plan_id': plan_id,
            'details': {
                'workspace': config_data['environment'],
                'resources': f"{config_data['quantity']} VMs"
            }
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'message': f"Error running Terraform plan: {str(e)}"
        }

def apply_atlantis_plan(config_data, tf_directory):
    """Apply a Terraform plan in Atlantis"""
    try:
        plan_id = config_data.get('plan_id')
        
        if not plan_id:
            return {
                'status': 'error',
                'message': 'No plan ID found in configuration'
            }
        
        # Prepare the Atlantis payload for containerized setup
        atlantis_payload = {
            'plan_id': plan_id,
            'comment': f"Applying approved VM config: {config_data['server_name']}",
            'user': config_data['build_owner'],
            'workspace': config_data['environment']
        }
        
        # Call Atlantis API to apply
        headers = {
            'Content-Type': 'application/json',
            'X-Atlantis-Token': ATLANTIS_TOKEN
        }
        
        response = requests.post(f"{ATLANTIS_URL}/api/apply", json=atlantis_payload, headers=headers)
        
        if response.status_code != 200:
            return {
                'status': 'error',
                'message': f"Failed to trigger Atlantis apply: {response.text}"
            }
        
        apply_response = response.json()
        apply_id = apply_response.get('apply_id')
        
        # Generate build receipt
        build_url = f"{ATLANTIS_URL}/apply/{apply_id}"
        text_receipt = f"""
VM BUILD RECEIPT
---------------
Request ID: {config_data['request_id']}
Server Name: {config_data['server_name']}
Quantity: {config_data['quantity']}
Apply ID: {apply_id}
Workspace: {config_data['environment']}
Approved By: {config_data.get('approved_by', 'Unknown')}

NEXT STEPS:
1. Monitor the Terraform apply at {build_url}
2. Wait for deployment to complete
3. VMs will be automatically registered with Ansible
        """
        
        return {
            'status': 'success',
            'build_url': build_url,
            'build_receipt': text_receipt,
            'details': {
                'apply_id': apply_id,
                'workspace': config_data['environment'],
                'instructions': "Your Atlantis apply has been initiated. Monitor the build progress at the URL above."
            }
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'message': f"Error applying Terraform plan: {str(e)}"
        }

def generate_variables_file(variables_file, config):
    """Generate Terraform variables file based on user input"""
    # Extract configuration values
    server_name = config['server_name']
    environment = config['environment']
    
    # Determine environment-specific values
    if environment == "production":
        resource_pool = "Production"
        network = "PROD-NETWORK"
    else:
        resource_pool = "Development"
        network = "DEV-NETWORK"
    
    # Generate variables content
    variables_content = f"""
# Terraform variables for {server_name}
# Generated on {config['timestamp']}

# VM Configuration
name             = "{server_name}"
num_cpus         = {config['num_cpus']}
memory           = {config['memory']}
disk_size        = {config['disk_size']}
quantity         = {config['quantity']}
start_number     = {config['start_number']}

# Environment Configuration
environment      = "{environment}"

# These values need to be replaced with actual values from your vSphere environment
resource_pool_id = "resource-pool-id-placeholder"
datastore_id     = "datastore-id-placeholder"
network_id       = "network-id-placeholder"
template_uuid    = "template-uuid-placeholder"
ipv4_address     = "192.168.1.100"
ipv4_netmask     = 24
ipv4_gateway     = "192.168.1.1"
dns_servers      = ["8.8.8.8", "8.8.4.4"]
time_zone        = "UTC"
"""
    
    # Write to file
    with open(variables_file, 'w') as f:
        f.write(variables_content)
    
    return variables_content

def generate_terraform_config(config):
    """Generate Terraform configuration based on user input"""
    server_name = config['server_name']
    quantity = config['quantity']
    num_cpus = config['num_cpus']
    memory = config['memory']
    disk_size = config['disk_size']
    additional_disks = config['additional_disks']
    start_number = config['start_number']
    environment = config['environment']
    
    # Format additional disks for Terraform
    additional_disks_tf = "[\n"
    for disk in additional_disks:
        additional_disks_tf += f'    {{ size = {disk["size"]}, type = "{disk["type"]}" }},\n'
    additional_disks_tf += "  ]"
    
    # Generate the Terraform configuration
    tf_config = f"""
# Generated Terraform configuration for {server_name}
# Request ID: {config['request_id']}
# Timestamp: {config['timestamp']}

variable "quantity" {{
  description = "Number of machines to create"
  type        = number
  default     = {quantity}
}}

variable "name" {{
  description = "Base name for the virtual machines"
  type        = string
  default     = "{server_name}"
}}

variable "resource_pool_id" {{
  description = "Resource pool ID"
  type        = string
}}

variable "datastore_id" {{
  description = "Datastore ID"
  type        = string
}}

variable "num_cpus" {{
  description = "Number of CPUs"
  type        = number
  default     = {num_cpus}
}}

variable "memory" {{
  description = "Memory in MB"
  type        = number
  default     = {memory}
}}

variable "guest_id" {{
  description = "Guest OS ID"
  type        = string
  default     = "rhel9_64Guest"
}}

variable "network_id" {{
  description = "Network ID"
  type        = string
}}

variable "adapter_type" {{
  description = "Network adapter type"
  type        = string
  default     = "vmxnet3"
}}

variable "disk_size" {{
  description = "Disk size in GB"
  type        = number
  default     = {disk_size}
}}

variable "template_uuid" {{
  description = "Template UUID"
  type        = string
}}

variable "ipv4_address" {{
  description = "IPv4 address"
  type        = string
}}

variable "ipv4_netmask" {{
  description = "IPv4 netmask"
  type        = number
  default     = 24
}}

variable "ipv4_gateway" {{
  description = "IPv4 gateway"
  type        = string
}}

variable "dns_servers" {{
  description = "DNS servers"
  type        = list(string)
  default     = ["8.8.8.8", "8.8.4.4"]
}}

variable "time_zone" {{
  description = "Time zone"
  type        = string
  default     = "UTC"
}}

variable "start_number" {{
  description = "Starting number for VM names"
  type        = number
  default     = {start_number}
}}

variable "additional_disks" {{
  description = "Additional disks to attach"
  type        = list(object({{
    size = number
    type = string
  }}))
  default     = {additional_disks_tf}
}}

resource "vsphere_virtual_machine" "vm" {{
  count = var.quantity

  name             = "${{var.name}}-${{var.start_number + count.index}}"
  resource_pool_id = var.resource_pool_id
  datastore_id     = var.datastore_id
  num_cpus         = var.num_cpus
  memory           = var.memory
  guest_id         = var.guest_id
  
  network_interface {{
    network_id   = var.network_id
    adapter_type = var.adapter_type
  }}
  
  disk {{
    label            = "disk0"
    size             = var.disk_size
    eagerly_scrub    = false
    thin_provisioned = true
  }}

  dynamic "disk" {{
    for_each = var.additional_disks
    content {{
      label            = "disk${{disk.key + 1}}"
      size             = disk.value.size
      eagerly_scrub    = false
      thin_provisioned = disk.value.type == "thin"
    }}
  }}

  clone {{
    template_uuid = var.template_uuid
  }}

  custom_attributes = {{
    ipv4_address = var.ipv4_address
  }}
}}

output "vm_ips" {{
  description = "List of IP addresses for the created VMs"
  value       = [for vm in vsphere_virtual_machine.vm : vm.custom_attributes["ipv4_address"]]
}}

output "vm_ids" {{
  description = "List of IDs for the created VMs"
  value       = [for vm in vsphere_virtual_machine.vm : vm.id]
}}
"""
    
    return tf_config

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5150)
