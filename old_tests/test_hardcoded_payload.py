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
ATLANTIS_TOKEN = os.environ.get("ATLANTIS_TOKEN", "lkajsdflkasdkljasdf")  # The token from .env

def test_hardcoded_payload():
    """Test the Atlantis API with a hardcoded JSON payload with placeholders"""
    
    # Read the test Terraform file
    tf_directory = "terraform/test_fix"
    
    if not os.path.exists(tf_directory):
        logger.error(f"Test directory {tf_directory} does not exist.")
        return {"status": "error", "message": f"Test directory {tf_directory} not found"}
    
    # Read the main.tf file
    tf_file_path = os.path.join(tf_directory, "main.tf")
    
    try:
        with open(tf_file_path, 'r') as f:
            tf_content = f.read()
            # Escape any double quotes and backslashes for JSON
            tf_content = tf_content.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    except Exception as e:
        logger.error(f"Error reading test Terraform file: {str(e)}")
        return {"status": "error", "message": f"Error reading test file: {str(e)}"}
    
    # Create a hardcoded JSON with placeholders
    payload = f'''{{
  "repo": {{
    "owner": "fake",
    "name": "terraform-repo",
    "clone_url": "https://github.com/fake/terraform-repo.git"
  }},
  "pull_request": {{
    "num": 1,
    "branch": "main",
    "author": "Test User"
  }},
  "head_commit": "abcd1234",
  "pull_num": 1,
  "pull_author": "Test User",
  "repo_rel_dir": "test_fix",
  "workspace": "development",
  "project_name": "hardcoded-test",
  "plan_only": true,
  "comment": "Testing Hardcoded Payload",
  "user": "Test User",
  "verbose": true,
  "cmd": "plan",
  "terraform_files": {{
    "main.tf": "{tf_content}"
  }}
}}'''
    
    # Log the first part of the payload for debugging
    logger.info(f"Hardcoded payload first 100 chars: {payload[:100]}...")
    
    # Call Atlantis API
    headers = {
        'Content-Type': 'application/json',
        'X-Atlantis-Token': ATLANTIS_TOKEN
    }
    
    logger.info(f"Sending plan request to Atlantis with hardcoded payload")
    try:
        response = requests.post(
            f"{ATLANTIS_URL}/api/plan", 
            data=payload, 
            headers=headers
        )
        
        logger.info(f"Response status code: {response.status_code}")
        
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
    print("Testing Atlantis API with hardcoded payload")
    result = test_hardcoded_payload()
    print(f"Test result: {json.dumps(result, indent=2)}")
    
    if result.get('status') == 'success':
        print("\nSUCCESS: The hardcoded payload approach works!")
        sys.exit(0)
    else:
        print("\nFAILURE: The hardcoded payload approach failed.")
        sys.exit(1)
