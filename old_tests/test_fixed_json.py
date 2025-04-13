import requests
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Atlantis API configuration
ATLANTIS_URL = "http://localhost:4141"
ATLANTIS_TOKEN = "lkajsdflkasdkljasdf"  # Token from .env file

def test_with_fixed_json():
    """Test Atlantis API with manually formatted JSON"""
    try:
        # Create a simplified payload with proper formatting
        payload = {
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
            "terraform_files": {
                "main.tf": """# Simple test configuration for Atlantis
terraform {
  required_version = ">= 0.14.0"
}

variable "test_string" {
  description = "A test string variable"
  type        = string
  default     = "Hello Atlantis"
}

resource "null_resource" "test" {
  triggers = {
    test_string = var.test_string
  }

  provisioner "local-exec" {
    command = "echo ${var.test_string}"
  }
}

output "test_output" {
  value = var.test_string
}
"""
            },
            "comment": "API Test Plan",
            "user": "Admin User",
            "verbose": True,
            "plan_only": True
        }
        
        # Display key information
        logger.info(f"Using manually constructed payload with keys: {', '.join(payload.keys())}")
        
        # Serialize the payload - ensure_ascii=False to preserve Unicode characters
        # indent=None to avoid adding newlines and spaces that might cause issues
        # sort_keys=False to maintain the order of keys
        json_str = json.dumps(payload, ensure_ascii=False, indent=None, sort_keys=False)
        logger.info(f"First 100 chars of payload: {json_str[:100]}")
        
        # Call Atlantis API
        headers = {
            'Content-Type': 'application/json',
            'X-Atlantis-Token': ATLANTIS_TOKEN
        }
        
        logger.info(f"Sending request to Atlantis with fixed JSON payload")
        response = requests.post(
            f"{ATLANTIS_URL}/api/plan", 
            data=json_str,
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
        logger.exception(f"Error in test_with_fixed_json: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error in test_with_fixed_json: {str(e)}"
        }

if __name__ == "__main__":
    result = test_with_fixed_json()
    print(f"Test result: {json.dumps(result, indent=2)}")
