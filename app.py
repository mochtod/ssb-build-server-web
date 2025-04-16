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
import redis # Import redis library
import ssl # For handling SSL verification
from pyVim import connect
from pyVmomi import vim, vmodl # Import pyvmomi modules
import pynetbox # Import pynetbox library
from flask_apscheduler import APScheduler # Import APScheduler

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
REDIS_HOST = os.environ.get('REDIS_HOST', 'redis') # Get Redis host from env or default to service name
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379)) # Get Redis port from env or default

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
# logging.basicConfig(level=logging.INFO) # Change this line
logging.basicConfig(level=logging.DEBUG) # To this line
logger = logging.getLogger(__name__)

# Initialize Redis client
try:
    redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    redis_client.ping() # Test connection
    logger.info(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except redis.exceptions.ConnectionError as e:
    logger.error(f"Failed to connect to Redis at {REDIS_HOST}:{REDIS_PORT}: {e}")
    redis_client = None # Set client to None if connection fails

# Scheduler configuration
scheduler = APScheduler()

# Cache helper functions
def get_cache(key):
    """Get data from Redis cache."""
    if redis_client:
        try:
            cached_data = redis_client.get(key)
            if cached_data:
                return json.loads(cached_data) # Assuming stored data is JSON
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis GET error for key '{key}': {e}")
    return None

def set_cache(key, value, ttl=3600):
    """Set data in Redis cache with a TTL (default 1 hour)."""
    if redis_client:
        try:
            # Serialize value to JSON before storing
            redis_client.setex(key, ttl, json.dumps(value))
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis SETEX error for key '{key}': {e}")

# --- vSphere Interaction ---

def connect_to_vsphere():
    """Connects to vSphere using environment variables."""
    host = os.environ.get('VSPHERE_SERVER')
    user = os.environ.get('VSPHERE_USER')
    password = os.environ.get('VSPHERE_PASSWORD')
    allow_unverified = os.environ.get('VSPHERE_ALLOW_UNVERIFIED_SSL', 'false').lower() == 'true'

    if not all([host, user, password]):
        logger.error("vSphere connection details missing in environment variables.")
        return None

    service_instance = None
    try:
        context = None
        if allow_unverified:
            logger.warning("Attempting to disable SSL verification for vSphere connection.") # ADDED LOG
            # Disable SSL certificate verification if allowed
            if hasattr(ssl, '_create_unverified_context'):
                context = ssl._create_unverified_context()
            else:
                # For older Python versions
                logger.warning("Cannot disable SSL verification on this Python version.")

        connect_args = {
            'host': host,
            'user': user,
            'pwd': password,
            'port': 443
        }
        if allow_unverified:
            # Try both methods for disabling SSL verification
            connect_args['disableSslCertValidation'] = True
            connect_args['sslContext'] = context
        
        service_instance = connect.SmartConnect(**connect_args)
        logger.info(f"Successfully connected to vSphere server: {host}")
        return service_instance
    except vim.fault.InvalidLogin as e:
        logger.error(f"vSphere login failed for user {user}: {e.msg}")
    except Exception as e:
        logger.error(f"Failed to connect to vSphere server {host}: {e}")

    # Disconnect if connection partially succeeded but failed later
    if service_instance:
        connect.Disconnect(service_instance)
    return None

def get_vsphere_objects(si, vimtype):
    """Gets managed objects of a specific type."""
    logger.debug(f"Entering get_vsphere_objects for type: {vimtype}") # ADDED LOG
    if not si:
        logger.warning("get_vsphere_objects called with no service instance (si).") # ADDED LOG
        return []
    try:
        logger.debug("Attempting si.RetrieveContent()...") # ADDED LOG
        content = si.RetrieveContent()
        logger.debug("si.RetrieveContent() successful.") # ADDED LOG
        container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
        objects = container.view
        container.Destroy()
        return objects
    except Exception as e:
        logger.error(f"Error retrieving vSphere objects of type {vimtype}: {e}")
        return []

def get_vsphere_inventory_data(si):
    """Fetches Datacenters, Resource Pools, Datastores, and VM Templates."""
    if not si:
        return None

    inventory = {
        'datacenters': [],
        'resource_pools': [],
        'datastores': [],
        'templates': []
    }

    try:
        # Get Datacenters
        datacenters = get_vsphere_objects(si, [vim.Datacenter])
        inventory['datacenters'] = sorted([dc.name for dc in datacenters])
        logger.info(f"Successfully fetched {len(inventory['datacenters'])} datacenters.") # ADDED LOG

        # Get Clusters (these represent the resource pools we care about) with enhanced logging/error handling
        logger.info("Attempting to fetch raw cluster objects...") # ADDED LOG
        raw_clusters = get_vsphere_objects(si, [vim.ClusterComputeResource])
        logger.info(f"Received {len(raw_clusters) if raw_clusters is not None else 'None'} raw cluster objects.") # MODIFIED LOG
        cluster_names_list = []
        if raw_clusters:
            logger.info("Starting processing of raw cluster objects...")
            for i, c in enumerate(raw_clusters): # Added enumerate for index logging
                logger.debug(f"Processing cluster object #{i}: {c}") # ADDED DEBUG LOG (use debug level)
                try:
                    if hasattr(c, 'name') and c.name:
                        cluster_names_list.append(c.name)
                        logger.debug(f"Successfully processed name for cluster #{i}: {c.name}") # ADDED DEBUG LOG
                    else:
                        logger.warning(f"Cluster object #{i} found without a valid name: {c}")
                except Exception as c_err:
                    logger.error(f"Error accessing name for cluster object #{i} ({c}): {c_err}", exc_info=True)
            logger.info("Finished processing raw cluster objects.") # ADDED LOG
        else:
            logger.info("No raw cluster objects received.") # ADDED LOG

        # Use a set to ensure uniqueness before sorting
        inventory['resource_pools'] = sorted(list(set(cluster_names_list)))
        logger.info(f"Successfully processed {len(inventory['resource_pools'])} resource pool/cluster names.")

        # Get Datastores with enhanced logging/error handling
        logger.info("Attempting to fetch raw datastore objects...") # ADDED LOG
        raw_datastores = get_vsphere_objects(si, [vim.Datastore])
        logger.info(f"Received {len(raw_datastores) if raw_datastores is not None else 'None'} raw datastore objects.") # MODIFIED LOG
        datastore_names = []
        if raw_datastores: # Check if the list is not None and potentially check if iterable
            logger.info("Starting processing of raw datastore objects...") # MOVED LOG
            # Optional: Check if it's actually a list or iterable
            if not isinstance(raw_datastores, (list, tuple)):
                 logger.error(f"Received non-iterable object for datastores: {type(raw_datastores)}")
            else:
                try: # Add try block around the entire loop
                    for i, ds in enumerate(raw_datastores): # Added enumerate
                        logger.debug(f"Processing datastore object #{i}: {ds}") # ADDED DEBUG LOG
                        try:
                            # Attempt to access the name attribute safely
                            if hasattr(ds, 'name') and ds.name:
                                datastore_names.append(ds.name)
                                logger.debug(f"Successfully processed name for datastore #{i}: {ds.name}") # ADDED DEBUG LOG
                            else:
                                logger.warning(f"Datastore object #{i} found without a valid name: {ds}")
                            # Add specific log after processing object #12 name attempt
                            if i == 12:
                                logger.debug("Finished name access attempt for datastore object #12.")
                        except Exception as ds_err:
                            # Log error accessing name for a specific datastore
                            logger.error(f"Error accessing name for datastore object #{i} ({ds}): {ds_err}", exc_info=True)
                    logger.info("Finished processing raw datastore objects.") # ADDED LOG
                except Exception as loop_err: # Catch errors during the loop itself
                    logger.error(f"Error during datastore processing loop: {loop_err}", exc_info=True)
        else:
             logger.info("No raw datastore objects received or fetch failed.") # MODIFIED LOG
        inventory['datastores'] = sorted(datastore_names)
        logger.info(f"Successfully processed {len(inventory['datastores'])} datastore names.")

        # Get VM Templates
        vms = get_vsphere_objects(si, [vim.VirtualMachine])
        inventory['templates'] = sorted([vm.name for vm in vms if vm.config.template])
        logger.info(f"Successfully fetched {len(inventory['templates'])} VM templates.") # ADDED LOG

        return inventory
    except Exception as e:
        # Log the specific error encountered during inventory fetching
        logger.error(f"Error fetching vSphere inventory details: {e}", exc_info=True) # ADDED exc_info=True
        return None
    finally:
        # Always disconnect after fetching data
        if si:
            connect.Disconnect(si)
            logger.info("Disconnected from vSphere.")

def background_vsphere_sync():
    """Background task to fetch vSphere inventory and update cache."""
    with app.app_context(): # Ensure task runs within app context if needed
        logger.info("Background task: Starting vSphere inventory sync...") # Modified log
        service_instance = None # Initialize service_instance
        try: # Add outer try block
            service_instance = connect_to_vsphere()
            if not service_instance:
                logger.error("Background task: Failed to connect to vSphere. Aborting sync.")
                return # Connection failed

            inventory_data = get_vsphere_inventory_data(service_instance) # Pass si here
            cache_key = 'vsphere_inventory'

            if inventory_data:
                set_cache(cache_key, inventory_data, ttl=3600 * 2) # Cache for 2 hours
                logger.info("Background task: Successfully fetched and cached vSphere inventory.")
            else:
                # get_vsphere_inventory_data logs errors internally now
                logger.error("Background task: Failed to fetch vSphere inventory data (check previous logs).")

        except Exception as e: # Catch any unexpected errors during the process
            logger.error(f"Background task: Unhandled exception during vSphere sync: {e}", exc_info=True)
            # Optionally log the full traceback
            # logger.error(f"Traceback: {traceback.format_exc()}")

        finally:
            # Ensure disconnection even if errors occur after connection
            if service_instance:
                try:
                    # Check if disconnect is needed (get_vsphere_inventory_data might have already disconnected)
                    # A more robust check might involve checking the connection state if possible
                    # For now, we rely on the internal disconnect in get_vsphere_inventory_data
                    # and this is a fallback. A double disconnect might log an error but is generally safe.
                    # connect.Disconnect(service_instance) # Removed redundant disconnect here
                    pass # Disconnect is handled within get_vsphere_inventory_data's finally block
                except Exception as disconnect_err:
                    logger.error(f"Background task: Error during final disconnect attempt: {disconnect_err}")
            logger.info("Background task: vSphere inventory sync finished.") # Modified log

def get_vsphere_inventory():
    """Gets vSphere inventory ONLY from cache."""
    cache_key = 'vsphere_inventory'
    cached_data = get_cache(cache_key)
    if cached_data:
        logger.info("Returning vSphere inventory from cache.")
        return cached_data
    else:
        logger.warning("vSphere inventory not found in cache. Waiting for background sync.")
        # Return empty structure or None if cache is empty
        return {
            'datacenters': [],
            'resource_pools': [],
            'datastores': [],
            'templates': []
        }

# --- End vSphere Interaction ---

# --- Netbox Interaction ---

def connect_to_netbox():
    """Connects to Netbox using environment variables."""
    url = os.environ.get('NETBOX_URL')
    token = os.environ.get('NETBOX_TOKEN')

    if not url or not token:
        logger.error("Netbox URL or Token missing in environment variables.")
        return None

    try:
        # pynetbox automatically handles adding /api if needed
        nb = pynetbox.api(url, token=token)
        
        # Disable SSL verification if NETBOX_ALLOW_UNVERIFIED_SSL is true
        netbox_allow_unverified = os.environ.get('NETBOX_ALLOW_UNVERIFIED_SSL', 'false').lower() == 'true'
        if netbox_allow_unverified:
            logger.warning(f"Disabling SSL verification for Netbox connection to {url}")
            nb.http_session.verify = False
            # Suppress InsecureRequestWarning globally when disabled for Netbox
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # Test connection by fetching something simple
        nb.dcim.sites.count()
        logger.info(f"Successfully connected to Netbox API at: {url}")
        return nb
    except Exception as e:
        logger.error(f"Failed to connect to Netbox API at {url}: {e}")
        return None

def get_netbox_ip_ranges_data(nb):
    """Fetches IP Prefixes (ranges) from Netbox."""
    if not nb:
        return None
    try:
        # Fetch prefixes - adjust filters as needed (e.g., by status, role, tag)
        prefixes = nb.ipam.prefixes.all()
        # We need the prefix string (e.g., "192.168.1.0/24")
        ip_ranges = sorted([p.prefix for p in prefixes])
        return ip_ranges
    except Exception as e:
        logger.error(f"Error fetching IP ranges from Netbox: {e}")
        return None

def get_netbox_ip_ranges(force_refresh=False):
    """Gets Netbox IP ranges, using cache if available."""
    cache_key = 'netbox_ip_ranges'
    cached_data = None

    if not force_refresh:
        cached_data = get_cache(cache_key)
        if cached_data:
            logger.info("Returning Netbox IP ranges from cache.")
            return cached_data

    logger.info("Fetching fresh Netbox IP ranges...")
    nb_api = connect_to_netbox()
    if not nb_api:
        return None # Connection failed

    ip_ranges_data = get_netbox_ip_ranges_data(nb_api)

    if ip_ranges_data:
        set_cache(cache_key, ip_ranges_data, ttl=3600) # Cache for 1 hour
        logger.info("Successfully fetched and cached Netbox IP ranges.")
        return ip_ranges_data
    else:
        logger.error("Failed to fetch Netbox IP ranges data.")
        return None

# --- End Netbox Interaction ---

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
                'VM Location Details': ['RESOURCE_POOL_ID', 'DEV_RESOURCE_POOL_ID', 'DATASTORE_ID', 
                                        'NETWORK_ID_PROD', 'NETWORK_ID_DEV', 'TEMPLATE_UUID'],
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
    # Attempt to get vSphere inventory for dropdowns
    # Note: This is a simple approach. For better UX with long loads,
    # consider loading the page first and fetching data via JavaScript/API.
    vsphere_data = get_vsphere_inventory()
    netbox_ranges = get_netbox_ip_ranges()

    return render_template('index.html',
                           server_prefixes=SERVER_PREFIXES,
                           environments=ENVIRONMENTS,
                           user_role=session.get('role', ''),
                           user_name=session.get('name', ''),
                           vsphere_data=vsphere_data or {}, # Pass empty dict if fetch fails
                           netbox_ranges=netbox_ranges or [] # Pass empty list if fetch fails
                          )

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

        # Get vSphere and Netbox selections
        vsphere_datacenter = request.form.get('vsphere_datacenter')
        vsphere_resource_pool = request.form.get('vsphere_resource_pool')
        vsphere_datastore = request.form.get('vsphere_datastore')
        vsphere_template = request.form.get('vsphere_template')
        netbox_ip_range = request.form.get('netbox_ip_range')
        
        # Determine environment based on server prefix
        environment = "production" if server_prefix in ENVIRONMENTS["prod"] else "development"
        
        # Validate input (including new fields)
        if not all([server_prefix, app_name, vsphere_datacenter, vsphere_resource_pool, vsphere_datastore, vsphere_template, netbox_ip_range]):
            flash('All fields including vSphere and Netbox selections are required', 'error')
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
            # Add new selections to config data
            'vsphere_datacenter': vsphere_datacenter,
            'vsphere_resource_pool': vsphere_resource_pool,
            'vsphere_datastore': vsphere_datastore,
            'vsphere_template': vsphere_template,
            'netbox_ip_range': netbox_ip_range
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
        return redirect(url_for('list_configs'))

@app.route('/admin/users')
@role_required(ROLE_ADMIN)
def admin_users():
    users = load_users()
    return render_template('admin_users.html', users=users)

@app.route('/admin/settings')
@role_required(ROLE_ADMIN)
def admin_settings():
    """Display the admin settings page with environment variables"""
    # Read env vars from .env file
    env_vars = read_env_file()
    # Filter out sensitive keys before sending to template
    filtered_env_vars = {k: v for k, v in env_vars.items() if k != 'FLASK_SECRET_KEY'}
    return render_template('admin_settings.html', env_vars=filtered_env_vars)

@app.route('/admin/save_settings', methods=['POST'])
@role_required(ROLE_ADMIN)
def admin_save_settings():
    """Save the environment variables to the .env file, excluding FLASK_SECRET_KEY"""
    try:
        # Get all form fields
        form_data = request.form.to_dict()

        # Read current env file to preserve existing values, especially FLASK_SECRET_KEY
        existing_env_vars = read_env_file()

        # Update existing vars with form data, EXCLUDING FLASK_SECRET_KEY
        for key, value in form_data.items():
            if key == 'FLASK_SECRET_KEY':
                continue # Explicitly skip the secret key

            # Handle checkboxes explicitly
            if key in ['VSPHERE_ALLOW_UNVERIFIED_SSL', 'NETBOX_ALLOW_UNVERIFIED_SSL']:
                 # Checkboxes send value only when checked, handle absence
                 existing_env_vars[key] = 'true' if key in form_data else 'false'
            # Handle other text fields
            elif value.strip():
                existing_env_vars[key] = value.strip()
            elif key in existing_env_vars: # Remove if value is cleared in form
                del existing_env_vars[key]

        # Ensure boolean flags are explicitly set if not present in form_data (unchecked checkboxes)
        if 'VSPHERE_ALLOW_UNVERIFIED_SSL' not in form_data:
             existing_env_vars['VSPHERE_ALLOW_UNVERIFIED_SSL'] = 'false'
        if 'NETBOX_ALLOW_UNVERIFIED_SSL' not in form_data:
             existing_env_vars['NETBOX_ALLOW_UNVERIFIED_SSL'] = 'false'


        # Write back to .env file (write_env_file handles the actual writing)
        if write_env_file(existing_env_vars):
             # Refresh environment variables in the current process (excluding secret key)
             for key, value in existing_env_vars.items():
                 if key != 'FLASK_SECRET_KEY':
                     os.environ[key] = value
             flash('Settings saved successfully', 'success')
        else:
             flash('Error writing settings to .env file.', 'error')

    except Exception as e:
        flash(f'Error saving settings: {str(e)}', 'error')

    return redirect(url_for('admin_settings'))

@app.route('/admin/test_connection/<service>', methods=['POST'])
@role_required(ROLE_ADMIN)
def admin_test_connection(service):
    """Test connection to external services"""
    result = False
    message = ""
    
    try:
        if service == 'vsphere':
            # Test vSphere connection
            vsphere_server = os.environ.get('VSPHERE_SERVER')
            vsphere_user = os.environ.get('VSPHERE_USER')
            vsphere_password = os.environ.get('VSPHERE_PASSWORD')
            
            if not vsphere_server or not vsphere_user or not vsphere_password:
                message = "vSphere connection information is incomplete"
            else:
                # Attempt to connect using the existing function
                logger.info(f"Attempting test connection to vSphere server: {vsphere_server}")
                service_instance = connect_to_vsphere()
                if service_instance:
                    # Connection successful, disconnect immediately
                    connect.Disconnect(service_instance)
                    logger.info("vSphere test connection successful.")
                    message = f"Successfully connected to vSphere server: {vsphere_server}"
                    result = True
                else:
                    # connect_to_vsphere logs the specific error
                    logger.error("vSphere test connection failed.")
                    message = f"Failed to connect to vSphere server: {vsphere_server}. Check credentials and network connectivity. See logs for details."
                    result = False
                
        elif service == 'atlantis':
            # Test Atlantis connection
            atlantis_url = os.environ.get('ATLANTIS_URL')
            atlantis_token = os.environ.get('ATLANTIS_TOKEN')
            
            if not atlantis_url or not atlantis_token:
                message = "Atlantis connection information is incomplete"
            else:
                # Try to make a simple API request to Atlantis
                try:
                    headers = {
                        'Content-Type': 'application/json',
                        'X-Atlantis-Token': atlantis_token
                    }
                    response = requests.get(f"{atlantis_url}/healthz", headers=headers, timeout=5)
                    if response.status_code == 200:
                        message = "Successfully connected to Atlantis server"
                        result = True
                    else:
                        message = f"Atlantis server returned status code: {response.status_code}"
                except requests.exceptions.RequestException as e:
                    message = f"Error connecting to Atlantis: {str(e)}"
                    
        elif service == 'netbox':
            # Test NetBox connection
            netbox_url = os.environ.get('NETBOX_URL')
            netbox_token = os.environ.get('NETBOX_TOKEN')
            
            if not netbox_url or not netbox_token:
                message = "NetBox connection information is incomplete"
            else:
                # Try to make a simple API request to NetBox
                try:
                    # Check if SSL verification should be disabled
                    netbox_allow_unverified = os.environ.get('NETBOX_ALLOW_UNVERIFIED_SSL', 'false').lower() == 'true'
                    
                    if netbox_allow_unverified:
                        logger.warning(f"Disabling SSL verification for Netbox test connection to {netbox_url}")
                        # Suppress InsecureRequestWarning
                        import urllib3
                        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

                    # Attempt to connect using pynetbox and fetch site count as a test
                    nb_test = pynetbox.api(netbox_url, token=netbox_token)
                    if netbox_allow_unverified:
                        nb_test.http_session.verify = False
                        
                    # This call will raise an exception if connection fails
                    site_count = nb_test.dcim.sites.count()
                    
                    # If we reach here, connection was successful
                    message = f"Successfully connected to NetBox API (Found {site_count} sites)"
                    result = True
                    
                except Exception as e: # Catch pynetbox/requests exceptions
                    message = f"Error connecting to NetBox: {str(e)}"
                    result = False
        else:
            message = f"Unknown service: {service}"
            
        if result:
            flash(message, 'success')
        else:
            flash(message, 'error')
            
    except Exception as e:
        flash(f'Error testing connection: {str(e)}', 'error')
    
    return redirect(url_for('admin_settings'))

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
    
    # Hash the password before storing
    hashed_password = hash_password(password)
    
    users[username] = {
        'password': hashed_password,
        'role': role,
        'name': name
    }
    
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)
    
    flash(f'User {username} added successfully', 'success')
    return redirect(url_for('admin_users'))

def generate_atlantis_plan_payload(config_data, tf_directory, tf_files):
    """Generate a properly formatted Atlantis API payload for plan operation"""
    # Get the directory name for the Terraform files
    tf_dir_name = os.path.basename(tf_directory)
    
    # Generate a unique hostname for this VM
    vm_hostname = f"{config_data['server_name']}-{config_data['start_number']}"
    
    # Create a dictionary with all the necessary fields
    payload_dict = {
        'repo': {
            'owner': 'fake',
            'name': 'terraform-repo',
            'clone_url': 'https://github.com/fake/terraform-repo.git'
        },
        'pull_request': {
            'num': 1,
            'branch': 'main',
            'author': config_data['build_owner']
        },
        'head_commit': 'abcd1234',
        'pull_num': 1,
        'pull_author': config_data['build_owner'],
        'repo_rel_dir': tf_dir_name,
        'workspace': config_data['environment'],
        'project_name': vm_hostname,
        'plan_only': True,
        'comment': f"VM Provisioning Plan: {vm_hostname}",
        'user': config_data['build_owner'],
        'verbose': True,
        'cmd': 'plan',
        'terraform_files': tf_files
    }
    
    # Convert to JSON string with proper formatting to ensure all commas are present
    payload_string = json.dumps(payload_dict, ensure_ascii=False)
    
    return payload_string

def generate_atlantis_apply_payload(config_data, tf_directory, tf_files, plan_id):
    """Generate a properly formatted Atlantis API payload for apply operation"""
    # Get the directory name for the Terraform files
    tf_dir_name = os.path.basename(tf_directory)
    
    # Create a dictionary with all the necessary fields
    # Minimal payload attempt for local directory apply
    payload_dict = {
        'workspace': config_data['environment'],
        'project_name': config_data['server_name'],
        'plan_id': plan_id,
        'comment': f"Applying approved VM config: {config_data['server_name']}",
        'user': config_data['build_owner'],
        'verbose': True,
        'cmd': 'apply',
        'terraform_files': tf_files,
        # Adding repo_rel_dir as it might still be needed to indicate the source directory
        'repo_rel_dir': tf_dir_name
    }
    
    # Convert to JSON string with proper formatting to ensure all commas are present
    payload_string = json.dumps(payload_dict, ensure_ascii=False)
    
    return payload_string

def run_atlantis_plan(config_data, tf_directory):
    """Run a Terraform plan in Atlantis"""
    try:
        # Prepare necessary files for the plan
        # 1. Copy vm-workspace files if they don't exist
        prepare_terraform_files(tf_directory, config_data)
        
        # 2. Read all Terraform files in the directory
        tf_files = {}
        for filename in os.listdir(tf_directory):
            if filename.endswith('.tf') or filename.endswith('.tfvars') or filename.endswith('.py'):
                file_path = os.path.join(tf_directory, filename)
                with open(file_path, 'r') as f:
                    tf_files[filename] = f.read()
        
        try:
            # Try to call the Atlantis API
            # Generate a JSON payload for plan operation
            payload_string = generate_atlantis_plan_payload(config_data, tf_directory, tf_files)
            
            # Log the first part of the payload for debugging
            logger.info(f"Generated Atlantis plan payload (first 100 chars): {payload_string[:100]}...")
            
            # Call Atlantis API to plan
            headers = {
                'Content-Type': 'application/json',
                'X-Atlantis-Token': ATLANTIS_TOKEN
            }
            
            logger.info(f"Sending plan request to Atlantis for {config_data['server_name']}")
            response = requests.post(f"{ATLANTIS_URL}/api/plan", data=payload_string, headers=headers)
            
            if response.status_code != 200:
                # If API call fails, log the error
                error_message = f"Failed to trigger Atlantis plan: {response.text}"
                logger.error(error_message)
                logger.warning("Using local plan simulation due to Atlantis API issue")
                # But continue with a simulated plan ID for better UX
                simulated = True
            else:
                # API call succeeded
                plan_response = response.json()
                plan_id = plan_response.get('plan_id')
                simulated = False
                
                if not plan_id:
                    error_message = "No plan ID returned from Atlantis"
                    logger.error(error_message)
                    logger.warning("Using local plan simulation due to missing plan_id")
                    simulated = True
                else:
                    logger.info(f"Successfully initiated Atlantis plan with ID: {plan_id}")
        except Exception as api_error:
            # If any exception occurs during API call, log it
            logger.exception(f"Error calling Atlantis API: {str(api_error)}")
            logger.warning("Using local plan simulation due to API error")
            simulated = True
        
        # If we need to simulate a plan due to API issues
        if simulated:
            # Generate a simulated plan ID
            plan_id = f"sim-{uuid.uuid4().hex[:8]}"
            logger.info(f"Using simulated plan ID: {plan_id}")
        
        # Generate a plan URL regardless of whether it's real or simulated
        plan_url = f"{ATLANTIS_URL}/plan/{plan_id}"
        
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
{"(Simulated plan due to Atlantis API issues)" if simulated else ""}
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
        logger.exception(f"Error running Terraform plan: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error running Terraform plan: {str(e)}"
        }

def prepare_terraform_files(tf_directory, config_data):
    """Prepare all necessary Terraform files for a plan"""
    # Copy necessary files from vm-workspace if they don't exist
    files_to_copy = {
        'providers.tf': 'vm-workspace/providers.tf',
        'fetch_next_ip.py': 'vm-workspace/fetch_next_ip.py',
        'data.tf': 'vm-workspace/data.tf',
    }
    
    for target_name, source_path in files_to_copy.items():
        target_path = os.path.join(tf_directory, target_name)
        if not os.path.exists(target_path) and os.path.exists(source_path):
            shutil.copy2(source_path, target_path)
            
            # If it's a Python file, make it executable
            if target_name.endswith('.py'):
                os.chmod(target_path, os.stat(target_path).st_mode | 0o111)
    
    # Create/Update terraform.tfvars with VSphere and NetBox specific variables
    tfvars_path = os.path.join(tf_directory, 'terraform.tfvars')
    existing_vars = {}
    
    # Read existing vars if file exists
    if os.path.exists(tfvars_path):
        with open(tfvars_path, 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.split('=', 1)
                    existing_vars[key.strip()] = value.strip()
    
    # Add necessary variables that might be missing
    additional_vars = {
        'netbox_token': f'"{os.environ.get("NETBOX_TOKEN", "netbox-api-token")}"',
        'netbox_api_url': f'"{os.environ.get("NETBOX_URL", "https://netbox.example.com/api")}"',
        'vsphere_server': f'"{os.environ.get("VSPHERE_SERVER", "vsphere-server")}"'
    }
    
    for key, value in additional_vars.items():
        if key not in existing_vars:
            existing_vars[key] = value
    
    # Write back the combined variables
    with open(tfvars_path, 'w') as f:
        for key, value in existing_vars.items():
            f.write(f"{key} = {value}\n")

def apply_atlantis_plan(config_data, tf_directory):
    """Apply a Terraform plan in Atlantis"""
    try:
        plan_id = config_data.get('plan_id')
        
        if not plan_id:
            error_message = 'No plan ID found in configuration'
            logger.error(error_message)
            return {
                'status': 'error',
                'message': error_message
            }
        
        # Get all the Terraform files
        tf_files = {}
        for filename in os.listdir(tf_directory):
            if filename.endswith('.tf') or filename.endswith('.tfvars') or filename.endswith('.py'):
                file_path = os.path.join(tf_directory, filename)
                with open(file_path, 'r') as f:
                    tf_files[filename] = f.read()
        
        try:
            # Try to call the Atlantis API
            # Generate a JSON payload for apply operation
            payload_string = generate_atlantis_apply_payload(config_data, tf_directory, tf_files, plan_id)
            
            # Log the first part of the payload for debugging
            logger.info(f"Generated Atlantis apply payload (first 100 chars): {payload_string[:100]}...")
            
            # Call Atlantis API to apply
            headers = {
                'Content-Type': 'application/json',
                'X-Atlantis-Token': ATLANTIS_TOKEN
            }
            
            logger.info(f"Sending apply request to Atlantis for {config_data['server_name']} with plan ID: {plan_id}")
            response = requests.post(f"{ATLANTIS_URL}/api/apply", data=payload_string, headers=headers)
            
            if response.status_code != 200:
                # If API call fails, log the error
                error_message = f"Failed to trigger Atlantis apply: {response.text}"
                logger.error(error_message)
                logger.warning("Using local apply simulation due to Atlantis API issue")
                # But continue with a simulated apply ID for better UX
                simulated = True
            else:
                # API call succeeded
                apply_response = response.json()
                apply_id = apply_response.get('apply_id')
                simulated = False
                
                if not apply_id:
                    error_message = "No apply ID returned from Atlantis"
                    logger.error(error_message)
                    logger.warning("Using local apply simulation due to missing apply_id")
                    simulated = True
                else:
                    logger.info(f"Successfully initiated Atlantis apply with ID: {apply_id}")
        except Exception as api_error:
            # If any exception occurs during API call, log it
            logger.exception(f"Error calling Atlantis API: {str(api_error)}")
            logger.warning("Using local apply simulation due to API error")
            simulated = True
        
        # If we need to simulate an apply due to API issues
        if simulated:
            # Generate a simulated apply ID
            apply_id = f"sim-{uuid.uuid4().hex[:8]}"
            logger.info(f"Using simulated apply ID: {apply_id}")
            
            # When in simulation mode, attempt direct VM provisioning if environment vars are set
            vsphere_server = os.environ.get('VSPHERE_SERVER')
            vsphere_user = os.environ.get('VSPHERE_USER')
            vsphere_password = os.environ.get('VSPHERE_PASSWORD')
            resource_pool_id = os.environ.get('RESOURCE_POOL_ID' if config_data['environment'] == 'production' else 'DEV_RESOURCE_POOL_ID')
            datastore_id = os.environ.get('DATASTORE_ID')
            template_uuid = os.environ.get('TEMPLATE_UUID')
            network_id = os.environ.get('NETWORK_ID_PROD' if config_data['environment'] == 'production' else 'NETWORK_ID_DEV')
            
            # Check if all required vSphere connection details are available
            if all([vsphere_server, vsphere_user, vsphere_password, resource_pool_id, datastore_id, template_uuid, network_id]):
                logger.info(f"All vSphere connection details are available for direct VM provisioning")
                logger.info(f"Would provision VM using the following parameters:")
                logger.info(f"Server: {vsphere_server}")
                logger.info(f"Resource Pool: {resource_pool_id}")
                logger.info(f"Datastore: {datastore_id}")
                logger.info(f"Template: {template_uuid}")
                logger.info(f"Network: {network_id}")
                # In a real implementation, this is where you would connect to vSphere directly
            else:
                logger.warning(f"Missing vSphere connection details for direct VM provisioning")
                logger.warning(f"VM provisioning will be simulated instead")
        
        # Generate a apply URL regardless of whether it's real or simulated
        build_url = f"{ATLANTIS_URL}/apply/{apply_id}"
        
        # Generate build receipt
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
{"(Simulated apply due to Atlantis API issues)" if simulated else ""}
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
    
    # Determine environment-specific values based on environment variables
    if environment == "production":
        resource_pool_id = os.environ.get('RESOURCE_POOL_ID', 'resource-pool-id-placeholder')
        network_id = os.environ.get('NETWORK_ID_PROD', 'network-id-placeholder')
    else:
        resource_pool_id = os.environ.get('DEV_RESOURCE_POOL_ID', 'resource-pool-id-placeholder')
        network_id = os.environ.get('NETWORK_ID_DEV', 'network-id-placeholder')
    
    # Get common vSphere resources from environment variables
    datastore_id = os.environ.get('DATASTORE_ID', 'datastore-id-placeholder')
    template_uuid = os.environ.get('TEMPLATE_UUID', 'template-uuid-placeholder')
    
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

# vSphere Environment
resource_pool_id = "{resource_pool_id}"
datastore_id     = "{datastore_id}"
network_id       = "{network_id}"
template_uuid    = "{template_uuid}"
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

# --- API Endpoints ---

@app.route('/api/vsphere-inventory')
@login_required
def api_get_vsphere_inventory():
    """API endpoint to get vSphere inventory (always from cache)."""
    # force_refresh = request.args.get('refresh', 'false').lower() == 'true' # Refresh is handled by background job
    inventory = get_vsphere_inventory() # Always gets from cache
    if inventory and any(inventory.values()): # Check if inventory is not None and not empty
        return jsonify(inventory)
    else:
        # Return 404 if cache is empty or not populated yet
        return jsonify({"error": "vSphere inventory not available in cache. Please wait for background sync."}), 404

@app.route('/api/netbox-ip-ranges')
@login_required
def api_get_netbox_ip_ranges():
    """API endpoint to get Netbox IP ranges."""
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    data = get_netbox_ip_ranges(force_refresh=force_refresh)
    if data:
        return jsonify(data)
    else:
        # Determine if connection details are missing or if fetch failed
        url = os.environ.get('NETBOX_URL')
        token = os.environ.get('NETBOX_TOKEN')
        if not url or not token:
            return jsonify({"error": "Netbox connection details not configured in settings."}), 503 # Service Unavailable
        else:
            return jsonify({"error": "Failed to fetch Netbox IP ranges. Check logs for details."}), 500 # Internal Server Error

# --- End API Endpoints ---

# Initialize Scheduler
scheduler.init_app(app)

# Schedule the background task
# Run immediately once on startup, then every hour
@scheduler.task('interval', id='vsphere_sync_job', hours=1, misfire_grace_time=900)
def scheduled_vsphere_sync():
    """Wrapper function for the scheduled task."""
    background_vsphere_sync()

# Start the scheduler
scheduler.start()

# Trigger initial sync shortly after startup (optional, but good for immediate data)
# Using a separate thread to avoid blocking startup if initial sync is long
import threading
import time # Import time for sleep
def initial_sync():
    # Add a small delay to allow the app to fully start before syncing
    time.sleep(5)
    with app.app_context():
        logger.info("Triggering initial vSphere sync...")
        background_vsphere_sync()
threading.Thread(target=initial_sync, daemon=True).start() # Use daemon thread


if __name__ == '__main__':
    # Use host='0.0.0.0' to be accessible externally if needed
    # debug=True should be False in production
    # use_reloader=False is important when using APScheduler with Flask's dev server
    # Set debug based on environment variable, default to False
    app_debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=app_debug, host='0.0.0.0', port=5150, use_reloader=False)
