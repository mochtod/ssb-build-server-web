"""
Test script for vSphere connection testing using the pyVmomi library.

This script allows for quick testing of the vSphere connection 
functionality in the SSB Build Server Web application.

Usage:
    python test_vsphere_connection.py --server hostname --user username --password password
"""
import argparse
import os
import logging
from vsphere_utils import test_vsphere_connection

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Test vSphere connectivity with provided credentials or environment variables."""
    parser = argparse.ArgumentParser(description='Test vSphere connection')
    parser.add_argument('--server', help='vSphere server hostname or IP')
    parser.add_argument('--user', help='vSphere username')
    parser.add_argument('--password', help='vSphere password')
    args = parser.parse_args()
    
    # Get credentials from args or environment variables
    server = args.server or os.environ.get('VSPHERE_SERVER')
    username = args.user or os.environ.get('VSPHERE_USER')
    password = args.password or os.environ.get('VSPHERE_PASSWORD')
    
    if not server or not username or not password:
        print("Error: vSphere connection information is incomplete.")
        print("Please provide --server, --user, and --password arguments or set")
        print("VSPHERE_SERVER, VSPHERE_USER, and VSPHERE_PASSWORD environment variables.")
        return
    
    print(f"Testing connection to {server} with user {username}...")
    
    result = test_vsphere_connection(server, username, password)
    
    if result['success']:
        print("✅ CONNECTION SUCCESSFUL")
        details = result.get('details', {})
        print(f"vSphere Version: {details.get('version', 'Unknown')}")
        print(f"vSphere Build: {details.get('build', 'Unknown')}")
        print(f"vSphere Name: {details.get('name', 'Unknown')}")
        print(f"vSphere Vendor: {details.get('vendor', 'Unknown')}")
        
        if 'datacenters' in details:
            print("\nDatacenters:")
            for dc in details['datacenters']:
                print(f" - {dc}")
    else:
        print("❌ CONNECTION FAILED")
        print(f"Error: {result['message']}")
    
    print("\nRaw result data:")
    print(result)

if __name__ == "__main__":
    main()
