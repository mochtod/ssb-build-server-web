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
from apply_atlantis_plan import apply_atlantis_plan # Import the function for Atlantis plan application

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
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    encoding='utf-8'  # Specify UTF-8 encoding to handle all characters
)
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
        'templates': [],
        'networks': [],
        # Add hierarchical structure for datacenter-specific resources
        'datacenter_resources': {}
    }

    try:
        # Get Datacenters
        datacenters = get_vsphere_objects(si, [vim.Datacenter])
        inventory['datacenters'] = sorted([dc.name for dc in datacenters])
        logger.info(f"Successfully fetched {len(inventory['datacenters'])} datacenters.") # ADDED LOG
        
        # Initialize datacenter resource mapping
        for dc in datacenters:
            inventory['datacenter_resources'][dc.name] = {
                'clusters': [],
                'datastores': [],
                'networks': []
            }        # Get Clusters (these represent the resource pools we care about) with enhanced logging/error handling
        logger.info("Attempting to fetch raw cluster objects...") # ADDED LOG
        raw_clusters = get_vsphere_objects(si, [vim.ClusterComputeResource])
        logger.info(f"Received {len(raw_clusters) if raw_clusters is not None else 'None'} raw cluster objects.") # MODIFIED LOG
        cluster_names_list = []
        
        # Enhanced cluster processing with datacenter mapping
        if raw_clusters:
            logger.info("Starting processing of raw cluster objects...")
            for i, cluster in enumerate(raw_clusters): # Added enumerate for index logging
                logger.debug(f"Processing cluster object #{i}: {cluster}") # ADDED DEBUG LOG (use debug level)
                try:
                    if hasattr(cluster, 'name') and cluster.name:
                        cluster_names_list.append(cluster.name)
                        logger.debug(f"Successfully processed name for cluster #{i}: {cluster.name}") # ADDED DEBUG LOG
                        
                        # Find parent datacenter for this cluster
                        parent_dc = None
                        try:
                            # Navigate up the inventory tree to find the parent datacenter
                            parent = cluster.parent
                            while parent and not isinstance(parent, vim.Datacenter):
                                parent = parent.parent
                            
                            if parent and isinstance(parent, vim.Datacenter):
                                parent_dc = parent.name
                                # Add cluster to its datacenter's resources
                                if parent_dc in inventory['datacenter_resources']:
                                    inventory['datacenter_resources'][parent_dc]['clusters'].append(cluster.name)
                                    logger.debug(f"Mapped cluster '{cluster.name}' to datacenter '{parent_dc}'")
                        except Exception as map_err:
                            logger.error(f"Error mapping cluster to datacenter: {map_err}", exc_info=True)
                    else:
                        logger.warning(f"Cluster object #{i} found without a valid name: {cluster}")
                except Exception as c_err:
                    logger.error(f"Error accessing name for cluster object #{i} ({cluster}): {c_err}", exc_info=True)
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
            logger.info("Starting processing of raw datastore objects...") # MOVED LOG            # Optional: Check if it's actually a list or iterable
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
                                
                                # Find parent datacenter for this datastore
                                try:
                                    # Get accessible hosts for this datastore
                                    host_mounts = ds.host
                                    if host_mounts:
                                        # Get first host mount
                                        host_mount = host_mounts[0]
                                        if hasattr(host_mount, 'key') and host_mount.key:
                                            # Navigate up to find datacenter
                                            parent = host_mount.key.parent
                                            while parent and not isinstance(parent, vim.Datacenter):
                                                parent = parent.parent
                                                
                                            if parent and isinstance(parent, vim.Datacenter):
                                                parent_dc = parent.name
                                                # Add datastore to its datacenter's resources
                                                if parent_dc in inventory['datacenter_resources']:
                                                    if ds.name not in inventory['datacenter_resources'][parent_dc]['datastores']:
                                                        inventory['datacenter_resources'][parent_dc]['datastores'].append(ds.name)
                                                        logger.debug(f"Mapped datastore '{ds.name}' to datacenter '{parent_dc}'")
                                except Exception as ds_map_err:
                                    logger.error(f"Error mapping datastore to datacenter: {ds_map_err}", exc_info=True)
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
        logger.info(f"Successfully processed {len(inventory['datastores'])} datastore names.")        # Get VM Templates
        vms = get_vsphere_objects(si, [vim.VirtualMachine])
        inventory['templates'] = sorted([vm.name for vm in vms if vm.config.template])
        logger.info(f"Successfully fetched {len(inventory['templates'])} VM templates.") # ADDED LOG        # Get Networks with datacenter mapping
        try:
            networks = get_vsphere_objects(si, [vim.Network])
            network_names = []
            
            if networks:
                logger.info(f"Processing {len(networks)} network objects...")
                for i, network in enumerate(networks):
                    try:
                        if hasattr(network, 'name') and network.name:
                            network_names.append(network.name)
                            
                            # Find parent datacenter for this network
                            try:
                                # Try to navigate up the object hierarchy
                                parent_dc = None
                                
                                # Try to navigate up until we find a datacenter
                                parent = network
                                if hasattr(network, 'parent'):
                                    parent = network.parent
                                    while parent and not isinstance(parent, vim.Datacenter):
                                        if hasattr(parent, 'parent'):
                                            parent = parent.parent
                                        else:
                                            break
                                
                                    if parent and isinstance(parent, vim.Datacenter):
                                        parent_dc = parent.name
                                        # Add network to its datacenter's resources
                                        if parent_dc in inventory['datacenter_resources']:
                                            if network.name not in inventory['datacenter_resources'][parent_dc]['networks']:
                                                inventory['datacenter_resources'][parent_dc]['networks'].append(network.name)
                                                logger.debug(f"Mapped network '{network.name}' to datacenter '{parent_dc}'")
                            except Exception as net_map_err:
                                logger.error(f"Error mapping network to datacenter: {net_map_err}", exc_info=True)
                    except Exception as net_err:
                        logger.error(f"Error processing network object #{i}: {net_err}", exc_info=True)
            
            inventory['networks'] = sorted(network_names)
            logger.info(f"Successfully fetched {len(inventory['networks'])} networks.")
        except Exception as net_err:
            logger.error(f"Error fetching networks: {net_err}", exc_info=True)
            # Add fallback networks from environment variables
            prod_network = os.environ.get('NETWORK_ID_PROD', 'Production Network')
            dev_network = os.environ.get('NETWORK_ID_DEV', 'Development Network')
            inventory['networks'] = [prod_network, dev_network] 
            logger.info(f"Using fallback networks from environment variables.")

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
        sync_status = {
            'status': 'in_progress',
            'step': 'connecting',
            'message': 'Connecting to vSphere server...',
            'progress': 10
        }
        # Store sync status in cache to make it available for API endpoint
        set_cache('vsphere_sync_status', sync_status, ttl=300)
        
        try: # Add outer try block
            service_instance = connect_to_vsphere()
            if not service_instance:
                logger.error("Background task: Failed to connect to vSphere. Aborting sync.")
                sync_status = {
                    'status': 'error',
                    'step': 'connecting',
                    'message': 'Failed to connect to vSphere server',
                    'progress': 0
                }
                set_cache('vsphere_sync_status', sync_status, ttl=300)
                return # Connection failed
            
            # Update sync status - connected successfully
            sync_status = {
                'status': 'in_progress',
                'step': 'fetching',
                'message': 'Connected to vSphere, fetching inventory data...',
                'progress': 30
            }
            set_cache('vsphere_sync_status', sync_status, ttl=300)
            
            # Assign the result to inventory_data
            inventory_data = get_vsphere_inventory_data(service_instance) # Pass si here
            cache_key = 'vsphere_inventory'

            if inventory_data:
                # Update sync status - processing data
                sync_status = {
                    'status': 'in_progress',
                    'step': 'processing',
                    'message': 'Processing vSphere inventory data...',
                    'progress': 70
                }
                set_cache('vsphere_sync_status', sync_status, ttl=300)
                
                # Try to import the new cache configuration
                try:
                    from cache_config import CACHE_TTL
                    # Use resource-specific TTL for better performance
                    ttl = CACHE_TTL.get('vsphere_inventory', 7200)  # Default to 2 hours if not configured
                    logger.info(f"Using configured TTL of {ttl} seconds for vSphere inventory")
                except ImportError:
                    # Fallback to original TTL if import fails
                    ttl = 3600 * 2  # 2 hours
                    logger.info(f"Using default TTL of {ttl} seconds for vSphere inventory")
                
                set_cache(cache_key, inventory_data, ttl=ttl)
                logger.info("Background task: Successfully fetched and cached vSphere inventory.")
                
                # Update sync status - completed successfully
                sync_status = {
                    'status': 'success',
                    'step': 'completed',
                    'message': f"Successfully fetched {len(inventory_data.get('datacenters', []))} datacenters, " +
                              f"{len(inventory_data.get('resource_pools', []))} resource pools, and " +
                              f"{len(inventory_data.get('templates', []))} templates",
                    'progress': 100
                }
                set_cache('vsphere_sync_status', sync_status, ttl=300)
            else:
                # get_vsphere_inventory_data logs errors internally now
                logger.error("Background task: Failed to fetch vSphere inventory data (check previous logs).")
                
                # Update sync status - failed to fetch data
                sync_status = {
                    'status': 'error',
                    'step': 'fetching',
                    'message': 'Failed to fetch vSphere inventory data',
                    'progress': 0
                }
                set_cache('vsphere_sync_status', sync_status, ttl=300)

        except Exception as e: # Catch any unexpected errors during the process
            logger.error(f"Background task: Unhandled exception during vSphere sync: {e}", exc_info=True)
            # Optionally log the full traceback
            # logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Update sync status - unexpected error
            sync_status = {
                'status': 'error',
                'step': 'unknown',
                'message': f'Unexpected error during vSphere sync: {str(e)}',
                'progress': 0
            }
            set_cache('vsphere_sync_status', sync_status, ttl=300)

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
            logger.info("Background task: vSphere inventory sync finished.")

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
            'templates': [],
            'networks': []
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
    """Fetches IP Prefixes (ranges) and their descriptions from Netbox."""
    if not nb:
        return None
    try:
        # Fetch prefixes - adjust filters as needed (e.g., by status, role, tag)
        prefixes = nb.ipam.prefixes.all()
        # Extract prefix string and description
        ip_ranges_data = []
        for p in prefixes:
            try:
                prefix_str = p.prefix
                description = p.description or "No description"  # Use default if description is empty
                ip_ranges_data.append({
                    'prefix': prefix_str,
                    'name': description
                })
            except AttributeError:
                logger.warning(f"Prefix object missing expected attributes: {p}")
            except Exception as e:
                logger.error(f"Unexpected error processing prefix {p}: {e}", exc_info=True)
                
        # Sort by name (description)
        ip_ranges_data.sort(key=lambda x: x.get('name', '').lower())
        return ip_ranges_data
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
        return None  # Connection failed

    ip_ranges_data = get_netbox_ip_ranges_data(nb_api)

    if ip_ranges_data:
        set_cache(cache_key, ip_ranges_data, ttl=3600)  # Cache for 1 hour
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
    # Fetch vSphere inventory from cache
    vsphere_data = get_vsphere_inventory()
    # Fetch Netbox IP ranges from cache (or trigger fetch if needed)
    netbox_ranges = get_netbox_ip_ranges() # Use existing function
    
    return render_template('index.html',
                           server_prefixes=SERVER_PREFIXES,
                           environments=ENVIRONMENTS,
                           user_role=session.get('role', ''),
                           user_name=session.get('name', ''),
                           vsphere_data=vsphere_data, # Pass fetched vSphere data
                           netbox_ranges=netbox_ranges if netbox_ranges else [] # Pass fetched Netbox ranges
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
        
        # Get path to Terraform files
        tf_directory = os.path.join(TERRAFORM_DIR, f"{request_id}_{timestamp}")
        
        # Check if we need a new plan before applying
        # This happens if a previous build was completed or if plan_id doesn't exist
        needs_replan = False
        if config_data.get('build_status') == 'submitted' or config_data.get('build_completed_at'):
            logger.info(f"Previous build detected for {request_id}. Running a new plan before apply.")
            needs_replan = True
        elif not config_data.get('plan_id'):
            logger.info(f"No plan ID found for {request_id}. Running a new plan before apply.")
            needs_replan = True
        
        # Run a new plan if needed
        if needs_replan:
            logger.info(f"Running new plan for {request_id} before apply")
            # Update status to indicate we're replanning
            config_data['plan_status'] = 'replanning'
            config_data['build_status'] = 'pending_replan'
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
                
            # Run the plan again, using a real Atlantis plan
            plan_result = run_atlantis_plan(config_data, tf_directory)
            
            if not plan_result or plan_result.get('status') != 'success':
                error_message = plan_result.get('message', 'Failed to create new plan') if plan_result else 'Plan process failed'
                flash(f'Failed to create new plan: {error_message}', 'error')
                return redirect(url_for('show_plan', request_id=request_id, timestamp=timestamp))
                
            # Update with new plan details
            config_data['plan_status'] = 'completed'
            config_data['atlantis_url'] = plan_result.get('atlantis_url', '')
            config_data['plan_log'] = plan_result.get('plan_log', '')
            config_data['plan_id'] = plan_result.get('plan_id', '')
            
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            flash('New real Atlantis plan created successfully, proceeding with build...', 'success')
        
        # Update build status
        config_data['build_status'] = 'building'
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        
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

def get_vsphere_terraform_vars():
    """Get vSphere authentication variables for Terraform"""
    # Get vSphere credentials from environment variables
    vsphere_vars = {
        'vsphere_user': os.environ.get('VSPHERE_USER', ''),
        'vsphere_password': os.environ.get('VSPHERE_PASSWORD', ''),
        'vsphere_server': os.environ.get('VSPHERE_SERVER', ''),
        'allow_unverified_ssl': 'true'  # Match the setting in your provider config
    }
    
    # Add any other required variables
    # These values are used in the Terraform apply but not necessarily in the plan
    vsphere_vars.update({
        'datacenter_id': os.environ.get('VSPHERE_DATACENTER_ID', ''),
        'vsphere_datacenter': os.environ.get('VSPHERE_DATACENTER', ''),
        'vsphere_insecure': 'true'
    })
    
    return vsphere_vars

def generate_atlantis_plan_payload(config_data, tf_directory, tf_files):
    """Generate a properly formatted Atlantis API payload for plan operation"""
    # Get the directory name for the Terraform files
    tf_dir_name = os.path.basename(os.path.normpath(tf_directory))
    
    # Generate a unique hostname for this VM
    vm_hostname = f"{config_data['server_name']}-{config_data['start_number']}"
    
    # Get vSphere credentials for Terraform to include in plan
    vsphere_vars = get_vsphere_terraform_vars()
    logger.info(f"Retrieved vSphere credentials for plan payload. Server: {vsphere_vars.get('vsphere_server', 'MISSING')}")
    
    # Read terraform.tfvars to include all variables in the payload
    additional_vars = {}
    tfvars_path = os.path.join(tf_directory, 'terraform.tfvars')
    if os.path.exists(tfvars_path):
        logger.info(f"Loading additional variables from {tfvars_path}")
        with open(tfvars_path, 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.split('=', 1)
                    additional_vars[key.strip()] = value.strip()
        
        # Merge with vsphere_vars, giving priority to existing values in vsphere_vars
        for key, value in additional_vars.items():
            if key not in vsphere_vars:
                vsphere_vars[key] = value
    
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
        'comment': f"VM Provisioning Plan: {vm_hostname}",
        'user': config_data['build_owner'],
        'verbose': True,
        'cmd': 'plan',             # Critical: ensure command is explicitly set to 'plan'
        'dir': '.',                # Critical: add the 'dir' field that's required
        'terraform_files': tf_files,
        'environment': config_data['environment'],  # Critical: environment field must be present
        # Add these missing fields required by Atlantis
        'atlantis_workflow': 'custom',             # Match your workflow defined in repo-config.yaml
        'autoplan': False,                         # Explicitly set to False for manual plans
        'parallel_plan': False,                    # Disable parallel planning
        'parallel_apply': False,                   # Disable parallel applying
        'terraform_version': '',                   # Let Atlantis use its default version
        'log_level': 'info',                       # Set log level
        'terraform_vars': vsphere_vars,            # Add vSphere and other variables
        'action': 'plan'                           # Explicitly set action field
    }
    
    # Add repository_id field which might be required by Atlantis
    payload_dict['repository_id'] = f"{payload_dict['repo']['owner']}/{payload_dict['repo']['name']}"
    
    # Add additional fields that might be required for the specific version of Atlantis
    payload_dict['command_name'] = 'plan'
    payload_dict['plan_requirements'] = []
    
    # Convert to JSON string with proper formatting to ensure all commas are present
    payload_string = json.dumps(payload_dict, ensure_ascii=False)
    
    return payload_string

def generate_atlantis_apply_payload(config_data, tf_directory):
    """Run a Terraform apply in Atlantis using the approved plan"""
    try:
        # Read all Terraform files in the directory
        tf_files = {}
        for filename in os.listdir(tf_directory):
            if filename.endswith('.tf') or filename.endswith('.tfvars') or filename.endswith('.py'):
                file_path = os.path.join(tf_directory, filename)
                with open(file_path, 'r') as f:
                    tf_files[filename] = f.read()
        
        # Get the plan ID from the config
        plan_id = config_data.get('plan_id')
        if not plan_id:
            logger.error("No plan ID found in configuration")
            return {
                'status': 'error',
                'message': "No plan ID found in configuration"
            }
        
        try:
            # Get vSphere credentials for Terraform
            vsphere_vars = get_vsphere_terraform_vars()
            logger.info(f"Retrieved vSphere credentials for apply payload. Server: {vsphere_vars.get('vsphere_server', 'MISSING')}")
            
            # Ensure we have the critical credentials
            if not vsphere_vars.get('vsphere_user') or not vsphere_vars.get('vsphere_password') or not vsphere_vars.get('vsphere_server'):
                logger.error("Missing critical vSphere credentials for apply operation")
                logger.error(f"Auth fields present: vsphere_user={bool(vsphere_vars.get('vsphere_user'))}, "
                            f"vsphere_password={bool(vsphere_vars.get('vsphere_password'))}, "
                            f"vsphere_server={bool(vsphere_vars.get('vsphere_server'))}")
                
                # Try to load from tfvars file as a backup
                tfvars_path = os.path.join(tf_directory, 'terraform.tfvars')
                if os.path.exists(tfvars_path):
                    logger.info(f"Attempting to load vSphere credentials from {tfvars_path}")
                    with open(tfvars_path, 'r') as f:
                        for line in f:
                            if '=' in line and not line.strip().startswith('#'):
                                key, value = line.split('=', 1)
                                key = key.strip()
                                value = value.strip()
                                if key in ['vsphere_user', 'vsphere_password', 'vsphere_server'] and not vsphere_vars.get(key):
                                    vsphere_vars[key] = value
                                    logger.info(f"Loaded {key} from tfvars file")
            
            # Enhance logging for troubleshooting
            logger.debug(f"Sending apply payload to Atlantis API for {config_data.get('server_name')}")
            logger.debug(f"Auth fields present after loading: vsphere_user={bool(vsphere_vars.get('vsphere_user'))}, "
                        f"vsphere_password={bool(vsphere_vars.get('vsphere_password'))}, "
                        f"vsphere_server={bool(vsphere_vars.get('vsphere_server'))}")
            
            # Read terraform.tfvars to include all variables in the payload
            additional_vars = {}
            tfvars_path = os.path.join(tf_directory, 'terraform.tfvars')
            if os.path.exists(tfvars_path):
                logger.info(f"Loading additional variables from {tfvars_path}")
                with open(tfvars_path, 'r') as f:
                    for line in f:
                        if '=' in line and not line.strip().startswith('#'):
                            key, value = line.split('=', 1)
                            additional_vars[key.strip()] = value.strip()
                
                # Merge with vsphere_vars, giving priority to existing values in vsphere_vars
                for key, value in additional_vars.items():
                    if key not in vsphere_vars:
                        vsphere_vars[key] = value
            
            # Generate a JSON payload for apply operation
            payload_dict = {
                'repo': {
                    'owner': 'fake',
                    'name': 'terraform-repo',
                    'clone_url': 'https://github.com/fake/terraform-repo.git'
                },
                'pull_request': {
                    'num': 1,
                    'branch': 'main',
                    'author': config_data.get('build_owner', 'Admin User')
                },
                'head_commit': 'abcd1234',
                'pull_num': 1,
                'pull_author': config_data.get('build_owner', 'Admin User'),
                'repo_rel_dir': os.path.basename(os.path.normpath(tf_directory)),
                'workspace': config_data.get('environment', 'development'),
                'project_name': config_data.get('server_name', 'unknown'),
                'plan_id': plan_id,
                'comment': f"Applying approved VM config: {config_data.get('server_name', 'unknown')}",
                'user': config_data.get('build_owner', 'Admin User'),
                'verbose': True,
                'cmd': 'apply',           # Critical: ensure command is explicitly set to 'apply'
                'dir': '.',               # Critical: add the 'dir' field that's required
                'terraform_files': tf_files,
                'environment': config_data.get('environment', 'development'),  # Critical: environment field must be present
                # Add these missing fields required by Atlantis
                'atlantis_workflow': 'custom',      # Match your workflow defined in repo-config.yaml
                'autoplan': False,                  # Explicitly set to False for manual applies
                'parallel_plan': False,             # Disable parallel planning
                'parallel_apply': False,            # Disable parallel applying
                'terraform_version': '',            # Let Atlantis use its default version
                'log_level': 'info',                # Set log level
                'terraform_vars': vsphere_vars,     # Add vSphere authentication variables
                'action': 'apply',                  # Explicitly set action
                'apply_requirements': ['approved']  # Apply requirements
            }
            
            # Convert to JSON string
            payload_string = json.dumps(payload_dict, ensure_ascii=False)
            
            # Call Atlantis API to apply
            headers = {
                'Content-Type': 'application/json',
                'X-Atlantis-Token': ATLANTIS_TOKEN
            }
            
            logger.info(f"Sending apply request to Atlantis for {config_data.get('server_name', 'unknown')}")
            logger.debug(f"Using vSphere credentials - Server: {vsphere_vars.get('vsphere_server')}, User: {vsphere_vars.get('vsphere_user')}")
            response = requests.post(
                f"{ATLANTIS_URL}/api/apply", 
                data=payload_string, 
                headers=headers
            )
            
            if response.status_code != 200:
                # If API call fails, log the error
                error_message = f"Failed to trigger Atlantis apply: {response.text}"
                logger.error(error_message)
                return {
                    'status': 'error',
                    'message': error_message
                }
            
            # API call succeeded
            apply_response = response.json()
            apply_id = apply_response.get('id', '')
            
            if not apply_id:
                error_message = "No apply ID returned from Atlantis"
                logger.error(error_message)
                return {
                    'status': 'error',
                    'message': error_message
                }
            
            logger.info(f"Successfully initiated Atlantis apply with ID: {apply_id}")
            
            # Generate apply URL
            apply_url = f"{ATLANTIS_URL}/apply/{apply_id}"
            
            # Generate a receipt
            build_receipt = f"""
Terraform Apply Initiated:
-------------------------
Apply ID: {apply_id}
Environment: {config_data.get('environment', 'development')}
Server: {config_data.get('server_name', 'unknown')}
Resources: {config_data.get('quantity', 1)} virtual machines
Initiated by: {config_data.get('build_owner', 'Admin User')}
Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Atlantis Apply URL: {apply_url}
            """
            
            return {
                'status': 'success',
                'build_url': apply_url,
                'build_receipt': build_receipt,
                'apply_id': apply_id
            }
            
        except Exception as api_error:
            # If any exception occurs during API call, log it
            logger.exception(f"Error calling Atlantis API: {str(api_error)}")
            return {
                'status': 'error',
                'message': f"Error calling Atlantis API: {str(api_error)}"
            }
        
    except Exception as e:
        logger.exception(f"Error applying Terraform plan: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error applying Terraform plan: {str(e)}"
        }

def run_atlantis_plan(config_data, tf_directory):
    """Run a Terraform plan in Atlantis"""
    try:
        logger.info(f"Starting Atlantis plan process for config: {config_data.get('server_name')} in {tf_directory}")
        logger.info(f"*** ATLANTIS PLAN CODE VERSION WITH FIXED FIELDS - 2025-04-16 ***")
        logger.info(f"*** ATLANTIS PLAN CODE VERSION WITH FIXED FIELDS - 2025-04-16 ***")
        logger.debug(f"Full config for plan: {config_data.get('server_name')} with environment {config_data.get('environment')}")
          # Create the .git directory to make it appear as a git repo
        git_dir = os.path.join(tf_directory, '.git')
        try:
            if not os.path.exists(git_dir):
                os.makedirs(git_dir, exist_ok=True)
                logger.info(f"Created fake .git directory at {git_dir} to simulate git repo")
                
                # Create refs directory structure
                refs_dir = os.path.join(git_dir, 'refs', 'heads')
                os.makedirs(refs_dir, exist_ok=True)
                logger.debug(f"Created fake .git/refs/heads directory structure")
                
                # Create a main branch reference file
                main_ref_path = os.path.join(refs_dir, 'main')
                with open(main_ref_path, 'w') as f:
                    f.write("0000000000000000000000000000000000000000\n")
                logger.debug(f"Created fake branch reference at {main_ref_path}")
                
                # Create a minimal .git/config file to make it appear as a valid repo
                git_config_path = os.path.join(git_dir, 'config')
                with open(git_config_path, 'w') as f:
                    f.write("""[core]
        repositoryformatversion = 0
        filemode = true
        bare = false
        logallrefupdates = true
[remote "origin"]
        url = https://github.com/fake/terraform-repo.git
        fetch = +refs/heads/*:refs/remotes/origin/*
[branch "main"]
        remote = origin
        merge = refs/heads/main
""")
                logger.info(f"Created fake .git/config file at {git_config_path}")
                
                # Create a HEAD file to indicate the current branch
                head_path = os.path.join(git_dir, 'HEAD')
                with open(head_path, 'w') as f:
                    f.write("ref: refs/heads/main\n")
                logger.info(f"Created fake .git/HEAD file at {head_path}")
            else:
                logger.info(f"Using existing .git directory at {git_dir}")
        except Exception as git_err:
            logger.error(f"Error creating fake Git repository structure: {git_err}", exc_info=True)
            return {
                'status': 'error',
                'message': f"Failed to create Git repository structure: {str(git_err)}"
            }
        
        # Prepare necessary files for the plan
        # 1. Copy vm-workspace files if they don't exist
        ensure_vsphere_provider_files(tf_directory)
          # 2. Read all Terraform files in the directory
        tf_files = {}
        for filename in os.listdir(tf_directory):
            if filename.endswith('.tf') or filename.endswith('.tfvars') or filename.endswith('.py'):
                file_path = os.path.join(tf_directory, filename)
                with open(file_path, 'r') as f:
                    tf_files[filename] = f.read()
                logger.debug(f"Read file {filename} for inclusion in Atlantis payload")
        
        try:
            # Try to call the Atlantis API
            # Generate a JSON payload for plan operation
            try:
                payload_string = generate_atlantis_plan_payload(config_data, tf_directory, tf_files)
                # Log the payload for debugging (first part only to avoid too much output)
                logger.info(f"Generated Atlantis plan payload (first 100 chars): {payload_string[:100]}...")
            except Exception as payload_err:
                logger.error(f"Error generating Atlantis plan payload: {payload_err}", exc_info=True)
                return {
                    'status': 'error',
                    'message': f"Failed to generate Atlantis payload: {str(payload_err)}"
                }
              # Call Atlantis API to plan
            headers = {
                'Content-Type': 'application/json',
                'X-Atlantis-Token': ATLANTIS_TOKEN
            }
            
            logger.info(f"Sending real plan request to Atlantis for {config_data['server_name']}")
            response = requests.post(
                f"{ATLANTIS_URL}/api/plan", 
                data=payload_string, 
                headers=headers
            )
            
            if response.status_code != 200:
                # If API call fails, log the error and return with proper error info
                error_message = f"Failed to trigger Atlantis plan: HTTP {response.status_code}"
                logger.error(error_message)
                try:
                    error_detail = response.json()
                    logger.error(f"{error_message} - Details: {error_detail}")
                except Exception:
                    # If response isn't valid JSON, log the raw text
                    logger.error(f"{error_message} - Response: {response.text}")
                
                # Include detailed error info in logs
                logger.error(f"Request URL: {ATLANTIS_URL}/api/plan")
                logger.error(f"Request Headers: {headers}")
                logger.error(f"Request Payload (first 100 chars): {payload_string[:100]}...")
                
                # Return error message immediately
                return {
                    'status': 'error',
                    'message': f"{error_message}. Check server logs for details."
                }
            
            # API call succeeded - parse the response
            try:
                plan_response = response.json()
                logger.info(f"Atlantis plan response received successfully")
                logger.debug(f"Full Atlantis plan response: {plan_response}")
            except json.JSONDecodeError as json_err:
                logger.error(f"Invalid JSON response from Atlantis API: {json_err}", exc_info=True)
                logger.error(f"Raw response text: {response.text[:500]}")  # Log first 500 chars of response
                return {
                    'status': 'error',
                    'message': "Invalid response received from Atlantis server. Check logs for details."
                }
              # Get the plan ID from the response
            # Look for either 'id' or 'plan_id' in the response
            plan_id = plan_response.get('id') or plan_response.get('plan_id')
            
            if not plan_id:
                logger.error(f"No plan ID found in Atlantis response: {plan_response}")
                return {
                    'status': 'error',
                    'message': "No plan ID returned from Atlantis. The server may be misconfigured."
                }
            
            logger.info(f"Successfully initiated Atlantis plan with ID: {plan_id}")
            
            # Generate a plan URL for the real plan
            try:
                plan_url = f"{ATLANTIS_URL}/plan/{plan_id}"
                logger.info(f"Generated Atlantis plan URL: {plan_url}")
                
                # Verify the plan URL is accessible
                url_check = requests.head(plan_url, timeout=5)
                if url_check.status_code >= 400:
                    logger.warning(f"Plan URL may not be accessible: {plan_url} (HTTP {url_check.status_code})")
            except Exception as url_err:
                logger.warning(f"Could not verify plan URL accessibility: {str(url_err)}")
                # Continue anyway as this is not critical
                plan_url = f"{ATLANTIS_URL}/plan/{plan_id}"
              # Generate plan log for real plan
            try:
                plan_log = f"""
Terraform Plan Output:
----------------------
Plan ID: {plan_id}
Environment: {config_data.get('environment', 'development')}
Server: {config_data.get('server_name', 'unknown')}
Planned Resources:
- {config_data.get('quantity', 1)} virtual machine(s)
- {len(config_data.get('additional_disks', []))} additional disk(s)

This plan will:
- Create {config_data.get('quantity', 1)} new VM(s)
- Configure networking and storage
- Register VMs with infrastructure management systems

Initiated at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Initiated by: {config_data.get('build_owner', 'Unknown')}

Atlantis Plan URL: {plan_url}
                """
                logger.info(f"Generated plan log summary for plan ID: {plan_id}")
            except Exception as log_err:
                logger.error(f"Error generating plan log: {log_err}", exc_info=True)
                # Create a simplified log if there's an error
                plan_log = f"Terraform Plan initiated with ID: {plan_id}\nAtlantis Plan URL: {plan_url}"
                logger.info("Generated simplified plan log due to error with detailed log")
        
        except Exception as api_error:
            # If any exception occurs during API call that wasn't caught by specific handlers
            logger.exception(f"Unhandled error during Atlantis API processing: {str(api_error)}")
            return {
                'status': 'error',
                'message': f"Error during Atlantis API processing: {str(api_error)}"
            }
        
        # Successfully created plan - return plan details
        logger.info(f"Returning successful plan result with plan URL: {plan_url}")
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

def ensure_vsphere_provider_files(tf_directory):
    """Ensure all files needed for vSphere provider functionality are present"""
    logger.info(f"Ensuring vSphere provider files are present in {tf_directory}")
    
    # Files to copy from vm-workspace if they don't exist
    required_files = {
        'providers.tf': 'vm-workspace/providers.tf',
        'data.tf': 'vm-workspace/data.tf',
        'fetch_next_ip.py': 'vm-workspace/fetch_next_ip.py',
    }
    
    # Copy module directory if it doesn't exist
    module_source = 'vm-workspace/modules'
    module_target = os.path.join(tf_directory, 'modules')
    if not os.path.exists(module_target) and os.path.exists(module_source):
        logger.info(f"Copying modules directory to {module_target}")
        shutil.copytree(module_source, module_target)
    
    # Copy individual files
    for target_name, source_path in required_files.items():
        target_path = os.path.join(tf_directory, target_name)
        if not os.path.exists(target_path) and os.path.exists(source_path):
            logger.info(f"Copying {source_path} to {target_path}")
            shutil.copy2(source_path, target_path)
            
            # If it's a Python file, make it executable
            if target_name.endswith('.py'):
                os.chmod(target_path, os.stat(target_path).st_mode | 0o111)
                
    return True

def prepare_terraform_files(tf_directory, config_data):
    """Prepare all necessary Terraform files for a plan"""
    # Ensure all vSphere provider files are present (including modules)
    ensure_vsphere_provider_files(tf_directory)
    
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
                    
    logger.info(f"Adding critical vSphere and NetBox variables to {tfvars_path}")
    
    # Add necessary variables that might be missing
    additional_vars = {
        # NetBox variables
        'netbox_token': f'"{os.environ.get("NETBOX_TOKEN", "netbox-api-token")}"',
        'netbox_api_url': f'"{os.environ.get("NETBOX_URL", "https://netbox.example.com/api")}"',
        
        # VSphere variables - CRITICAL for authentication during apply
        'vsphere_server': f'"{os.environ.get("VSPHERE_SERVER", "vsphere-server")}"',
        'vsphere_user': f'"{os.environ.get("VSPHERE_USER", "vsphere-user")}"',
        'vsphere_password': f'"{os.environ.get("VSPHERE_PASSWORD", "vsphere-password")}"',
        'allow_unverified_ssl': 'true',
        'vsphere_insecure': 'true',
        'vsphere_datacenter': f'"{os.environ.get("VSPHERE_DATACENTER", "default-datacenter")}"',
        
        # Additional VM resource variables
        'template_uuid': f'"{os.environ.get("TEMPLATE_UUID", "template-uuid-placeholder")}"',
        'datacenter_id': f'"{os.environ.get("VSPHERE_DATACENTER_ID", "datacenter-id-placeholder")}"'
    }
    
    # Add environment-specific variables
    environment = config_data.get('environment', 'development')
    if environment == 'production':
        additional_vars.update({
            'resource_pool_id': f'"{os.environ.get("RESOURCE_POOL_ID", "resource-pool-prod-placeholder")}"',
            'network_id': f'"{os.environ.get("NETWORK_ID_PROD", "network-id-prod-placeholder")}"'
        })
    else:
        additional_vars.update({
            'resource_pool_id': f'"{os.environ.get("DEV_RESOURCE_POOL_ID", "resource-pool-dev-placeholder")}"',
            'network_id': f'"{os.environ.get("NETWORK_ID_DEV", "network-id-dev-placeholder")}"'
        })
    
    # Always use the updated values from environment variables
    for key, value in additional_vars.items():
        existing_vars[key] = value
    
    # Write back the combined variables
    with open(tfvars_path, 'w') as f:
        f.write("# Updated with critical vSphere credentials on {}\n".format(
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        for key, value in existing_vars.items():
            f.write(f"{key} = {value}\n")
            
    logger.info(f"Successfully prepared Terraform files in {tf_directory} with critical vSphere variables")

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

# --- API Endpoints for vSphere Resources ---

@app.route('/api/vsphere/datacenter/<datacenter>/pools')
@login_required
def api_get_resource_pools_for_datacenter(datacenter):
    """API endpoint to get resource pools for a specific datacenter."""
    try:
        # Get cached vSphere inventory
        vsphere_data = get_vsphere_inventory()
        
        # Check if inventory data exists and has datacenter resources
        if not vsphere_data or 'datacenter_resources' not in vsphere_data:
            logger.warning(f"No datacenter resources found in vSphere inventory data for datacenter: {datacenter}")
            return jsonify([])
        
        # Try to get from datacenter-specific cache first
        cache_key = f'vsphere_pools_{datacenter}'
        cached_pools = get_cache(cache_key)
        
        if cached_pools:
            logger.debug(f"Using cached resource pools for datacenter: {datacenter}")
            return jsonify(cached_pools)
            
        logger.debug(f"Fetching resource pools for datacenter: {datacenter}")
        
        # Check if this exact datacenter exists in our hierarchical structure
        if datacenter in vsphere_data['datacenter_resources']:
            # Great! We have directly mapped clusters for this datacenter
            clusters = vsphere_data['datacenter_resources'][datacenter]['clusters']
            logger.debug(f"Found {len(clusters)} directly mapped clusters for datacenter: {datacenter}")
            
            filtered_pools = []
            for cluster in clusters:
                filtered_pools.append({
                    "id": cluster,
                    "name": cluster
                })
                
            # Cache the results for this datacenter
            if filtered_pools:
                set_cache(cache_key, filtered_pools, ttl=3600)  # Cache for 1 hour
            
            return jsonify(filtered_pools)
        
        # Datacenter not found or no direct mapping, use the fallback approach
        logger.warning(f"No direct mapping found for datacenter: {datacenter}. Using fallback approach.")
        
        # Normalize datacenter name for more flexible matching
        datacenter_normalized = datacenter.lower().replace('-', '').replace('_', '').replace(' ', '')
        
        # Filter resource pools using original fallback logic...
        filtered_pools = []
        for pool in vsphere_data.get('resource_pools', []):
            # Original flexible matching logic...
            pool_name = pool
            belongs_to_datacenter = False
            display_name = pool_name  # Default display name
            
            # Check for exact match (for standalone cluster names)
            if pool == datacenter:
                belongs_to_datacenter = True
                logger.debug(f"Pool '{pool}' matched exact datacenter name '{datacenter}'")
            
            # Check for path format
            elif '/' in pool:
                parts = pool.split('/')
                if parts[0] == datacenter:
                    belongs_to_datacenter = True
                    # Display just the cluster part without datacenter prefix
                    if len(parts) > 1:
                        display_name = '/'.join(parts[1:])
                    logger.debug(f"Pool '{pool}' matched path-based datacenter '{datacenter}'")
            
            # Check for partial match in name
            else:
                normalized_pool = pool.lower().replace('-', '').replace('_', '').replace(' ', '')
                
                # Common datacenter prefix/suffix checks
                if "np" in datacenter_normalized and "np" in normalized_pool:
                    belongs_to_datacenter = True
                    logger.debug(f"Pool '{pool}' matched 'np' in datacenter '{datacenter}'")
                elif "prod" in datacenter_normalized and "prod" in normalized_pool:
                    belongs_to_datacenter = True
                    logger.debug(f"Pool '{pool}' matched 'prod' in datacenter '{datacenter}'")
                # Partial name match
                elif any(part.lower() in normalized_pool for part in datacenter.lower().split()):
                    belongs_to_datacenter = True
                    logger.debug(f"Pool '{pool}' matched partial datacenter name '{datacenter}'")
            
            # If no specific datacenter is found, show all pools
            if datacenter.lower() == 'all' or datacenter.lower() == 'any':
                belongs_to_datacenter = True
                
            # Add pool with proper structure if it belongs to the datacenter
            if belongs_to_datacenter:
                filtered_pools.append({
                    "id": pool,
                    "name": display_name
                })
        
        # Cache the results for this datacenter to avoid repeated filtering
        if filtered_pools:
            set_cache(cache_key, filtered_pools, ttl=3600)  # Cache for 1 hour
            
        # Return fallback pools if no matches
        if not filtered_pools:
            logger.warning(f"No resource pools matched for datacenter '{datacenter}'. Using fallback pools.")
            fallback_pools = []
            for pool in vsphere_data.get('resource_pools', [])[:10]:
                fallback_pools.append({
                    "id": pool,
                    "name": pool
                })
            filtered_pools = fallback_pools
            
        logger.debug(f"Returning {len(filtered_pools)} resource pools for datacenter {datacenter}")
        return jsonify(filtered_pools)
    except Exception as e:
        logger.error(f"Error fetching resource pools for datacenter {datacenter}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/vsphere/datacenter/<datacenter>/pool/<path:resource_pool>/datastores')
@login_required
def api_get_datastores_for_resource_pool(datacenter, resource_pool):
    """API endpoint to get datastores for a specific datacenter and resource pool."""
    try:
        # Get cached vSphere inventory
        vsphere_data = get_vsphere_inventory()
        
        # Check if inventory data exists and has datacenter resources
        if not vsphere_data or 'datacenter_resources' not in vsphere_data:
            logger.warning(f"No datacenter resources found in vSphere inventory data for datacenter: {datacenter}")
            return jsonify([])
        
        logger.debug(f"Fetching datastores for datacenter: {datacenter}, resource_pool: {resource_pool}")
        
        # Try direct mapping first - get datastores for this datacenter
        dc_datastores = []
        if datacenter in vsphere_data['datacenter_resources']:
            dc_datastores = vsphere_data['datacenter_resources'][datacenter]['datastores']
            logger.debug(f"Found {len(dc_datastores)} directly mapped datastores for datacenter: {datacenter}")
        
        # If no datacenter-specific datastores found, fall back to all datastores
        if not dc_datastores:
            logger.warning(f"No datacenter-specific datastores found for {datacenter}, using global datastores")
            dc_datastores = vsphere_data.get('datastores', [])
        
        # First filter out any datastores ending with 'local'
        non_local_datastores = []
        for ds in dc_datastores:
            if not (ds.lower().endswith('local') or '_local' in ds.lower()):
                non_local_datastores.append(ds)
        
        # Now check if we need to filter further based on the cluster
        filtered_datastores = []
        cluster_name = resource_pool.lower()
        
        # If the resource pool name contains a cluster identifier, try to find distributed datastores for that cluster
        distributed_datastores = []
        if any(cluster_id in cluster_name for cluster_id in ['cl', 'cluster']):
            # Extract cluster number if present
            cluster_number = ""
            import re
            match = re.search(r'cl(\d+)', cluster_name)
            if match:
                cluster_number = match.group(1)
                logger.debug(f"Detected cluster number: {cluster_number}")
            
            # Look for distributed datastores specific to this cluster
            for ds in non_local_datastores:
                ds_lower = ds.lower()
                is_distributed = any(pattern in ds_lower for pattern in ['vsan', 'shared', 'dist', 'distributed'])
                matches_cluster = cluster_number and cluster_number in ds_lower
                
                if is_distributed or matches_cluster:
                    distributed_datastores.append(ds)
        
        # Use distributed datastores if found, otherwise fall back to non-local datastores
        datastores_to_use = distributed_datastores if distributed_datastores else non_local_datastores
        
        # Format the datastores for the response
        for ds in datastores_to_use:
            filtered_datastores.append({
                "id": ds,
                "name": ds
            })
        
        # If we ended up with no datastores, fall back to showing all non-local datastores
        if not filtered_datastores and non_local_datastores:
            logger.warning(f"No matching distributed datastores found for {resource_pool}, showing all non-local datastores")
            for ds in non_local_datastores:
                filtered_datastores.append({
                    "id": ds,
                    "name": ds
                })
        
        logger.debug(f"Returning {len(filtered_datastores)} datastores for datacenter {datacenter} and resource pool {resource_pool}")
        return jsonify(filtered_datastores)
    except Exception as e:
        logger.error(f"Error fetching datastores for datacenter {datacenter} and resource pool {resource_pool}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/vsphere/datacenter/<datacenter>/pool/<path:resource_pool>/templates')
@login_required
def api_get_templates_for_resource_pool(datacenter, resource_pool):
    """API endpoint to get VM templates for a specific datacenter and resource pool."""
    try:
        # Get cached vSphere inventory
        vsphere_data = get_vsphere_inventory()
        
        # Check if inventory data exists and has templates
        if not vsphere_data or not vsphere_data.get('templates'):
            logger.warning(f"No templates found in vSphere inventory data for resource pool: {resource_pool}")
            return jsonify([])

        logger.debug(f"Fetching templates for datacenter: {datacenter}, resource_pool: {resource_pool}")
        logger.debug(f"Available templates: {vsphere_data.get('templates')}")

        # In a production environment, this would use your hierarchical loader to get only templates
        # in the specific cluster/resource pool
        # Here we're returning all templates with proper structure
        filtered_templates = []
        templates_data = vsphere_data.get('templates', [])
        
        # Handle case where templates might be a list of strings or objects
        for template in templates_data:
            if isinstance(template, dict) and 'name' in template:
                # If it's already a dict with name
                filtered_templates.append({
                    "id": template.get('id', template['name']),
                    "name": template['name']
                })
            else:
                # Treat as a string template name
                filtered_templates.append({
                    "id": template,
                    "name": template
                })
        
        logger.debug(f"Returning {len(filtered_templates)} templates for resource pool {resource_pool}")
        return jsonify(filtered_templates)
    except Exception as e:
        logger.error(f"Error fetching templates for resource pool {resource_pool}: {e}", exc_info=True)
        return jsonify({"error": f"Failed to fetch templates: {str(e)}"}), 500

@app.route('/api/vsphere/datacenter/<datacenter>/pool/<path:resource_pool>/networks')
@login_required
def api_get_networks_for_resource_pool(datacenter, resource_pool):
    """API endpoint to get networks for a specific datacenter and resource pool."""
    try:
        # Get cached vSphere inventory
        vsphere_data = get_vsphere_inventory()
        
        # Check if inventory data exists and has datacenter resources
        if not vsphere_data or 'datacenter_resources' not in vsphere_data:
            logger.warning(f"No datacenter resources found in vSphere inventory data for datacenter: {datacenter}")
            # Fall back to environment variables
            environment = "development"
            if "prod" in resource_pool.lower():
                environment = "production"
                
            if environment == "production":
                network_id = os.environ.get('NETWORK_ID_PROD', 'network-id-placeholder')
                network_name = "Production Network"
            else:
                network_id = os.environ.get('NETWORK_ID_DEV', 'network-id-placeholder')
                network_name = "Development Network"
            
            return jsonify([{
                "id": network_id,
                "name": network_name
            }])
        
        logger.debug(f"Fetching networks for datacenter: {datacenter}, resource_pool: {resource_pool}")
        
        # Try direct mapping first - get networks for this datacenter
        dc_networks = []
        if datacenter in vsphere_data['datacenter_resources']:
            dc_networks = vsphere_data['datacenter_resources'][datacenter]['networks']
            logger.debug(f"Found {len(dc_networks)} directly mapped networks for datacenter: {datacenter}")
        
        # If no datacenter-specific networks found, fall back to all networks
        if not dc_networks:
            logger.warning(f"No datacenter-specific networks found for {datacenter}, using global networks")
            dc_networks = vsphere_data.get('networks', [])
        
        # Get the cluster name from the resource pool
        cluster_name = resource_pool.lower()
        
        # Filter networks based on the selected cluster/resource pool
        cluster_specific_networks = []
        
        # Extract cluster number if present
        cluster_number = ""
        import re
        match = re.search(r'cl(\d+)', cluster_name)
        if match:
            cluster_number = match.group(1)
            logger.debug(f"Detected cluster number: {cluster_number}")
            
        # Look for networks that match the cluster naming pattern
        for network in dc_networks:
            network_lower = network.lower()
            
            # Check if network name matches the cluster
            matches_cluster = False
            
            # Look for cluster number in network name
            if cluster_number and cluster_number in network_lower:
                matches_cluster = True
                logger.debug(f"Network '{network}' matched cluster number '{cluster_number}'")
                
            # Look for cluster environment indicator in network name
            if any(env_marker in cluster_name and env_marker in network_lower 
                   for env_marker in ['np', 'nonprod', 'prod', 'dev', 'int', 'test']):
                matches_cluster = True
                logger.debug(f"Network '{network}' matched environment marker in '{cluster_name}'")
                
            # Check for direct cluster name subset
            cluster_parts = cluster_name.split('-')
            for part in cluster_parts:
                if len(part) > 2 and part in network_lower:
                    matches_cluster = True
                    logger.debug(f"Network '{network}' matched cluster part '{part}'")
                    
            if matches_cluster:
                cluster_specific_networks.append(network)
        
        # Determine which networks to use
        filtered_networks = []
        if cluster_specific_networks:
            filtered_networks = cluster_specific_networks
        else:
            # Fall back to environment-based filtering
            logger.debug(f"No cluster-specific networks found for {resource_pool}, filtering by environment")
            
            # Determine environment from the cluster name
            is_prod = any(prod_marker in cluster_name for prod_marker in ['prod', 'pr'])
            is_nonprod = any(nonprod_marker in cluster_name for nonprod_marker in ['np', 'nonprod', 'dev', 'int', 'test'])
            
            # Filter networks by environment indicators
            for network in dc_networks:
                network_lower = network.lower()
                
                if is_prod and any(prod_marker in network_lower for prod_marker in ['prod', 'pr']):
                    filtered_networks.append(network)
                elif is_nonprod and any(nonprod_marker in network_lower for nonprod_marker in ['np', 'nonprod', 'dev', 'int', 'test']):
                    filtered_networks.append(network)
            
            # If still no networks found, use all datacenter networks
            if not filtered_networks:
                logger.debug(f"No environment-specific networks found, using all datacenter networks")
                filtered_networks = dc_networks
        
        # Format the networks for the response
        network_objects = []
        for network in filtered_networks:
            network_objects.append({
                "id": network,
                "name": network
            })
        
        logger.debug(f"Returning {len(network_objects)} networks for datacenter {datacenter} and resource pool {resource_pool}")
        return jsonify(network_objects)
    except Exception as e:
        logger.error(f"Error fetching networks for datacenter {datacenter} and resource pool {resource_pool}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# --- End API Endpoints for vSphere Resources ---

# Add a status endpoint for vSphere sync
@app.route('/api/vsphere-sync-status')
@login_required
def api_get_vsphere_sync_status():
    """API endpoint to get the current status of vSphere synchronization."""
    try:
        # Try to get detailed sync status from cache first
        sync_status = get_cache('vsphere_sync_status')
        
        # Check vsphere inventory data
        vsphere_data = get_vsphere_inventory()
        has_data = vsphere_data and len(vsphere_data.get('datacenters', [])) > 0
        
        # Initialize default result
        result = {
            "status": "in_progress",
            "message": "vSphere data synchronization in progress...",
            "completed": False,
            "has_data": has_data,
            "progress": 50  # Default progress value
        }
        
        # If we have detailed sync status, use it
        if sync_status:
            # Update with available status info
            result["status"] = sync_status.get('status', result["status"])
            result["message"] = sync_status.get('message', result["message"])
            result["progress"] = sync_status.get('progress', result["progress"])
            
            # Determine if completed based on status
            if sync_status.get('status') in ['success', 'error']:
                result["completed"] = True
        else:
            # Fallback logic if no sync status is available
            if has_data:
                # We have data, so sync must have completed successfully at some point
                result["status"] = "success"
                result["message"] = f"vSphere data loaded successfully with {len(vsphere_data.get('datacenters'))} datacenters"
                result["completed"] = True
                result["progress"] = 100
            elif get_cache('vsphere_inventory') is not None:
                # We tried to sync but didn't get any datacenters - likely an error
                result["status"] = "error"
                result["message"] = "Failed to load vSphere data. Check logs for errors."
                result["completed"] = True
                result["progress"] = 0
            
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error checking vSphere sync status: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error checking status: {str(e)}",
            "completed": False,
            "has_data": False,
            "progress": 0
        }), 500

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
    # debug=True should be False in production    # use_reloader=False is important when using APScheduler with Flask's dev server
    # Set debug based on environment variable, default to False    
    app_debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=app_debug, host='0.0.0.0', port=5150, use_reloader=False)
