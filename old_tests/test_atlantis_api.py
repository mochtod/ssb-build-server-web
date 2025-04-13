import requests
import json
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Atlantis API configuration
ATLANTIS_URL = "http://localhost:4141"
ATLANTIS_TOKEN = os.environ.get("ATLANTIS_TOKEN", "lkajsdflkasdkljasdf")

def test_atlantis_plan():
    """Test the Atlantis API plan endpoint with our fixes"""
    
    # Read the Terraform files from test_fix directory
    tf_files = {}
    tf_directory = "terraform/test_fix"
    
    for filename in os.listdir(tf_directory):
        if filename.endswith('.tf') or filename.endswith('.tfvars'):
            file_path = os.path.join(tf_directory, filename)
            with open(file_path, 'r') as f:
                tf_files[filename] = f.read()
    
    # Prepare the Atlantis payload with proper structure
    try:
        # Load the test-payload-fixed.json as a reference
        with open('test-payload-fixed.json', 'r') as f:
            reference_payload = json.load(f)
            
        # Create payload based on the reference structure
        atlantis_payload = {
            # Copy required structure from reference
            'repo': reference_payload['repo'],
            'pull_request': reference_payload['pull_request'],
            'head_commit': reference_payload['head_commit'],
            'pull_num': reference_payload['pull_num'],
            'pull_author': reference_payload['pull_author'],
            
            # Update with our test-specific values
            'repo_rel_dir': 'test_fix',
            'workspace': 'development',
            'project_name': 'test-fix',
            'terraform_files': tf_files,
            'plan_only': True,
            'comment': "API Test Plan",
            'user': 'Test User',
            'verbose': True
        }
        
        # Print the keys in the payload for debugging
        logger.info(f"Prepared Atlantis payload with keys: {', '.join(atlantis_payload.keys())}")
    except Exception as e:
        logger.error(f"Error preparing Atlantis payload: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error preparing Atlantis payload: {str(e)}"
        }
    
    # Call Atlantis API
    headers = {
        'Content-Type': 'application/json',
        'X-Atlantis-Token': ATLANTIS_TOKEN
    }
    
    logger.info(f"Sending plan request to Atlantis for test_fix")
    try:
        # Properly serialize the JSON with correct commas
        payload_string = json.dumps(atlantis_payload, ensure_ascii=False, separators=(',', ':'))
        logger.info(f"First 100 chars of payload: {payload_string[:100]}")
        
        response = requests.post(f"{ATLANTIS_URL}/api/plan", 
                               data=payload_string, 
                               headers=headers)
        
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
    result = test_atlantis_plan()
    print(f"Test result: {json.dumps(result, indent=2)}")
