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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_atlantis_apply_payload_fixed(config_data, tf_directory, tf_files, plan_id):
    """Generate a properly formatted Atlantis API payload for apply operation"""
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
