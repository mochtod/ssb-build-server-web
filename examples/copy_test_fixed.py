import requests
import json
import os
import logging
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a copy of the fixed test payload
def copy_and_modify_payload():
    """Create a copy of the test-payload-fixed.json and change only the repo_rel_dir"""
    
    # Copy test-payload-fixed.json to test-payload-test-fix.json
    shutil.copy("test-payload-fixed.json", "test-payload-test-fix.json")
    
    # Read the contents of the test-payload-test-fix.json
    with open("test-payload-test-fix.json", "r") as f:
        data = f.read()
    
    # Replace 'test-tf' with 'test_fix'
    data = data.replace('"repo_rel_dir": "test-tf"', '"repo_rel_dir": "test_fix"')
    
    # Write the modified contents back to the file
    with open("test-payload-test-fix.json", "w") as f:
        f.write(data)
    
    logger.info("Created modified payload file test-payload-test-fix.json")
    return "test-payload-test-fix.json"

def test_with_file():
    """Test the Atlantis API using the copied payload file"""
    
    try:
        # Create the modified payload file
        payload_file = copy_and_modify_payload()
        
        # Read the contents of the payload file
        with open(payload_file, "r") as f:
            payload = f.read()
        
        # Call Atlantis API
        headers = {
            'Content-Type': 'application/json',
            'X-Atlantis-Token': os.environ.get("ATLANTIS_TOKEN", "lkajsdf;lkasd;kljasdf")
        }
        
        logger.info(f"Sending direct API request to Atlantis using file {payload_file}")
        response = requests.post(
            "http://localhost:4141/api/plan",
            data=payload,
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
        logger.exception(f"Error in test_with_file: {str(e)}")
        return {
            'status': 'error',
            'message': f"Error in test_with_file: {str(e)}"
        }

if __name__ == "__main__":
    result = test_with_file()
    print(f"Test result: {json.dumps(result, indent=2)}")
