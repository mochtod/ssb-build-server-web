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

def test_final_payload():
    """Test using the exact structure from test-payload-fixed.json with cmd field added"""
    
    # Load the known working payload
    try:
        with open('test-payload-fixed.json', 'r') as f:
            payload_dict = json.load(f)
            logger.info("Loaded test-payload-fixed.json as base template")
    except Exception as e:
        logger.error(f"Error loading test-payload-fixed.json: {str(e)}")
        return {"status": "error", "message": f"Error loading test-payload-fixed.json: {str(e)}"}
    
    # Update the repo_rel_dir to match our test directory
    payload_dict["repo_rel_dir"] = "test_fix"
    
    # Add the cmd field which appears to be missing
    payload_dict["cmd"] = "plan"
    
    # Convert to a JSON string - this is important
    payload_string = json.dumps(payload_dict)
    
    # Log the keys in the payload for debugging
    logger.info(f"Final payload keys: {sorted(payload_dict.keys())}")
    logger.info(f"First 100 chars of payload string: {payload_string[:100]}...")
    
    # Call Atlantis API
    headers = {
        'Content-Type': 'application/json',
        'X-Atlantis-Token': ATLANTIS_TOKEN
    }
    
    logger.info(f"Sending plan request to Atlantis with fixed payload")
    try:
        response = requests.post(
            f"{ATLANTIS_URL}/api/plan", 
            data=payload_string, 
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
    print("Testing Atlantis API with final fix payload")
    result = test_final_payload()
    print(f"Test result: {json.dumps(result, indent=2)}")
    
    if result.get('status') == 'success':
        print("\nSUCCESS: The final fix payload works!")
        sys.exit(0)
    else:
        print("\nFAILURE: The final fix payload failed.")
        sys.exit(1)
