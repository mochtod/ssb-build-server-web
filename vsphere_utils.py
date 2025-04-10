"""
VSphere connectivity utilities for the SSB Build Server application.
These functions provide connectivity testing to vSphere environments.
"""
import ssl
import logging
from pyVim import connect
from pyVmomi import vim
from urllib.error import URLError

# Set up logging
logger = logging.getLogger(__name__)

def test_vsphere_connection(server, username, password, port=443, timeout=5):
    """
    Test connection to vSphere server
    
    Args:
        server (str): vSphere server hostname or IP
        username (str): vSphere username
        password (str): vSphere password
        port (int): vSphere server port (default: 443)
        timeout (int): Connection timeout in seconds (default: 5)
        
    Returns:
        dict: Connection test result containing:
            - success (bool): True if connection successful, False otherwise
            - message (str): Description of the result or error message
            - details (dict): Additional details about the connection (when successful)
    """
    if not (server and username and password):
        return {
            'success': False,
            'message': 'vSphere connection information is incomplete. Server, username, and password are required.',
            'details': {}
        }

    try:
        # Create SSL context
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.verify_mode = ssl.CERT_NONE  # Disable certificate verification
        
        logger.info(f"Attempting to connect to vSphere server: {server}")
        
        # Attempt connection
        service_instance = connect.SmartConnect(
            host=server,
            user=username,
            pwd=password,
            port=port,
            sslContext=context
        )
        
        if not service_instance:
            return {
                'success': False,
                'message': 'Failed to connect to vSphere server. Connection returned null.',
                'details': {}
            }
        
        # Get vSphere server information
        content = service_instance.RetrieveContent()
        about = content.about
        
        # Get datacenter information
        datacenters = [dc.name for dc in content.rootFolder.childEntity 
                      if isinstance(dc, vim.Datacenter)]
        
        # Disconnect
        connect.Disconnect(service_instance)
        
        return {
            'success': True,
            'message': f'Successfully connected to vSphere server: {server}',
            'details': {
                'version': about.version,
                'build': about.build,
                'name': about.name,
                'vendor': about.vendor,
                'datacenters': datacenters
            }
        }
    
    except vim.fault.InvalidLogin:
        logger.error(f"Invalid login credentials for vSphere server: {server}")
        return {
            'success': False,
            'message': 'Invalid login credentials. Please check your username and password.',
            'details': {}
        }
    except URLError as e:
        logger.error(f"Connection error to vSphere server {server}: {str(e)}")
        return {
            'success': False,
            'message': f'Connection error: {str(e)}',
            'details': {}
        }
    except Exception as e:
        logger.exception(f"Error connecting to vSphere server {server}: {str(e)}")
        return {
            'success': False,
            'message': f'Error connecting to vSphere server: {str(e)}',
            'details': {}
        }
