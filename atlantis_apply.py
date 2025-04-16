#!/usr/bin/env python3
"""
Function to apply Atlantis plan for SSB Build Server Web application.

This stand-alone module defines the missing apply_atlantis_plan function
that was causing the "name is not defined" error.
"""
import os
import json
import logging
import datetime
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Atlantis API configuration
ATLANTIS_URL = os.environ.get("ATLANTIS_URL", "http://localhost:4141")
ATLANTIS_TOKEN = os.environ.get("ATLANTIS_TOKEN", "your-atlantis-api-secret")

def apply_atlantis_plan(config_data, tf_directory):
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
                'environment': config_data.get('environment', 'development')  # Critical: environment field must be present
            }
            
            # Convert to JSON string
            payload_string = json.dumps(payload_dict, ensure_ascii=False)
            
            # Call Atlantis API to apply
            headers = {
                'Content-Type': 'application/json',
                'X-Atlantis-Token': ATLANTIS_TOKEN
            }
            
            logger.info(f"Sending apply request to Atlantis for {config_data.get('server_name', 'unknown')}")
            response = requests.post(f"{ATLANTIS_URL}/api/apply", data=payload_string, headers=headers)
            
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
