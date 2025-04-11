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

def direct_test():
    """Test the Atlantis API using an exact copy of the working payload structure"""
    
    try:
        # Load the test-payload-fixed.json
        with open('test-payload-fixed.json', 'r') as f:
            payload = json.load(f)
        
        # Only change the repo_rel_dir to our test_fix directory
        payload['repo_rel_dir'] = 'test_fix'
        
        # Update terraform_files to point to our test file
        with open('terraform/test_fix/main.tf', 'r') as f:
            terraform_content = f.read()
            
        payload['terraform_files'] = {
            'main.tf': terraform_content
        }
        
        # Print the payload structure
        logger.info(f"Payload keys: {', '.join(payload.keys())}")
        
        # Force the order of keys to match exactly the test-payload-fixed.json
        # Create a new ordered payload
        ordered_keys = list(payload.keys())
        logger.info(f"Keys in order: {ordered_keys}")
        
        # Create a properly formatted JSON string with commas
        # The issue appears to be that json.dumps is not adding commas between fields correctly
        
        # Manual JSON formatting to ensure commas are included
        repo_part = json.dumps(payload['repo']).replace('" "', '", "')
        pull_request_part = json.dumps(payload['pull_request']).replace('" "', '", "')
        terraform_files_part = json.dumps(payload['terraform_files'])
        
        payload_str = f"""{{
  "repo": {repo_part},
  "pull_request": {pull_request_part},
  "head_commit": "{payload['head_commit']}",
  "pull_num": {payload['pull_num']},
  "pull_author": "{payload['pull_author']}",
  "repo_rel_dir": "{payload['repo_rel_dir']}",
  "workspace": "{payload['workspace']}",
  "project_name": "{payload['project_name']}",
  "comment": "{payload['comment']}",
  "user": "{payload['user']}",
  "verbose": {str(payload['verbose']).lower()},
  "plan_only": {str(payload['plan_only']).lower()},
  "terraform_files": {terraform_files_part}
}}"""
        logger.info(f"Manually formatted payload (first 100 chars): {payload_str[:100]}...")
        
        # Call Atlantis API
        headers = {
            'Content-Type': 'application/json',
            'X-Atlantis-Token': ATLANTIS_TOKEN
        }
        
        logger.info(f"Sending direct API request to Atlantis")
        response = requests.post(f"{ATLANTIS_URL}/api/plan", 
                               data=payload_str,  # Use the raw string
                               headers=headers)
        
        if response.status_code != 200:
            error_message = f"Failed to trigger Atlantis plan: {response.text}"
            logger.error(error_message)
            return {
                'status': 'error',
                'message': error_message,
                'payload_used': payload_str
            }
        
        plan_response = response.json()
        logger.info(f"Plan response: {json.dumps(plan_response, indent=2)}")
        return {
            'status': 'success',
            'response': plan_response
        }
    except Exception as e:
        logger.exception(f"Error in direct test: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error in direct test: {str(e)}"
        }

if __name__ == "__main__":
    result = direct_test()
    print(f"Direct test result: {json.dumps(result, indent=2)}")
