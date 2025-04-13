import requests
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Atlantis API configuration
ATLANTIS_URL = "http://localhost:4141"
ATLANTIS_TOKEN = "lkajsdflkasdkljasdf"  # Token from .env file

def test_with_minimal_payload():
    """Test Atlantis API with the minimal payload"""
    try:
        # Load the test-payload-minimal.json
        with open('test-payload-minimal.json', 'r') as f:
            payload = json.load(f)
            
        # Properly serialize the JSON with commas between fields
        payload_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        
        # Display key information
        logger.info(f"Using payload with keys: {', '.join(payload.keys())}")
            
        # Call Atlantis API
        headers = {
            'Content-Type': 'application/json',
            'X-Atlantis-Token': ATLANTIS_TOKEN
        }
        
        logger.info(f"Sending request to Atlantis with minimal payload")
        response = requests.post(
            f"{ATLANTIS_URL}/api/plan", 
            data=payload_str,
            headers=headers
        )
        
        logger.info(f"Response status code: {response.status_code}")
        
        if response.status_code != 200:
            error_message = f"Failed to trigger Atlantis plan: {response.text}"
            logger.error(error_message)
            return {
                'status': 'error',
                'message': error_message,
                'payload_used': payload
            }
        
        plan_response = response.json()
        logger.info(f"Plan response: {json.dumps(plan_response, indent=2)}")
        return {
            'status': 'success',
            'response': plan_response
        }
    except Exception as e:
        logger.exception(f"Error in test_with_minimal_payload: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error in test_with_minimal_payload: {str(e)}"
        }

if __name__ == "__main__":
    result = test_with_minimal_payload()
    print(f"Test result: {json.dumps(result, indent=2)}")
