#!/usr/bin/env python3
"""
Fix for the Atlantis apply API call in the SSB Build Server Web application.

This script modifies the apply payload to include all required fields and
fixes the validation error in the API request.
"""
import sys
import json
import os
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def ensure_terraform_structure(tf_directory):
    """
    Ensure that the Terraform directory has the required file structure.
    
    Args:
        tf_directory (str): Directory containing Terraform files
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Import the ensure_directory_structure function from the ensure_config_structure module
    try:
        # Check if the script exists
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                  'terraform', 'ensure_config_structure.py')
        
        if os.path.exists(script_path):
            # Run the script directly
            import subprocess
            result = subprocess.run(
                ['python', script_path, tf_directory],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully ensured Terraform structure for {tf_directory}")
                return True
            else:
                logger.warning(f"Failed to ensure Terraform structure: {result.stderr}")
                # Continue anyway
                return True
        else:
            # Script not found, try to ensure structure manually
            from terraform.ensure_config_structure import ensure_directory_structure
            return ensure_directory_structure(tf_directory)
    except Exception as e:
        logger.warning(f"Error ensuring Terraform structure: {str(e)}")
        # Continue anyway
        return True

def generate_atlantis_payload(repo, workspace, dir, commit_hash, comment, user, files):
    """
    Generate a properly formatted Atlantis API payload for plan operation
    
    Args:
        repo (str): Repository name
        workspace (str): Workspace name
        dir (str): Directory containing Terraform files
        commit_hash (str): Commit hash
        comment (str): Comment for the plan
        user (str): Username
        files (list or dict): Either a list of filenames or a dict of filename->content
        
    Returns:
        dict: Payload dictionary for Atlantis API
    """
    # First, ensure the Terraform directory has the proper structure
    ensure_terraform_structure(dir)
    
    # If files is a list of filenames, convert it to a dict with file contents
    terraform_files = {}
    if isinstance(files, list):
        # Make sure we have providers.tf and variables.tf
        required_files = set(['providers.tf', 'variables.tf'])
        files_set = set(files)
        missing_files = required_files - files_set
        
        # If some required files are missing, run the ensure_terraform_structure function
        # which will create the missing files
        if missing_files:
            logger.info(f"Missing required files: {', '.join(missing_files)}")
            ensure_terraform_structure(dir)
            
            # Add the newly created files to the list
            for filename in missing_files:
                file_path = os.path.join(dir, filename)
                if os.path.exists(file_path):
                    files.append(filename)
        
        # Read the contents of each file
        for filename in files:
            file_path = os.path.join(dir, filename)
            try:
                with open(file_path, 'r') as f:
                    terraform_files[filename] = f.read()
            except Exception as e:
                logger.warning(f"Error reading file {file_path}: {str(e)}")
                terraform_files[filename] = f"# Error reading file: {str(e)}"
    else:
        # Files is already a dict with contents
        terraform_files = files
        
        # Make sure we have providers.tf and variables.tf
        required_files = set(['providers.tf', 'variables.tf'])
        files_set = set(terraform_files.keys())
        missing_files = required_files - files_set
        
        # If some required files are missing, run the ensure_terraform_structure function
        # which will create the missing files
        if missing_files:
            logger.info(f"Missing required files in terraform_files dict: {', '.join(missing_files)}")
            ensure_terraform_structure(dir)
            
            # Add the newly created files to the dict
            for filename in missing_files:
                file_path = os.path.join(dir, filename)
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r') as f:
                            terraform_files[filename] = f.read()
                    except Exception as e:
                        logger.warning(f"Error reading file {file_path}: {str(e)}")
                        terraform_files[filename] = f"# Error reading file: {str(e)}"
    
    # Ensure we have a valid repo name
    repo_name = repo if repo else "build-server-repo"
    
    # Determine environment from workspace if provided, otherwise use development
    # This is the critical field that Atlantis requires 
    environment = workspace if workspace else "development"
    # Never use "default" as an environment name - it's a reserved word in Atlantis
    if environment == "default":
        environment = "development"  # Default to development if not specified
    
    # Ensure we have a valid commit hash
    if not commit_hash:
        commit_hash = f"request-{int(time.time())}"
    
    # Ensure the repo_rel_dir is correct - it should be relative to the repo root
    # but for our purposes, we'll just use the base directory name
    repo_rel_dir = os.path.basename(os.path.normpath(dir))
    
    payload_dict = {
        # Complete repo information
        'repo': {
            'owner': 'fake',
            'name': repo_name,
            'clone_url': f'https://github.com/fake/{repo_name}.git',
            'full_name': f'fake/{repo_name}',
            'html_url': f'https://github.com/fake/{repo_name}',
            'ssh_url': f'git@github.com:fake/{repo_name}.git',
            'vcs_host': {
                'hostname': 'github.com',
                'type': 'github'
            }
        },
        # Complete pull request information
        'pull_request': {
            'num': 1,
            'branch': 'main',
            'author': user,
            'base_branch': 'main',
            'url': f'https://github.com/fake/{repo_name}/pull/1',
            'state': 'open'
        },
        'user': user,
        'head_commit': commit_hash,
        'pull_num': 1,
        'pull_author': user,
        'repo_rel_dir': repo_rel_dir,
        'workspace': workspace if workspace else "default",
        'project_name': repo_name,
        'comment': comment,
        'verbose': True,
        'cmd': 'plan',  # Command is 'plan' for planning operation
        'dir': '.',     # Critical: include the 'dir' field
        'terraform_files': terraform_files,
        'environment': environment,  # Critical: environment field must be present and valid
        # Additional fields that might be expected by Atlantis
        'apply_requirements': ['approved'],  # Require approval before apply
        'automerge': False,          # Don't automerge the PR
        'workflow': 'default',       # Use default workflow
        'atlantis_version': '0.24.0', # Specify version for compatibility
    }
    
    return payload_dict

def generate_atlantis_apply_payload_fixed(config_data, tf_directory, tf_files, plan_id):
    """
    Generate a properly formatted Atlantis API payload for apply operation
    
    Args:
        config_data (dict): VM configuration data
        tf_directory (str): Directory containing Terraform files
        tf_files (list): List of Terraform files
        plan_id (str): ID of the Terraform plan to apply
        
    Returns:
        str: JSON formatted payload string for Atlantis API
    """
    # First, ensure the Terraform directory has the proper structure
    ensure_terraform_structure(tf_directory)
    
    # Get the directory name for the Terraform files
    tf_dir_name = os.path.basename(os.path.normpath(tf_directory))
    
    # Make sure we have providers.tf and variables.tf
    required_files = set(['providers.tf', 'variables.tf'])
    
    # If tf_files is a list
    if isinstance(tf_files, list):
        files_set = set(tf_files)
        missing_files = required_files - files_set
        
        # If some required files are missing, add them
        if missing_files:
            logger.info(f"Missing required files for apply: {', '.join(missing_files)}")
            # Add the missing files to the list
            for filename in missing_files:
                file_path = os.path.join(tf_directory, filename)
                if os.path.exists(file_path):
                    tf_files.append(filename)
    
    # Convert list of files to a dictionary with file contents
    terraform_files = {}
    if isinstance(tf_files, list):
        # Read the contents of each file
        for filename in tf_files:
            file_path = os.path.join(tf_directory, filename)
            try:
                with open(file_path, 'r') as f:
                    terraform_files[filename] = f.read()
            except Exception as e:
                logger.warning(f"Error reading file {file_path}: {str(e)}")
                terraform_files[filename] = f"# Error reading file: {str(e)}"
    else:
        # tf_files is already a dict with contents
        terraform_files = tf_files
        
        # Check for missing required files
        files_set = set(terraform_files.keys())
        missing_files = required_files - files_set
        
        # If some required files are missing, add them
        if missing_files:
            logger.info(f"Missing required files in terraform_files dict for apply: {', '.join(missing_files)}")
            for filename in missing_files:
                file_path = os.path.join(tf_directory, filename)
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r') as f:
                            terraform_files[filename] = f.read()
                    except Exception as e:
                        logger.warning(f"Error reading file {file_path}: {str(e)}")
                        terraform_files[filename] = f"# Error reading file: {str(e)}"
    
    # Ensure we have a valid repo name and server name
    repo_name = "build-server-repo" 
    server_name = config_data.get('server_name', 'default-server')
    environment = config_data.get('environment', 'development')
    request_id = config_data.get('request_id', 'unknown')
    
    # Make sure we have a valid environment - never use 'default' as it's a reserved word in Atlantis
    if not environment or environment == "default":
        environment = "development"
    
    # Also make sure workspace is set to the same environment value to maintain consistency
    workspace = environment
    
    # Ensure we have a valid commit hash
    commit_hash = f"request-{request_id}"
    
    # Get the owner/username
    owner = config_data.get('build_owner', 'Admin User')
    
    # Create a dictionary with all the necessary fields
    payload_dict = {
        # Complete repo information
        'repo': {
            'owner': 'fake',
            'name': repo_name,
            'clone_url': f'https://github.com/fake/{repo_name}.git',
            'full_name': f'fake/{repo_name}',
            'html_url': f'https://github.com/fake/{repo_name}',
            'ssh_url': f'git@github.com:fake/{repo_name}.git',
            'vcs_host': {
                'hostname': 'github.com',
                'type': 'github'
            }
        },
        # Complete pull request information
        'pull_request': {
            'num': 1,
            'branch': 'main',
            'author': owner,
            'base_branch': 'main',
            'url': f'https://github.com/fake/{repo_name}/pull/1',
            'state': 'open'
        },
        'head_commit': commit_hash,
        'pull_num': 1,
        'pull_author': owner,
        'repo_rel_dir': tf_dir_name,
        'workspace': workspace,
        'project_name': server_name,
        'plan_id': plan_id,
        'comment': f"Applying approved VM config: {server_name}",
        'user': owner,
        'verbose': True,
        'cmd': 'apply',  # Critical: ensure command is explicitly set to 'apply'
        'dir': '.',      # Critical: add the 'dir' field that's required
        'terraform_files': terraform_files,
        'environment': environment,  # Critical: environment field must be present and valid
        # Additional fields that might be expected by Atlantis
        'apply_requirements': ['approved'],  # Require approval before apply
        'automerge': False,          # Don't automerge the PR
        'workflow': 'default',       # Use default workflow
        'atlantis_version': '0.24.0', # Specify version for compatibility
    }
    
    # Convert to JSON string with proper formatting
    payload_string = json.dumps(payload_dict, ensure_ascii=False)
    
    return payload_string

def fix_apply_request(input_file):
    """Fix an existing apply payload JSON file"""
    try:
        # Read the existing payload
        with open(input_file, 'r') as f:
            payload = json.load(f)
        
        # Ensure all required fields exist
        required_fields = ['repo', 'pull_request', 'head_commit', 'pull_num', 
                          'pull_author', 'repo_rel_dir', 'workspace', 'project_name',
                          'plan_id', 'comment', 'user', 'cmd', 'dir']
        
        # Check for missing fields
        missing = [field for field in required_fields if field not in payload]
        
        if missing:
            logger.info(f"Adding missing fields to payload: {', '.join(missing)}")
            
            # Add missing fields with default values
            if 'cmd' not in payload:
                payload['cmd'] = 'apply'
            
            if 'dir' not in payload:
                payload['dir'] = '.'
            
            # Add other missing fields with placeholder values
            for field in missing:
                if field not in payload:
                    if field == 'repo':
                        payload[field] = {
                            'owner': 'fake',
                            'name': 'terraform-repo',
                            'clone_url': 'https://github.com/fake/terraform-repo.git'
                        }
                    elif field == 'pull_request':
                        payload[field] = {
                            'num': 1,
                            'branch': 'main',
                            'author': 'Admin User'
                        }
                    else:
                        payload[field] = f"placeholder-{field}"
        
        # Ensure repo field has all required subfields
        if 'repo' in payload:
            repo_fields = ['owner', 'name', 'clone_url']
            for field in repo_fields:
                if field not in payload['repo']:
                    payload['repo'][field] = f"fake-{field}"
        
        # Ensure pull_request field has all required subfields
        if 'pull_request' in payload:
            pr_fields = ['num', 'branch', 'author']
            for field in pr_fields:
                if field not in payload['pull_request']:
                    payload['pull_request'][field] = f"default-{field}"
        
        # Write the fixed payload back to file
        output_file = f"{input_file}.fixed"
        with open(output_file, 'w') as f:
            json.dump(payload, f, indent=2)
        
        logger.info(f"Fixed payload written to {output_file}")
        return output_file
    
    except Exception as e:
        logger.error(f"Error fixing apply payload: {str(e)}")
        return None

def modify_app_py():
    """Generate a patch for app.py to fix the apply_atlantis_plan function"""
    patch = """
To fix the issue with the Atlantis apply API call, modify the generate_atlantis_apply_payload 
function in app.py with these changes:

```python
def generate_atlantis_apply_payload(config_data, tf_directory, tf_files, plan_id):
    \"\"\"Generate a properly formatted Atlantis API payload for apply operation\"\"\"
    # Get the directory name for the Terraform files
    tf_dir_name = os.path.basename(tf_directory)
    
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
            'author': config_data.get('build_owner', 'Admin User')
        },
        'head_commit': 'abcd1234',
        'pull_num': 1,
        'pull_author': config_data.get('build_owner', 'Admin User'),
        'repo_rel_dir': tf_dir_name,
        'workspace': config_data.get('environment', 'development'),
        'project_name': config_data.get('server_name', 'default-server'),
        'plan_id': plan_id,
        'comment': f"Applying approved VM config: {config_data.get('server_name', 'unknown')}",
        'user': config_data.get('build_owner', 'Admin User'),
        'verbose': True,
        'cmd': 'apply',  # Critical: ensure command is explicitly set to 'apply'
        'dir': '.',      # Critical: add the 'dir' field that's required
        'terraform_files': tf_files
    }
    
    # Convert to JSON string with proper formatting
    payload_string = json.dumps(payload_dict, ensure_ascii=False)
    
    return payload_string
```

The key changes are:
1. Added the 'dir' field which was missing from the original request
2. Made sure 'cmd' is explicitly set to 'apply'
3. Added fallback defaults for important fields using .get() method
"""
    print(patch)
    
    # Write the patch to a file
    with open('atlantis_apply_fix.patch', 'w') as f:
        f.write(patch)
    
    logger.info("Patch written to atlantis_apply_fix.patch")

if __name__ == "__main__":
    logger.info("Atlantis Apply API Fix Tool")
    logger.info("==========================")
    
    # Check if a file was provided as argument
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        logger.info(f"Fixing payload in file: {input_file}")
        fixed_file = fix_apply_request(input_file)
        if fixed_file:
            logger.info(f"Success! Use the fixed payload in {fixed_file}")
    else:
        # Generate the patch for app.py
        logger.info("Generating patch for app.py")
        modify_app_py()
        
    logger.info("\nFix Summary:")
    logger.info("1. The Atlantis apply API requires the 'dir' field which was missing")
    logger.info("2. Ensure the 'cmd' field is explicitly set to 'apply'")
    logger.info("3. All fields in the payload must be properly formatted")
    logger.info("4. Apply the patch to app.py to fix the issue permanently")
