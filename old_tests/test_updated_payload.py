import requests
import json
import os
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Atlantis API configuration
ATLANTIS_URL = "http://localhost:4141"
ATLANTIS_TOKEN = os.environ.get("ATLANTIS_TOKEN", "lkajsdflkasdkljasdf")  # Updated to match .env file

def test_atlantis_plan_with_fixes():
    """Test the Atlantis API plan endpoint with our fixes"""
    
    # Read the Terraform files from a test directory
    tf_files = {}
    tf_directory = "terraform/test_fix"
    
    if not os.path.exists(tf_directory):
        logger.error(f"Test directory {tf_directory} does not exist. Please create it first.")
        return {"status": "error", "message": f"Test directory {tf_directory} not found"}
    
    for filename in os.listdir(tf_directory):
        if filename.endswith('.tf') or filename.endswith('.tfvars'):
            file_path = os.path.join(tf_directory, filename)
            with open(file_path, 'r') as f:
                tf_files[filename] = f.read()
    
    if not tf_files:
        logger.error(f"No Terraform files found in {tf_directory}")
        return {"status": "error", "message": f"No Terraform files found in {tf_directory}"}
    
    # Load the reference payload
    try:
        with open('test-payload-fixed.json', 'r') as f:
            reference_payload = json.load(f)
            logger.info("Loaded reference payload template")
    except Exception as e:
        logger.error(f"Error loading reference payload: {str(e)}")
        return {"status": "error", "message": f"Error loading reference payload: {str(e)}"}
    
    # Create payload with our updated structure
    atlantis_payload = {
        'repo': {
            'owner': 'fake',
            'name': 'terraform-repo',
            'clone_url': 'https://github.com/fake/terraform-repo.git'
        },
        'pull_request': {
            'num': 1,
            'branch': 'main',
            'author': 'Test User'
        },
        'head_commit': 'abcd1234',
        'pull_num': 1,
        'pull_author': 'Test User',
        'repo_rel_dir': 'test_fix',
        'workspace': 'development',
        'project_name': 'test-vm-fixed',
        'terraform_files': tf_files,
        'plan_only': True,
        'comment': "Testing Updated Payload Structure",
        'user': 'Test User',
        'verbose': True,
        'cmd': 'plan'  # Added the cmd field
    }
    
    # Ensure all required fields from reference payload are included
    for key in reference_payload.keys():
        if key not in atlantis_payload and key != 'terraform_files':
            logger.info(f"Adding missing field from reference: {key}")
            atlantis_payload[key] = reference_payload[key]
    
    # Log the final payload keys
    logger.info(f"Final payload keys: {sorted(atlantis_payload.keys())}")
    
    # Call Atlantis API
    headers = {
        'Content-Type': 'application/json',
        'X-Atlantis-Token': ATLANTIS_TOKEN
    }
    
    logger.info(f"Sending plan request to Atlantis with updated payload structure")
    
    # Use a more robust method for JSON serialization
    try:
        # Convert the terraform_files content to a separate JSON
        terraform_files_json = json.dumps(atlantis_payload['terraform_files'])
        
        # Remove the terraform_files temporarily
        temp_payload = atlantis_payload.copy()
        del temp_payload['terraform_files']
        
        # Create a properly formatted JSON string for the main payload
        payload_string = json.dumps(temp_payload, ensure_ascii=False, indent=2)
        
        # Insert the terraform_files back in
        # Find the closing brace position
        closing_brace_pos = payload_string.rstrip().rfind('}')
        
        # Insert terraform_files before the closing brace
        payload_string = payload_string[:closing_brace_pos] + ',\n  "terraform_files": ' + terraform_files_json + payload_string[closing_brace_pos:]
        
        # Display part of the payload for debugging
        logger.info(f"First 100 chars of payload: {payload_string[:100]}...")
    except Exception as e:
        logger.error(f"Error creating JSON payload: {e}")
        return {
            'status': 'error',
            'message': f"Error creating JSON payload: {e}"
        }
    
    # Make the API request
    try:
        response = requests.post(
            f"{ATLANTIS_URL}/api/plan", 
            data=payload_string, 
            headers=headers
        )
        
        if response.status_code != 200:
            error_message = f"Failed to trigger Atlantis plan: {response.text}"
            logger.error(error_message)
            return {
                'status': 'error',
                'message': error_message
            }
        
        plan_response = response.json()
        logger.info(f"Plan response: {json.dumps(plan_response, indent=2)}")
        return {
            'status': 'success',
            'response': plan_response
        }
    except Exception as e:
        logger.exception(f"Error calling Atlantis API: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error calling Atlantis API: {str(e)}"
        }

if __name__ == "__main__":
    print("Testing updated Atlantis API payload structure")
    result = test_atlantis_plan_with_fixes()
    print(f"Test result: {json.dumps(result, indent=2)}")
    
    if result.get('status') == 'success':
        print("\nSUCCESS: The updated payload structure worked correctly!")
        sys.exit(0)
    else:
        print("\nFAILURE: The updated payload structure did not work.")
        sys.exit(1)
