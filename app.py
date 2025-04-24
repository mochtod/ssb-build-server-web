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
from vsphere_redis_cache import VSphereRedisCache, sync_vsphere_to_redis, VSPHERE_DATACENTERS_KEY, VSPHERE_TEMPLATES_KEY

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_key_for_development_only')

# Configuration paths
CONFIG_DIR = os.environ.get('CONFIG_DIR', 'configs')
TERRAFORM_DIR = os.environ.get('TERRAFORM_DIR', 'terraform')
USERS_FILE = os.environ.get('USERS_FILE', 'users.json')
GIT_REPO_URL = os.environ.get('GIT_REPO_URL', 'https://github.com/your-org/terraform-repo.git')
GIT_USERNAME = os.environ.get('GIT_USERNAME', '')
GIT_TOKEN = os.environ.get('GIT_TOKEN', '')
ATLANTIS_URL = os.environ.get('ATLANTIS_URL', 'http://localhost:4141')
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
    try:
        # Check if vSphere Redis cache is available
        vsphere_cache = VSphereRedisCache()
        cache_status = vsphere_cache.get_cache_status()
        
        # Get initial vSphere servers for dropdown
        vsphere_servers = vsphere_cache.get_vsphere_servers()
        
        # Get the full hierarchical vSphere data with all components needed for machine_inputs.tfvars
        # Include all parameters to ensure we get complete data
        hierarchical_data = vsphere_cache.get_hierarchical_data(
            vsphere_server=vsphere_servers[0]["id"] if vsphere_servers else None,
            # Don't specify other parameters so we get all data at each level
        )
        
        # Debug log to server console
        logger.info(f"Rendering index template with vSphere data: {len(vsphere_servers)} servers available")
        logger.info(f"Cache status: {cache_status}")
        logger.info(f"Retrieved datastore clusters: {len(hierarchical_data.get('datastore_clusters', []))} available")
        
        return render_template('index.html', 
                              server_prefixes=SERVER_PREFIXES,
                              environments=ENVIRONMENTS,
                              user_role=session.get('role', ''),
                              user_name=session.get('name', ''),
                              vsphere_servers=vsphere_servers,
                              vsphere_cache_status=cache_status,
                              vsphere_data=hierarchical_data)  # Pass the full data to the template
    except Exception as e:
        logger.error(f"Error initializing index page: {str(e)}")
        logger.exception("Detailed exception information:")
        # Still render the template, but with an error message
        return render_template('index.html', 
                              server_prefixes=SERVER_PREFIXES,
                              environments=ENVIRONMENTS,
                              user_role=session.get('role', ''),
                              user_name=session.get('name', ''),
                              vsphere_error=str(e))

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
        
        # Get vSphere resource selections
        vsphere_server = request.form.get('vsphere_server')
        datacenter = request.form.get('datacenter')
        cluster = request.form.get('cluster')
        datastore_cluster = request.form.get('datastore_cluster')
        network = request.form.get('network')
        template = request.form.get('template')
        
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
        
        # Validate vSphere selections
        if not vsphere_server or not datacenter or not cluster or not datastore_cluster or not network or not template:
            flash('All vSphere resource selections are required', 'error')
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
            'created_at': datetime.datetime.now().isoformat(),
            # vSphere resource selections
            'vsphere_server': vsphere_server,
            'datacenter': datacenter,
            'cluster': cluster,
            'datastore_cluster': datastore_cluster,
            'network': network,
            'template': template
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
        
        # Generate and save machine_inputs.tfvars to the VM workspace directory
        machine_inputs_content = generate_machine_inputs_tfvars(config_data)
        
        # Ensure the vm-workspace directory exists
        vm_workspace_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vm-workspace")
        if not os.path.exists(vm_workspace_dir):
            logger.warning(f"VM workspace directory {vm_workspace_dir} does not exist, creating it")
            os.makedirs(vm_workspace_dir, exist_ok=True)
        
        # Save machine_inputs.tfvars to the vm-workspace directory
        machine_inputs_file = os.path.join(vm_workspace_dir, "machine_inputs.tfvars")
        with open(machine_inputs_file, 'w') as f:
            f.write(machine_inputs_content)
        
        # Also save a copy to the request-specific terraform directory for reference
        with open(os.path.join(tf_directory, "machine_inputs.tfvars"), 'w') as f:
            f.write(machine_inputs_content)
            
        logger.info(f"Generated machine_inputs.tfvars for {server_name}")
        
        flash('VM configuration created successfully!', 'success')
        return redirect(url_for('show_config', request_id=request_id, timestamp=timestamp))
        
    except Exception as e:
        logger.exception(f"Error creating configuration: {str(e)}")
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
        plan_result = run_terraform_plan(config_data, tf_directory)
        
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
        build_result = apply_terraform_plan(config_data, tf_directory)
        
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
            'build_reciept.html',  # Fix: Use the existing misspelled template name
            config=config_data,
            request_id=request_id,
            timestamp=timestamp,
            user_role=session.get('role', '')
        )
    except Exception as e:
        flash(f'Error loading build receipt: {str(e)}', 'error')
        return redirect(url_for('list_configs'))  # Fix: Use the correct endpoint name 'list_configs' instead of 'configs'

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
    
    # Use bcrypt for better password security
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    users[username] = {
        'password': hashed_password,
        'role': role,
        'name': name
    }
    
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)
    
    flash(f'User {username} added successfully', 'success')
    return redirect(url_for('admin_users'))

def run_terraform_plan(config_data, tf_directory):
    """Run a Terraform plan directly using terraform_executor instead of Atlantis"""
    try:
        # Import our terraform executor functions
        from terraform_executor import run_terraform_plan as run_tf_plan
        
        # Get request ID and timestamp from config data
        request_id = config_data['request_id']
        timestamp = config_data['timestamp']
        
        # Get vSphere resources from Redis cache
        logger.info(f"Retrieving vSphere resources for environment: {config_data['environment']}")
        vsphere_cache = VSphereRedisCache()
        vsphere_resources = vsphere_cache.get_resource_for_terraform(config_data['environment'])
        
        # Update machine_inputs.tfvars with vSphere resource IDs from Redis
        vm_workspace_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vm-workspace")
        machine_inputs_file = os.path.join(vm_workspace_dir, "machine_inputs.tfvars")
        
        try:
            with open(machine_inputs_file, 'r') as f:
                machine_inputs_content = f.read()
            
            # Get the appropriate resource pool ID (which might be a cluster ID)
            resource_pool_id = vsphere_resources['resource_pool_id']
            if resource_pool_id:
                if vsphere_resources.get('resource_pool_is_cluster', False):
                    logger.info(f"Using cluster as resource pool: {vsphere_resources['resource_pool_name']} (ID: {resource_pool_id})")
                else:
                    logger.info(f"Using resource pool: {vsphere_resources['resource_pool_name']} (ID: {resource_pool_id})")
                machine_inputs_content = machine_inputs_content.replace('<resource_pool_id>', resource_pool_id)
            
            # Determine and use the appropriate storage ID (either datastore or datastore cluster)
            storage_id = vsphere_resources.get('storage_id')
            storage_type = vsphere_resources.get('storage_type')
            
            if storage_id:
                if storage_type == 'datastore_cluster':
                    logger.info(f"Using datastore cluster for storage (ID: {storage_id})")
                    # For a datastore cluster, we need to set it differently in Terraform
                    machine_inputs_content = machine_inputs_content.replace('datastore_id     = "<datastore_id>"', 
                                                                           f'datastore_id     = null\ndatastore_cluster_id = "{storage_id}"')
                else:
                    logger.info(f"Using individual datastore for storage (ID: {storage_id})")
                    machine_inputs_content = machine_inputs_content.replace('<datastore_id>', storage_id)
            
            if vsphere_resources['network_id']:
                machine_inputs_content = machine_inputs_content.replace('<network_id>', vsphere_resources['network_id'])
            
            if vsphere_resources['template_uuid']:
                machine_inputs_content = machine_inputs_content.replace('<template_uuid>', vsphere_resources['template_uuid'])
            
            if vsphere_resources['ipv4_gateway']:
                machine_inputs_content = machine_inputs_content.replace('<ipv4_gateway>', vsphere_resources['ipv4_gateway'])
            
            if vsphere_resources['ipv4_address']:
                machine_inputs_content = machine_inputs_content.replace('<ipv4_address>', vsphere_resources['ipv4_address'])
            
            # Write updated machine_inputs.tfvars
            with open(machine_inputs_file, 'w') as f:
                f.write(machine_inputs_content)
            
            # Copy updated machine_inputs.tfvars to the terraform directory
            shutil.copy(machine_inputs_file, os.path.join(tf_directory, "machine_inputs.tfvars"))
            
            logger.info(f"Updated machine_inputs.tfvars with vSphere resource IDs for {config_data['server_name']}")
        except Exception as e:
            logger.error(f"Error updating machine_inputs.tfvars: {str(e)}")
            logger.exception("Detailed error:")
            # Continue with plan even if we couldn't update machine_inputs.tfvars
        
        # Call our terraform executor to run the plan
        plan_result = run_tf_plan(request_id, timestamp, config_data, tf_directory)
        
        if plan_result['status'] == 'success':
            # Add plan URL to the result
            plan_result['atlantis_url'] = f"/terraform_plan/{plan_result['plan_id']}"
            
            return {
                'status': 'success',
                'atlantis_url': plan_result['atlantis_url'],
                'plan_log': plan_result['plan_log'],
                'plan_id': plan_result['plan_id'],
                'workspace': plan_result['workspace_id'],
                'workspace_id': plan_result['workspace_id'],
                'details': plan_result
            }
        else:
            return {
                'status': 'error',
                'message': plan_result['message']
            }
    except Exception as e:
        logger.exception(f"Error running Terraform plan: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error running Terraform plan: {str(e)}"
        }

def apply_terraform_plan(config_data, tf_directory):
    """Apply a Terraform plan directly using terraform_executor instead of Atlantis"""
    try:
        # Import our terraform executor functions
        from terraform_executor import apply_terraform_plan as apply_tf_plan
        
        # Get request ID and timestamp from config data
        request_id = config_data['request_id']
        timestamp = config_data['timestamp']
        
        # Call our terraform executor to apply the plan
        apply_result = apply_tf_plan(request_id, timestamp, config_data, tf_directory)
        
        if apply_result['status'] == 'success':
            return {
                'status': 'success',
                'build_url': apply_result['build_url'],
                'build_receipt': apply_result['build_receipt'],
                'details': {
                    'apply_id': apply_result['apply_id'],
                    'workspace': apply_result['workspace'],
                    'instructions': "Your Terraform apply has been initiated. Your VMs are being created now."
                }
            }
        else:
            return {
                'status': 'error',
                'message': apply_result['message']
            }
    except Exception as e:
        logger.exception(f"Error applying Terraform plan: {str(e)}")
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

def generate_machine_inputs_tfvars(config):
    """
    Generate a machine_inputs.tfvars file from web form input data
    This is used to feed variables to the vSphere provider in Terraform
    """
    # Extract configuration values
    server_name = config['server_name']
    num_cpus = config['num_cpus']
    memory = config['memory']
    disk_size = config['disk_size']
    additional_disks = config['additional_disks']
    quantity = config['quantity']
    environment = config['environment']
    start_number = config.get('start_number', 10001)
    
    # Format additional disks for Terraform
    additional_disks_tf = "[\n"
    for disk in additional_disks:
        additional_disks_tf += f'  {{ size = {disk["size"]}, type = "{disk["type"]}" }},\n'
    additional_disks_tf += "]"
    
    # Use default values where appropriate for vSphere-specific fields that may not be present in the form
    # These will be replaced with actual values from the vSphere Redis cache later
    
    # Generate the tfvars content
    tfvars_content = f"""# Machine inputs for {server_name}
# Generated on {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
# Environment: {environment}

name             = "{server_name}"
num_cpus         = {num_cpus}
memory           = {memory}
disk_size        = {disk_size}
guest_id         = "rhel9_64Guest"
adapter_type     = "vmxnet3"
time_zone        = "UTC"
quantity         = {quantity}
start_number     = {start_number}
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
additional_disks = {additional_disks_tf}
"""
    
    return tfvars_content

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

# vSphere Redis Cache API endpoints
@app.route('/api/vsphere-cache/status', methods=['GET'])
@login_required
def get_vsphere_cache_status():
    """
    Get the status of the vSphere Redis cache
    """
    try:
        cache = VSphereRedisCache()
        status = cache.get_cache_status()
        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        logging.error(f"Error getting vSphere cache status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/vsphere-cache/sync', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def trigger_vsphere_cache_sync():
    """
    Trigger a manual sync of vSphere objects to Redis cache
    """
    try:
        success = sync_vsphere_to_redis()
        if success:
            return jsonify({
                'success': True,
                'message': 'vSphere cache sync completed successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to sync vSphere cache'
            }), 500
    except Exception as e:
        logging.error(f"Error syncing vSphere cache: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/vsphere-cache/clear', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def clear_vsphere_cache():
    """
    Clear the vSphere Redis cache
    """
    try:
        cache = VSphereRedisCache()
        success = cache.clear_cache()
        if success:
            return jsonify({
                'success': True,
                'message': 'vSphere cache cleared successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to clear vSphere cache'
            }), 500
    except Exception as e:
        logging.error(f"Error clearing vSphere cache: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/vsphere/hierarchical', methods=['GET'])
@login_required
def get_vsphere_hierarchical_data():
    """
    Get the hierarchical data for vSphere resources
    Used to populate the cascading dropdown menus for VM creation
    """
    try:
        vsphere_server = request.args.get('vsphere_server')
        datacenter_id = request.args.get('datacenter_id')
        cluster_id = request.args.get('cluster_id')
        datastore_cluster_id = request.args.get('datastore_cluster_id')
        
        # Add more detailed logging for debugging
        logging.info(f"Hierarchical API request - Server: {vsphere_server}, Datacenter: {datacenter_id}, Cluster: {cluster_id}")
        
        cache = VSphereRedisCache()
        
        # First verify Redis connection
        redis_connected = False
        redis_error = None
        try:
            redis_connected = cache.redis_client.ping()
            logging.info(f"Redis connection status: {redis_connected}")
        except Exception as redis_err:
            redis_error = str(redis_err)
            logging.error(f"Redis connection error: {redis_error}")
            
        # First check vSphere connection directly
        vsphere_connected = False
        vsphere_error = None
        if not vsphere_server:
            vsphere_server = os.environ.get('VSPHERE_SERVER', '')
            
        if vsphere_server:
            try:
                # Test vSphere connection
                vsphere_connected = cache.connect_to_vsphere()
                if vsphere_connected:
                    cache.disconnect_from_vsphere()
                else:
                    vsphere_error = "Failed to connect to vSphere server"
            except Exception as vsphere_err:
                vsphere_error = str(vsphere_err)
                logging.error(f"vSphere connection error: {vsphere_error}")
        else:
            vsphere_error = "vSphere server not specified"
            
        # If both Redis and vSphere connections fail, return a detailed error
        if not redis_connected and not vsphere_connected:
            return jsonify({
                'success': False,
                'error': 'Connection Error',
                'details': {
                    'redis_error': redis_error,
                    'vsphere_error': vsphere_error,
                    'message': 'Cannot connect to Redis cache or vSphere server. Please verify your server connection and Redis service are running.'
                }
            }), 500
            
        # Check if datacenters exist in cache
        all_datacenters = cache.redis_client.get(VSPHERE_DATACENTERS_KEY)
        logging.info(f"Total datacenters in cache: {len(all_datacenters) if all_datacenters else 0}")
        
        # If we're requesting a specific server but no datacenters are found, this might indicate a Redis cache issue
        if vsphere_server and (not all_datacenters or len(all_datacenters) == 0):
            logging.warning(f"No datacenters found for server {vsphere_server} - Redis cache may need refreshing")
            # Try to trigger an essential sync
            try:
                from vsphere_redis_cache import sync_essential_to_redis
                success = sync_essential_to_redis()
                logging.info(f"Emergency essential sync triggered: {'Success' if success else 'Failed'}")
                # Refresh the datacenter list after sync
                all_datacenters = cache.redis_client.get(VSPHERE_DATACENTERS_KEY)
                logging.info(f"After sync - Total datacenters in cache: {len(all_datacenters) if all_datacenters else 0}")
                
                # If still no datacenters, return error with troubleshooting info
                if not all_datacenters or len(all_datacenters) == 0:
                    # Return detailed error information instead of dummy data
                    logging.error("No datacenter data found even after sync attempt")
                    return jsonify({
                        'success': False,
                        'error': 'No Datacenter Data',
                        'details': {
                            'redis_status': 'Connected but no data' if redis_connected else f'Connection error: {redis_error}',
                            'vsphere_status': 'Connected but no data' if vsphere_connected else f'Connection error: {vsphere_error}',
                            'message': 'No datacenter data found in cache or from vSphere. Please check your vSphere connection and sync settings.',
                            'troubleshooting': [
                                '1. Verify your vSphere server is reachable and credentials are correct',
                                '2. Check if Redis is running (docker-compose ps)',
                                '3. Try manually triggering a sync (docker-compose restart vsphere-sync)',
                                '4. Check logs for detailed error messages (docker-compose logs)'
                            ]
                        }
                    }), 404
            except Exception as sync_err:
                logging.error(f"Failed to trigger emergency sync: {str(sync_err)}")
                # Return a structured error response
                return jsonify({
                    'success': False,
                    'error': 'Sync Failure',
                    'details': {
                        'message': f"Failed to sync vSphere data: {str(sync_err)}",
                        'redis_status': 'Connected' if redis_connected else f'Connection error: {redis_error}',
                        'vsphere_status': 'Connected' if vsphere_connected else f'Connection error: {vsphere_error}',
                        'troubleshooting': [
                            '1. Verify Redis is running (docker-compose ps)',
                            '2. Check vSphere credentials in your .env file',
                            '3. Verify vSphere server is reachable from your environment',
                            '4. Check network connectivity and firewall settings'
                        ]
                    }
                }), 500
                
        # Get hierarchical data
        try:
            hierarchical_data = cache.get_hierarchical_data(
                vsphere_server=vsphere_server,
                datacenter_id=datacenter_id,
                cluster_id=cluster_id,
                datastore_cluster_id=datastore_cluster_id
            )
            
            # Add the vsphere_servers list to the response
            if 'vsphere_servers' not in hierarchical_data:
                hierarchical_data['vsphere_servers'] = cache.get_vsphere_servers()
            
            # Check if we have real templates or fallbacks
            templates = hierarchical_data.get('templates', [])
            has_fallback_templates = any(
                t.get('id', '').startswith('vm-fallback-') or 
                'fallback' in t.get('name', '').lower() 
                for t in templates
            )
            
            if has_fallback_templates:
                # If using fallback templates, include a warning but don't provide the templates
                return jsonify({
                    'success': False,
                    'error': 'Placeholder Templates',
                    'details': {
                        'message': 'The templates returned are placeholder values that cannot be used for real deployments.',
                        'redis_status': 'Connected' if redis_connected else f'Connection error: {redis_error}',
                        'vsphere_status': 'Connected' if vsphere_connected else f'Connection error: {vsphere_error}',
                        'troubleshooting': [
                            '1. Verify your vSphere connection settings in .env file',
                            '2. Make sure Redis is running (docker-compose ps)',
                            '3. Restart the vsphere-sync service to refresh the template cache (docker-compose restart vsphere-sync)',
                            '4. Check if your vSphere environment has templates available'
                        ]
                    }
                }), 503  # Service Unavailable
                
            # Log the result size
            logging.info(f"Returned datacenters: {len(hierarchical_data.get('datacenters', []))}")
            logging.info(f"Returned clusters: {len(hierarchical_data.get('clusters', []))}")
            logging.info(f"Returned templates: {len(hierarchical_data.get('templates', []))}")
            
            return jsonify({
                'success': True,
                'data': hierarchical_data
            })
        except Exception as hier_err:
            logging.error(f"Error retrieving hierarchical data: {str(hier_err)}")
            # Return structured error response
            return jsonify({
                'success': False,
                'error': 'Data Retrieval Error',
                'details': {
                    'message': f"Error retrieving hierarchical data: {str(hier_err)}",
                    'redis_status': 'Connected' if redis_connected else f'Connection error: {redis_error}',
                    'vsphere_status': 'Connected' if vsphere_connected else f'Connection error: {vsphere_error}',
                    'troubleshooting': [
                        '1. Try refreshing the page',
                        '2. Verify Redis and vSphere connections',
                        '3. Check application logs for more details'
                    ]
                }
            }), 500
    except Exception as e:
        logging.error(f"Error getting vSphere hierarchical data: {str(e)}")
        logging.exception("Detailed exception information:")
        # Return structured error
        return jsonify({
            'success': False,
            'error': 'Server Error',
            'details': {
                'message': str(e),
                'troubleshooting': [
                    '1. Check your server connection',
                    '2. Verify Redis is running',
                    '3. Examine server logs for detailed error messages'
                ]
            }
        }), 500

@app.route('/api/vsphere/servers', methods=['GET'])
@login_required
def get_vsphere_servers():
    """
    Get the list of available vSphere servers
    This is a simplified endpoint that just returns the hardcoded server list
    """
    try:
        cache = VSphereRedisCache()
        servers = cache.get_vsphere_servers()
        return jsonify({
            'success': True,
            'data': {
                'vsphere_servers': servers
            }
        })
    except Exception as e:
        logging.error(f"Error getting vSphere servers: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/vsphere-cache/sync-essential', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def trigger_vsphere_essential_sync():
    """
    Trigger a quick sync of essential vSphere objects to Redis cache
    Only syncs data needed for the UI (datacenters, clusters, networks, templates)
    """
    try:
        from vsphere_redis_cache import sync_essential_to_redis
        success = sync_essential_to_redis()
        if success:
            return jsonify({
                'success': True,
                'message': 'Essential vSphere data synchronized successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to synchronize essential vSphere data'
            }), 500
    except Exception as e:
        logging.error(f"Error syncing essential vSphere data: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/vsphere-cache/progress', methods=['GET'])
@login_required
def get_vsphere_sync_progress():
    """
    Get the progress of the current vSphere sync operation
    """
    try:
        from vsphere_redis_cache import get_sync_progress
        progress = get_sync_progress()
        return jsonify({
            'success': True,
            'progress': progress
        })
    except Exception as e:
        logging.error(f"Error getting vSphere sync progress: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/settings')
@login_required
def settings():
    """
    User settings page with theme preferences and environment settings for admins
    """
    # Default env settings
    env_settings = {
        'CONFIG_DIR': os.environ.get('CONFIG_DIR', 'configs'),
        'TERRAFORM_DIR': os.environ.get('TERRAFORM_DIR', 'terraform'),
        'USERS_FILE': os.environ.get('USERS_FILE', 'users.json'),
        'GIT_REPO_URL': os.environ.get('GIT_REPO_URL', ''),
        'GIT_USERNAME': os.environ.get('GIT_USERNAME', ''),
        'GIT_TOKEN': os.environ.get('GIT_TOKEN', ''),
        'ATLANTIS_URL': os.environ.get('ATLANTIS_URL', 'https://atlantis.chrobinson.com'),
        'ATLANTIS_TOKEN': os.environ.get('ATLANTIS_TOKEN', ''),
        'FLASK_SECRET_KEY': os.environ.get('FLASK_SECRET_KEY', ''),
        'VSPHERE_SERVER': os.environ.get('VSPHERE_SERVER', ''),
        'VSPHERE_PORT': os.environ.get('VSPHERE_PORT', ''),
        'VSPHERE_USER': os.environ.get('VSPHERE_USER', ''),
        'VSPHERE_PASSWORD': os.environ.get('VSPHERE_PASSWORD', ''),
        'VSPHERE_USE_SSL': os.environ.get('VSPHERE_USE_SSL', 'True')
    }
    
    return render_template(
        'settings.html',
        user_role=session.get('role', ''),
        user_name=session.get('name', ''),
        env_settings=env_settings
    )

@app.route('/update_env_settings', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def update_env_settings():
    """
    Update application environment settings (.env file)
    """
    try:
        # Get current settings
        current_settings = load_env_settings()
        
        # Update settings from form data
        form_settings = {}
        
        # Server configuration
        form_settings['CONFIG_DIR'] = request.form.get('config_dir', current_settings.get('CONFIG_DIR', '/app/configs'))
        form_settings['TERRAFORM_DIR'] = request.form.get('terraform_dir', current_settings.get('TERRAFORM_DIR', '/app/terraform'))
        form_settings['USERS_FILE'] = request.form.get('users_file', current_settings.get('USERS_FILE', '/app/users.json'))
        
        # Application security
        form_settings['FLASK_SECRET_KEY'] = request.form.get('flask_secret_key', current_settings.get('FLASK_SECRET_KEY', ''))
        if not form_settings['FLASK_SECRET_KEY']:
            # Generate a random secret key if none provided
            import secrets
            form_settings['FLASK_SECRET_KEY'] = secrets.token_hex(32)
            
        # vSphere connection settings
        form_settings['VSPHERE_SERVER'] = request.form.get('vsphere_server', current_settings.get('VSPHERE_SERVER', ''))
        form_settings['VSPHERE_PORT'] = request.form.get('vsphere_port', current_settings.get('VSPHERE_PORT', '443'))
        form_settings['VSPHERE_USER'] = request.form.get('vsphere_user', current_settings.get('VSPHERE_USER', ''))
        form_settings['VSPHERE_PASSWORD'] = request.form.get('vsphere_password', current_settings.get('VSPHERE_PASSWORD', ''))
        form_settings['VSPHERE_USE_SSL'] = request.form.get('vsphere_use_ssl', current_settings.get('VSPHERE_USE_SSL', 'true'))
        form_settings['VSPHERE_VERIFY_SSL'] = request.form.get('vsphere_verify_ssl', current_settings.get('VSPHERE_VERIFY_SSL', 'false'))
        
        # NetBox integration settings
        form_settings['NETBOX_URL'] = request.form.get('netbox_url', current_settings.get('NETBOX_URL', ''))
        form_settings['NETBOX_TOKEN'] = request.form.get('netbox_token', current_settings.get('NETBOX_TOKEN', ''))
        form_settings['NETBOX_VERIFY_SSL'] = request.form.get('netbox_verify_ssl', current_settings.get('NETBOX_VERIFY_SSL', 'false'))
        
        # Redis configuration
        form_settings['REDIS_HOST'] = request.form.get('redis_host', current_settings.get('REDIS_HOST', 'localhost'))
        form_settings['REDIS_PORT'] = request.form.get('redis_port', current_settings.get('REDIS_PORT', '6379'))
        form_settings['REDIS_PASSWORD'] = request.form.get('redis_password', current_settings.get('REDIS_PASSWORD', ''))
        form_settings['REDIS_CACHE_TTL'] = request.form.get('redis_cache_ttl', current_settings.get('REDIS_CACHE_TTL', '3600'))
        
        # Keep existing settings not in the form
        for key, value in current_settings.items():
            if key not in form_settings:
                form_settings[key] = value
        
        # Save updated settings
        if save_env_settings(form_settings):
            flash('Environment settings updated successfully.', 'success')
            
            # Reload environment variables for the current app instance
            from dotenv import load_dotenv
            load_dotenv(override=True)
            
        else:
            flash('Error saving environment settings.', 'error')
        
        return redirect(url_for('settings'))
        
    except Exception as e:
        logging.error(f"Error updating environment settings: {str(e)}")
        flash(f'Error updating environment settings: {str(e)}', 'error')
        return redirect(url_for('settings'))

@app.route('/api/vsphere/templates', methods=['GET'])
def get_vsphere_templates():
    """
    API endpoint to get VM templates from the Redis cache
    This helps debug template availability issues and provides a dedicated endpoint
    """
    try:
        # Initialize VSphereRedisCache to access Redis data
        vsphere_cache = VSphereRedisCache()
        
        # Get parameters from query string
        vsphere_server = request.args.get('vsphere_server')
        datacenter_id = request.args.get('datacenter_id')
        
        # Get templates from Redis cache
        templates = vsphere_cache.redis_client.get(VSPHERE_TEMPLATES_KEY) or []
        
        # Log template count and first few templates for debugging
        template_count = len(templates) 
        logger.info(f"API retrieved {template_count} templates from Redis cache")
        
        # Log first 3 templates for debugging
        for i, template in enumerate(templates[:3]):
            logger.info(f"Template {i+1}: {template.get('name')} (ID: {template.get('id')})")
            
        # Filter by datacenter if specified
        if datacenter_id:
            datacenter_templates = [t for t in templates if t.get('datacenter_id') == datacenter_id]
            if datacenter_templates:
                logger.info(f"Filtered to {len(datacenter_templates)} templates for datacenter {datacenter_id}")
                templates = datacenter_templates
            else:
                logger.info(f"No templates found specifically for datacenter {datacenter_id}, returning all templates")
        
        # Even if no templates found, ensure we return fallback templates
        if not templates:
            logger.warning("No templates found in Redis, adding fallback templates")
            templates = [
                {
                    'id': 'vm-fallback-rhel9',
                    'name': 'rhel9-template (fallback)',
                    'is_template': True,
                    'guest_id': 'rhel9_64Guest',
                    'guest_full_name': 'Red Hat Enterprise Linux 9 (64-bit)'
                },
                {
                    'id': 'vm-fallback-win',
                    'name': 'windows-template (fallback)',
                    'is_template': True,
                    'guest_id': 'windows2019srv_64Guest',
                    'guest_full_name': 'Windows Server 2019 (64-bit)'
                }
            ]
        
        return jsonify({
            'success': True,
            'templates': templates,
            'count': len(templates),
            'filtered_by_datacenter': bool(datacenter_id)
        })
    except Exception as e:
        logger.exception(f"Error getting vSphere templates: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Connection testing API endpoints
@app.route('/api/test-connection/vsphere', methods=['POST'])
@login_required
def test_vsphere_connection():
    """Test the connection to vSphere using provided credentials"""
    try:
        data = request.json
        logging.info("Testing vSphere connection with provided settings")
        
        # Extract connection parameters
        server = data.get('server')
        port = int(data.get('port', 443))
        username = data.get('username')
        password = data.get('password')
        use_ssl = data.get('use_ssl', 'true').lower() == 'true'
        verify_ssl = data.get('verify_ssl', 'false').lower() == 'true'
        
        # Validate required parameters
        if not server or not username or not password:
            return jsonify({
                'success': False,
                'error': 'Missing required parameters: server, username, and password are required'
            }), 400
        
        # Import necessary modules
        try:
            import ssl
            from pyVim import connect
            from pyVmomi import vim
        except ImportError as e:
            return jsonify({
                'success': False,
                'error': f'Required Python modules not installed: {str(e)}'
            }), 500
        
        # Create SSL context if using SSL
        context = None
        if use_ssl:
            context = ssl.create_default_context()
            if not verify_ssl:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
        
        # Handle Windows domain-style username (domain\username)
        if '\\' in username:
            # Escape backslash for vSphere API
            username = username.replace('\\', '\\\\')
        
        # Try to connect to vSphere
        try:
            vsphere_conn = connect.SmartConnect(
                host=server,
                user=username,
                pwd=password,
                port=port,
                sslContext=context
            )
            
            if not vsphere_conn:
                return jsonify({
                    'success': False,
                    'error': 'Failed to connect to vSphere - connection returned None'
                }), 500
            
            # Get information about the vSphere environment
            content = vsphere_conn.RetrieveContent()
            about_info = content.about
            
            # Disconnect
            connect.Disconnect(vsphere_conn)
            
            # Return success with vSphere details
            return jsonify({
                'success': True,
                'message': f'Connected to {about_info.fullName}',
                'details': {
                    'version': about_info.version,
                    'build': about_info.build,
                    'api_version': about_info.apiVersion,
                    'name': about_info.name,
                    'vendor': about_info.vendor
                }
            })
        except vim.fault.InvalidLogin as e:
            # Specifically handle authentication failures with a clear message
            return jsonify({
                'success': False,
                'error': f'Authentication failed: Cannot complete login due to an incorrect user name or password.',
                'troubleshooting': [
                    '1. Verify your username and password are correct',
                    '2. For domain accounts, make sure to use the format: domain\\username',
                    '3. Check if your account is locked or has expired',
                    '4. Verify this account has access to vSphere'
                ]
            }), 401
        except vim.fault.HostConnectFault as e:
            # Handle host connection issues
            return jsonify({
                'success': False,
                'error': f'Host connection error: {str(e)}',
                'troubleshooting': [
                    '1. Verify the vSphere host address is correct',
                    '2. Check if the host is reachable on your network',
                    '3. Verify the port number (default is 443)',
                    '4. Check firewall settings between this server and vSphere'
                ]
            }), 500
        except Exception as e:
            error_str = str(e).lower()
            if "login" in error_str and ("incorrect" in error_str or "failed" in error_str or "invalid" in error_str):
                # Additional handling for login errors that may not use the specific vim.fault.InvalidLogin exception
                return jsonify({
                    'success': False,
                    'error': f'Authentication failed: {str(e)}',
                    'troubleshooting': [
                        '1. Verify your username and password are correct',
                        '2. For domain accounts, make sure to use the format: domain\\username',
                        '3. Check if your account is locked or has expired',
                        '4. Verify this account has access to vSphere'
                    ]
                }), 401
            else:
                return jsonify({
                    'success': False,
                    'error': f'vSphere connection error: {str(e)}'
                }), 500
            
    except Exception as e:
        logging.error(f"Error testing vSphere connection: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500

@app.route('/api/test-connection/netbox', methods=['POST'])
@login_required
def test_netbox_connection():
    """Test the connection to NetBox using provided credentials"""
    try:
        data = request.json
        logging.info("Testing NetBox connection with provided settings")
        
        # Extract connection parameters
        url = data.get('url')
        token = data.get('token')
        verify_ssl = data.get('verify_ssl', 'true').lower() == 'true'
        
        # Validate required parameters
        if not url or not token:
            return jsonify({
                'success': False,
                'error': 'Missing required parameters: url and token are required'
            }), 400
        
        # Ensure URL has a trailing slash if needed
        if not url.endswith('/'):
            url = url + '/'
        
        # Import requests module
        try:
            import requests
        except ImportError:
            return jsonify({
                'success': False,
                'error': 'Python requests module not installed'
            }), 500
        
        # Set up headers for NetBox API
        headers = {
            'Authorization': f'Token {token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        # Try to connect to NetBox and get status
        try:
            # Use a simple API endpoint that should always be available
            # First try the status endpoint (if available)
            response = requests.get(
                f"{url}status/", 
                headers=headers, 
                verify=verify_ssl,
                timeout=10
            )
            
            if response.status_code != 200:
                # If status endpoint fails, try the main API endpoint
                response = requests.get(
                    url, 
                    headers=headers, 
                    verify=verify_ssl,
                    timeout=10
                )
            
            # Check response
            if response.status_code == 200:
                response_data = response.json()
                
                # Extract version if available
                version = "Unknown"
                if 'netbox-version' in response.headers:
                    version = response.headers['netbox-version']
                elif 'version' in response_data:
                    version = response_data['version']
                
                return jsonify({
                    'success': True,
                    'message': f'Connected to NetBox {version}',
                    'details': {
                        'version': version,
                        'api_endpoints': list(response_data.keys()) if isinstance(response_data, dict) else []
                    }
                })
            else:
                return jsonify({
                    'success': False,
                    'error': f'NetBox connection failed with status code {response.status_code}: {response.text}'
                }), 500
                
        except requests.exceptions.SSLError:
            return jsonify({
                'success': False,
                'error': 'SSL Certificate validation failed. Try setting "Verify SSL" to No.'
            }), 500
        except requests.exceptions.RequestException as e:
            return jsonify({
                'success': False,
                'error': f'NetBox connection error: {str(e)}'
            }), 500
            
    except Exception as e:
        logging.error(f"Error testing NetBox connection: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500

@app.route('/api/test-connection/redis', methods=['POST'])
@login_required
def test_redis_connection():
    """Test the connection to Redis using provided credentials"""
    try:
        data = request.json
        logging.info("Testing Redis connection with provided settings")
        
        # Extract connection parameters
        host = data.get('host')
        port = int(data.get('port', 6379))
        password = data.get('password')
        
        # Validate required parameters
        if not host:
            return jsonify({
                'success': False,
                'error': 'Missing required parameter: host'
            }), 400
        
        # Import Redis module
        try:
            import redis
        except ImportError:
            return jsonify({
                'success': False,
                'error': 'Python redis module not installed'
            }), 500
        
        # Try to connect to Redis and ping
        try:
            # Create connection
            if password and password.strip():
                r = redis.Redis(host=host, port=port, password=password, socket_timeout=5)
            else:
                r = redis.Redis(host=host, port=port, socket_timeout=5)
            
            # Test connection with ping
            if r.ping():
                # Get some Redis server info
                info = r.info()
                
                return jsonify({
                    'success': True,
                    'message': f'Connected to Redis {info.get("redis_version", "Unknown version")}',
                    'details': {
                        'version': info.get('redis_version', 'Unknown'),
                        'uptime_in_days': info.get('uptime_in_days', 0),
                        'memory_used': info.get('used_memory_human', 'Unknown'),
                        'total_connections': info.get('total_connections_received', 0)
                    }
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Redis connection succeeded but ping failed'
                }), 500
        except redis.exceptions.AuthenticationError:
            return jsonify({
                'success': False,
                'error': 'Redis authentication failed. Check your password.'
            }), 500
        except redis.exceptions.ConnectionError as e:
            return jsonify({
                'success': False,
                'error': f'Redis connection error: {str(e)}'
            }), 500
            
    except Exception as e:
        logging.error(f"Error testing Redis connection: {str(e)}")
        return jsonify({
            'success': False,
                'error': f'Server error: {str(e)}'
        }), 500

@app.route('/restart-application', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def restart_application():
    """
    Restart the Flask application to apply environment variable changes
    """
    try:
        # We'll implement a "soft restart" by sending a signal to the main process
        # This approach avoids disrupting active users
        
        # First, save any pending changes to ensure they're applied after restart
        if request.json and 'save_changes' in request.json and request.json['save_changes']:
            # Reload .env file to apply recent changes
            from dotenv import load_dotenv
            load_dotenv(override=True)
            logging.info("Reloaded environment variables from .env file")
        
        # Log the restart request
        logging.info("Application restart requested by admin user: {}".format(session.get('username')))
        
        # For Docker environments, we'll just inform the user that they need to restart the container
        # In a production environment, this could trigger a process manager to restart the app
        
        return jsonify({
            'success': True,
            'message': 'Environment variables reloaded. Some changes may require a container restart to take full effect.',
            'restart_required': True
        })
    except Exception as e:
        logging.error(f"Error restarting application: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def load_env_settings():
    """
    Load environment variables from .env file and return them as a dictionary
    """
    env_settings = {}
    
    # First try to load from .env file
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if line and not line.startswith('#'):
                        # Parse key-value pairs
                        if '=' in line:
                            key, value = line.split('=', 1)
                            env_settings[key.strip()] = value.strip()
        except Exception as e:
            logging.error(f"Error reading .env file: {str(e)}")
    
    # Fill any missing values from environment
    for key, value in os.environ.items():
        if key not in env_settings:
            env_settings[key] = value
    
    return env_settings

def save_env_settings(env_settings):
    """
    Save environment variables to .env file
    """
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    
    try:
        # Create backup of existing .env file
        if os.path.exists(env_path):
            backup_path = f"{env_path}.bak"
            shutil.copy2(env_path, backup_path)
            logging.info(f"Created backup of .env file at {backup_path}")
        
        # Write updated .env file
        with open(env_path, 'w') as f:
            f.write(f"# Environment settings - Updated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Group settings by category
            categories = {
                "Flask Application": ["FLASK_SECRET_KEY", "DEBUG"],
                "Application Directories": ["CONFIG_DIR", "TERRAFORM_DIR", "USERS_FILE", "VM_WORKSPACE_DIR"],
                "vSphere Connection": ["VSPHERE_SERVER", "VSPHERE_USER", "VSPHERE_PASSWORD", "VSPHERE_PORT", 
                                      "VSPHERE_USE_SSL", "VSPHERE_VERIFY_SSL"],
                "NetBox Integration": ["NETBOX_URL", "NETBOX_TOKEN", "NETBOX_VERIFY_SSL"],
                "Redis Configuration": ["REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD", "REDIS_CACHE_TTL",
                                      "REDIS_USE_COMPRESSION", "REDIS_CONNECTION_POOL_SIZE"],
                "Timeouts": ["TIMEOUT", "VSPHERE_SYNC_COOLDOWN", "VSPHERE_REFRESH_INTERVAL"],
                "Terraform Configuration": ["TF_VAR_vsphere_server", "TF_VAR_vsphere_user", "TF_VAR_vsphere_password", 
                                          "TF_CLI_ARGS_apply", "TF_IN_AUTOMATION", "TERRAFORM_CONTAINER"]
            }
            
            # Other settings not in any category
            other_settings = set(env_settings.keys())
            for category, keys in categories.items():
                for key in keys:
                    if key in env_settings:
                        other_settings.discard(key)
            
            # Write settings by category
            for category, keys in categories.items():
                category_keys = [key for key in keys if key in env_settings]
                if category_keys:
                    f.write(f"# {category}\n")
                    for key in category_keys:
                        f.write(f"{key}={env_settings[key]}\n")
                    f.write("\n")
            
            # Write other settings
            if other_settings:
                f.write("# Other Settings\n")
                for key in sorted(other_settings):
                    f.write(f"{key}={env_settings[key]}\n")
        
        logging.info(f"Successfully saved environment settings to {env_path}")
        return True
    except Exception as e:
        logging.error(f"Error saving environment settings: {str(e)}")
        return False

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5150)
