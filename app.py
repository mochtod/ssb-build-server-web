#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, make_response
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
import threading
import time
from werkzeug.utils import secure_filename
from functools import wraps
from git import Repo
from git.exc import GitCommandError
import logging
from vsphere_utils import test_vsphere_connection
import vsphere_optimized_loader
from vsphere_resource_functions import generate_variables_file, generate_terraform_config

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_key_for_development_only')

class VSphereResourceManager:
    """Manages asynchronous fetching of vSphere resources."""
    
    def __init__(self):
        self.resources = vsphere_optimized_loader.get_default_resources()
        self.status = {
            'loading': False,
            'last_update': None,
            'error': None
        }
        self.lock = threading.RLock()
    
    def start_background_fetch(self):
        """Start a background thread to fetch vSphere resources."""
        with self.lock:
            if self.status['loading']:
                logger.info("Resource fetching already in progress")
                return False
            
            self.status['loading'] = True
            self.status['error'] = None
        
        thread = threading.Thread(target=self._fetch_resources)
        thread.daemon = True
        thread.start()
        logger.info("Started background thread for vSphere resource fetching")
        return True
    
    def _fetch_resources(self):
        """Worker function to fetch vSphere resources."""
        try:
            logger.info("Background thread fetching vSphere resources")
            # Get target datacenters from environment variable, if set
            target_dcs = os.environ.get('VSPHERE_DATACENTERS', '').split(',')
            target_dcs = [dc.strip() for dc in target_dcs if dc.strip()]
            
            # Use optimized loader with targeted datacenter filtering
            resources = vsphere_optimized_loader.get_vsphere_resources(
                use_cache=True, 
                force_refresh=True,
                target_datacenters=target_dcs if target_dcs else None
            )
            
            with self.lock:
                self.resources = resources
                self.status['loading'] = False
                self.status['last_update'] = time.time()
                logger.info("Successfully updated vSphere resources in background")
        except Exception as e:
            logger.exception(f"Error fetching vSphere resources in background: {str(e)}")
            with self.lock:
                self.status['loading'] = False
                self.status['error'] = str(e)
    
    def get_resources(self):
        """Get the current resources (either cached or defaults)."""
        with self.lock:
            return self.resources
    
    def get_status(self):
        """Get the current loading status."""
        with self.lock:
            status = self.status.copy()
            if status['last_update']:
                status['last_update_str'] = datetime.datetime.fromtimestamp(
                    status['last_update']).strftime('%Y-%m-%d %H:%M:%S')
            return status

# Initialize vSphere resource manager
resource_manager = VSphereResourceManager()

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

# Functions to manage environment variables
def read_env_file(env_file='.env'):
    """Read environment variables from a .env file"""
    env_vars = {}
    try:
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    # Skip comments and empty lines
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Handle lines with = in the value
                        if '=' in line:
                            key, value = line.split('=', 1)
                            env_vars[key.strip()] = value.strip()
        return env_vars
    except Exception as e:
        logger.error(f"Error reading environment file: {str(e)}")
        return {}

def write_env_file(env_vars, env_file='.env'):
    """Write environment variables to a .env file"""
    try:
        # Create backup of current .env file
        if os.path.exists(env_file):
            backup_file = f"{env_file}.bak"
            shutil.copy2(env_file, backup_file)
            logger.info(f"Created backup of {env_file} at {backup_file}")
        
        # Write new .env file
        with open(env_file, 'w') as f:
            # Group variables by sections
            sections = {
                'Flask Application': ['FLASK_SECRET_KEY'],
                'Timeouts': ['TIMEOUT'],
                'Atlantis Integration': ['ATLANTIS_URL', 'ATLANTIS_TOKEN'],
                'VSphere Connection': ['VSPHERE_USER', 'VSPHERE_PASSWORD', 'VSPHERE_SERVER'],
                # Remove VM Location Details section as these should be set per VM
                'NetBox Integration': ['NETBOX_TOKEN', 'NETBOX_URL'],
                'Other': []
            }
            
            # Categorize variables
            categorized = set()
            for section, keys in sections.items():
                section_vars = {k: env_vars[k] for k in keys if k in env_vars}
                if section_vars:
                    f.write(f"# {section}\n")
                    for key, value in section_vars.items():
                        f.write(f"{key}={value}\n")
                    f.write("\n")
                    categorized.update(section_vars.keys())
            
            # Add any uncategorized variables
            uncategorized = {k: v for k, v in env_vars.items() if k not in categorized}
            if uncategorized:
                f.write("# Other Variables\n")
                for key, value in uncategorized.items():
                    f.write(f"{key}={value}\n")
        
        logger.info(f"Successfully wrote {len(env_vars)} environment variables to {env_file}")
        return True
    except Exception as e:
        logger.error(f"Error writing environment file: {str(e)}")
        return False

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

# Helper function to check password with bcrypt
def check_password(stored_password, provided_password):
    # Check if the stored password is already hashed (starts with $2b$)
    if stored_password.startswith('$2b$'):
        # Compare hashed password
        return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password.encode('utf-8'))
    else:
        # For backward compatibility - plaintext comparison
        # This allows existing plaintext passwords to still work
        return stored_password == provided_password

# Helper function to hash password
def hash_password(password):
    # Generate a salt and hash the password
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Set a maximum number of login attempts
        login_attempts = session.get('login_attempts', 0)
        
        # If too many attempts, show error
        if login_attempts >= 5:
            flash('Too many login attempts. Please try again later.', 'error')
            return render_template('login.html')
            
        users = load_users()
        
        if username in users and check_password(users[username]['password'], password):
            # Reset login attempts on successful login
            session.pop('login_attempts', None)
            
            # Set session variables
            session['username'] = username
            session['role'] = users[username]['role']
            session['name'] = users[username]['name']
            
            # Set session timeout (30 minutes)
            session.permanent = True
            app.permanent_session_lifetime = datetime.timedelta(minutes=30)
            
            flash(f'Welcome, {users[username]["name"]}!', 'success')
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            # Increment login attempts
            session['login_attempts'] = login_attempts + 1
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
    # Get VSphere resources from the resource manager
    # This will return either cached resources or defaults
    vs_resources = resource_manager.get_resources()
    
    # Get loading status
    resource_status = resource_manager.get_status()
    
    # No need to get default IDs from environment variables anymore
    # Resources will be set per-VM based on user selection
    
    logger.info(f"Using resources: {len(vs_resources['resource_pools'])} resource pools, "
               f"{len(vs_resources['datastores'])} datastores, "
               f"{len(vs_resources['networks'])} networks, "
               f"{len(vs_resources['templates'])} templates")
    
    # If resources aren't currently loading and we have no last update, start a fetch
    if (not resource_status['loading'] and not resource_status['last_update']):
        resource_manager.start_background_fetch()
        resource_status = resource_manager.get_status()
        logger.info("Started background fetch of vSphere resources")
    
    return render_template('index.html', 
                          server_prefixes=SERVER_PREFIXES,
                          environments=ENVIRONMENTS,
                          user_role=session.get('role', ''),
                          user_name=session.get('name', ''),
                          resource_pools=vs_resources['resource_pools'],
                          datastores=vs_resources['datastores'],
                          networks=vs_resources['networks'],
                          templates=vs_resources['templates'],
                          resource_status=resource_status,
                          resources_loading=resource_status['loading'])

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
        resource_pool = request.form.get('resource_pool', '')
        datastore = request.form.get('datastore', '')
        network = request.form.get('network', '')
        template = request.form.get('template', '')
        
        # Validate that all required vSphere resources are selected
        if not resource_pool or not datastore or not network or not template:
            flash('All vSphere resources (resource pool, datastore, network, and template) must be selected', 'error')
            return redirect(url_for('index'))
        
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
            'created_at': datetime.datetime.now().isoformat(),
            # Store the selected vSphere resources explicitly with the VM configuration
            'vsphere_resources': {
                'resource_pool_id': resource_pool,
                'datastore_id': datastore,
                'network_id': network,
                'template_uuid': template
            }
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
        build_result = run_atlantis_apply(config_data, tf_directory)
        
        if build_result and build_result.get('status') == 'success':
            # Update config with build info
            config_data['build_status'] = 'completed'
            config_data['build_log'] = build_result.get('build_log', '')
            config_data['build_completed_at'] = datetime.datetime.now().isoformat()
            
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            flash('VM build completed successfully!', 'success')
            return redirect(url_for('build_receipt', request_id=request_id, timestamp=timestamp))
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
        flash(f'Error building configuration: {str(e)}', 'error')
        return redirect(url_for('show_plan', request_id=request_id, timestamp=timestamp))

# Admin routes
@app.route('/admin/users')
@role_required(ROLE_ADMIN)
def admin_users():
    """Admin user management page"""
    users = load_users()
    return render_template('admin_users.html', users=users)

@app.route('/admin/add_user', methods=['POST'])
@role_required(ROLE_ADMIN)
def add_user():
    """Add a new user"""
    try:
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name')
        role = request.form.get('role')
        
        if not username or not password or not name or not role:
            flash('All fields are required', 'error')
            return redirect(url_for('admin_users'))
        
        # Load existing users
        users = load_users()
        
        # Check if user already exists
        if username in users:
            flash(f'User {username} already exists', 'error')
            return redirect(url_for('admin_users'))
        
        # Add new user with hashed password
        users[username] = {
            'password': hash_password(password),
            'name': name,
            'role': role
        }
        
        # Save updated users
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=2)
        
        flash(f'User {username} added successfully', 'success')
        return redirect(url_for('admin_users'))
        
    except Exception as e:
        flash(f'Error adding user: {str(e)}', 'error')
        return redirect(url_for('admin_users'))

@app.route('/admin/settings')
@role_required(ROLE_ADMIN)
def admin_settings():
    """Admin settings page"""
    env_vars = read_env_file()
    return render_template('admin_settings.html', env_vars=env_vars)

@app.route('/admin/save_settings', methods=['POST'])
@role_required(ROLE_ADMIN)
def admin_save_settings():
    """Save application settings"""
    try:
        # Get form data
        form_data = {key: value for key, value in request.form.items() if key not in ['csrf_token']}
        
        # Read existing environment variables
        env_vars = read_env_file()
        
        # Update with new values (only if not empty)
        for key, value in form_data.items():
            if value:  # Only update if value is not empty
                env_vars[key] = value
        
        # Save back to .env file
        if write_env_file(env_vars):
            flash('Settings saved successfully', 'success')
        else:
            flash('Error saving settings to file', 'error')
            
        return redirect(url_for('admin_settings'))
        
    except Exception as e:
        flash(f'Error saving settings: {str(e)}', 'error')
        return redirect(url_for('admin_settings'))

@app.route('/admin/test_connection/<service>', methods=['POST'])
@role_required(ROLE_ADMIN)
def admin_test_connection(service):
    """Test connection to a service"""
    try:
        if service == 'vsphere':
            # Test vSphere connection
            conn_result = test_vsphere_connection()
            if conn_result.get('success'):
                flash('vSphere connection successful', 'success')
            else:
                flash(f'vSphere connection failed: {conn_result.get("message")}', 'error')
        
        elif service == 'atlantis':
            # Test Atlantis connection
            try:
                atlantis_url = os.environ.get('ATLANTIS_URL', '')
                atlantis_token = os.environ.get('ATLANTIS_TOKEN', '')
                
                if not atlantis_url:
                    flash('Atlantis URL is not configured', 'error')
                    return redirect(url_for('admin_settings'))
                
                # Make a simple health check request
                headers = {}
                if atlantis_token:
                    headers['X-Atlantis-Token'] = atlantis_token
                
                response = requests.get(f"{atlantis_url}/healthz", headers=headers, timeout=10)
                
                if response.status_code == 200:
                    flash('Atlantis connection successful', 'success')
                else:
                    flash(f'Atlantis connection failed: HTTP {response.status_code}', 'error')
            except Exception as e:
                flash(f'Atlantis connection failed: {str(e)}', 'error')
        
        elif service == 'netbox':
            # Test NetBox connection
            try:
                netbox_url = os.environ.get('NETBOX_URL', '')
                netbox_token = os.environ.get('NETBOX_TOKEN', '')
                
                if not netbox_url:
                    flash('NetBox URL is not configured', 'error')
                    return redirect(url_for('admin_settings'))
                
                # Make a simple request to the API
                headers = {
                    'Accept': 'application/json'
                }
                
                if netbox_token:
                    headers['Authorization'] = f'Token {netbox_token}'
                
                response = requests.get(f"{netbox_url}/status/", headers=headers, timeout=10)
                
                if response.status_code == 200:
                    flash('NetBox connection successful', 'success')
                else:
                    flash(f'NetBox connection failed: HTTP {response.status_code}', 'error')
            except Exception as e:
                flash(f'NetBox connection failed: {str(e)}', 'error')
        
        else:
            flash(f'Unknown service: {service}', 'error')
        
        return redirect(url_for('admin_settings'))
    
    except Exception as e:
        flash(f'Error testing connection: {str(e)}', 'error')
        return redirect(url_for('admin_settings'))

# Atlantis API functions
def run_atlantis_plan(config_data, tf_directory):
    """Run Terraform plan via Atlantis API"""
    try:
        # Get plan metadata
        server_name = config_data.get('server_name', 'unknown')
        request_id = config_data.get('request_id', 'unknown')
        
        # Prepare the payload using the helper function from fix_atlantis_apply
        from fix_atlantis_apply import generate_atlantis_payload
        
        # Get all terraform files in the directory
        tf_files = [f for f in os.listdir(tf_directory) if f.endswith('.tf') or f.endswith('.tfvars')]
        
        # Generate the payload for Atlantis API
        payload = generate_atlantis_payload(
            repo="build-server-repo",
            workspace="default",
            dir=tf_directory,
            commit_hash=f"request-{request_id}",
            comment="plan",
            user=config_data.get('build_username', 'system'),
            files=tf_files
        )
        
        # Call Atlantis API
        atlantis_url = os.environ.get('ATLANTIS_URL', '')
        atlantis_token = os.environ.get('ATLANTIS_TOKEN', '')
        
        if not atlantis_url:
            return {
                'status': 'error',
                'message': 'Atlantis URL is not configured'
            }
        
        # Prepare headers
        headers = {
            'Content-Type': 'application/json'
        }
        
        if atlantis_token:
            headers['X-Atlantis-Token'] = atlantis_token
        
        # Make the request to Atlantis
        response = requests.post(
            f"{atlantis_url}/api/plan",
            json=payload,
            headers=headers,
            timeout=int(os.environ.get('TIMEOUT', 120))
        )
        
        # Check response
        if response.status_code == 200:
            response_data = response.json()
            plan_id = response_data.get('id', '')
            return {
                'status': 'success',
                'plan_id': plan_id,
                'atlantis_url': f"{atlantis_url}/plan/{plan_id}",
                'plan_log': response_data.get('log', '')
            }
        else:
            return {
                'status': 'error',
                'message': f"Atlantis API returned status code {response.status_code}: {response.text}"
            }
    
    except Exception as e:
        logger.exception(f"Error running Atlantis plan: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }

def run_atlantis_apply(config_data, tf_directory):
    """Apply Terraform plan via Atlantis API"""
    try:
        # Get the plan ID from the config
        plan_id = config_data.get('plan_id')
        if not plan_id:
            return {
                'status': 'error',
                'message': 'No plan ID found in configuration'
            }
        
        # Get all terraform files in the directory
        tf_files = [f for f in os.listdir(tf_directory) if f.endswith('.tf') or f.endswith('.tfvars')]
        
        # Prepare the payload for apply
        from fix_atlantis_apply import generate_atlantis_apply_payload_fixed
        
        payload = generate_atlantis_apply_payload_fixed(config_data, tf_directory, tf_files, plan_id)
        
        # Call Atlantis API
        atlantis_url = os.environ.get('ATLANTIS_URL', '')
        atlantis_token = os.environ.get('ATLANTIS_TOKEN', '')
        
        if not atlantis_url:
            return {
                'status': 'error',
                'message': 'Atlantis URL is not configured'
            }
        
        # Prepare headers
        headers = {
            'Content-Type': 'application/json'
        }
        
        if atlantis_token:
            headers['X-Atlantis-Token'] = atlantis_token
        
        # Make the request to Atlantis
        response = requests.post(
            f"{atlantis_url}/api/apply",
            json=payload,
            headers=headers,
            timeout=int(os.environ.get('TIMEOUT', 300))
        )
        
        # Check response
        if response.status_code == 200:
            response_data = response.json()
            return {
                'status': 'success',
                'apply_id': response_data.get('id', ''),
                'build_log': response_data.get('log', '')
            }
        else:
            return {
                'status': 'error',
                'message': f"Atlantis API returned status code {response.status_code}: {response.text}"
            }
    
    except Exception as e:
        logger.exception(f"Error applying Terraform plan: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }

@app.route('/build_receipt/<request_id>_<timestamp>')
@login_required
def build_receipt(request_id, timestamp):
    """Build receipt page"""
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
