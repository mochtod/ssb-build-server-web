import requests
import json
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Atlantis API configuration
ATLANTIS_URL = "http://localhost:4141"
ATLANTIS_TOKEN = os.environ.get("ATLANTIS_TOKEN", "lkajsdf;lkasd;kljasdf")

def test_atlantis_plan():
    """Test the Atlantis API with a literal payload to ensure correct formatting"""
    
    # Load test content directly
    with open('test-payload-fixed.json', 'r') as f:
        # Read the raw content
        raw_content = f.read()
        
    # Modify only the repo_rel_dir attribute to use test_fix instead of test-tf
    modified_content = raw_content.replace('"repo_rel_dir": "test-tf"', '"repo_rel_dir": "test_fix"')
    
    # Print some debug information
    logger.info("Using raw JSON payload with minimal modifications")
    logger.info(f"Payload first 100 chars: {modified_content[:100]}")
    
    # Call Atlantis API
    headers = {
        'Content-Type': 'application/json',
        'X-Atlantis-Token': ATLANTIS_TOKEN
    }
    
    logger.info(f"Sending plan request to Atlantis for test_fix")
    try:
        response = requests.post(
            f"{ATLANTIS_URL}/api/plan", 
            data=modified_content,  # Use the raw modified content 
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
