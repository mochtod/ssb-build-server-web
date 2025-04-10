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

def test_template_payload():
    """Test the Atlantis API with a template-based payload"""
    
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
    except Exception as e:
        logger.error(f"Error reading test Terraform file: {str(e)}")
        return {"status": "error", "message": f"Error reading test file: {str(e)}"}
    
    # Create a template-based payload using string formatting
    # This ensures we have full control over the JSON structure
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
  "project_name": "template-test",
  "plan_only": true,
  "comment": "Testing Template-Based Payload",
  "user": "Test User",
  "verbose": true,
  "cmd": "plan",
  "terraform_files": {{
    "main.tf": "{tf_content.replace('"', '\\"').replace('\n', '\\n')}"
  }}
}}'''
    
    # Log the first part of the payload for debugging
    logger.info(f"Template payload first 200 chars: {payload[:200]}...")
    
    # Call Atlantis API
    headers = {
        'Content-Type': 'application/json',
        'X-Atlantis-Token': ATLANTIS_TOKEN
    }
    
    logger.info(f"Sending plan request to Atlantis with template payload")
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
    print("Testing Atlantis API with template-based payload")
    result = test_template_payload()
    print(f"Test result: {json.dumps(result, indent=2)}")
    
    if result.get('status') == 'success':
        print("\nSUCCESS: The template-based payload approach works!")
        sys.exit(0)
    else:
        print("\nFAILURE: The template-based payload approach failed.")
        sys.exit(1)
