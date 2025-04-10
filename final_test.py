import requests
import json
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Atlantis API configuration
ATLANTIS_URL = "http://localhost:4141"
ATLANTIS_TOKEN = os.environ.get("ATLANTIS_TOKEN", "lkajsdflkasdkljasdf")  # Updated to match .env file

def test_atlantis_plan():
    """Test the Atlantis API with a completely manually formatted payload"""
    
    # Include the cmd field as it might be required by Atlantis
    payload = """{
  "repo": {
    "owner": "fake",
    "name": "terraform-repo",
    "clone_url": "https://github.com/fake/terraform-repo.git"
  },
  "pull_request": {
    "num": 1,
    "branch": "main",
    "author": "Admin User"
  },
  "head_commit": "abcd1234",
  "pull_num": 1,
  "pull_author": "Admin User",
  "repo_rel_dir": "test_fix",
  "workspace": "development",
  "project_name": "test-vm",
  "comment": "API Test Plan",
  "user": "Admin User",
  "verbose": true,
  "plan_only": true,
  "cmd": "plan",
  "terraform_files": {
    "main.tf": "# Simple test configuration for Atlantis\\nterraform {\\n  required_version = \\\">= 0.14.0\\\"\\n}\\n\\nvariable \\\"test_string\\\" {\\n  description = \\\"A test string variable\\\"\\n  type        = string\\n  default     = \\\"Hello Atlantis\\\"\\n}\\n\\nresource \\\"null_resource\\\" \\\"test\\\" {\\n  triggers = {\\n    test_string = var.test_string\\n  }\\n\\n  provisioner \\\"local-exec\\\" {\\n    command = \\\"echo ${var.test_string}\\\"\\n  }\\n}\\n\\noutput \\\"test_output\\\" {\\n  value = var.test_string\\n}\\n"
  }
}"""
    
    # Print some debug information
    logger.info("Using manually created valid JSON payload with explicit commas")
    logger.info(f"Payload first 100 chars: {payload[:100]}")
    
    # Call Atlantis API
    headers = {
        'Content-Type': 'application/json',
        'X-Atlantis-Token': ATLANTIS_TOKEN
    }
    
    logger.info(f"Sending plan request to Atlantis for test_fix")
    try:
        response = requests.post(
            f"{ATLANTIS_URL}/api/plan", 
            data=payload,  # Use the raw string payload
            headers=headers
        )
        
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response headers: {response.headers}")
        
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
