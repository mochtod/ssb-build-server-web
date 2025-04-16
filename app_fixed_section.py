# This is a fixed version of the exception handling block for app.py
# Use this to replace the problematic section in your app.py file

# Import necessary libraries
import requests
import logging

# Setup logger
logger = logging.getLogger(__name__)

# This is a demonstration function containing the fixed code block
def run_atlantis_plan_example(ATLANTIS_URL, payload_string, headers):
    """Example function showing the correct structure of the Atlantis API call with proper error handling"""
    try:
        response = requests.post(
            f"{ATLANTIS_URL}/api/plan", 
            data=payload_string, 
            headers=headers,
            timeout=30  # Add timeout to prevent hanging indefinitely
        )
    except requests.exceptions.Timeout:
        logger.error(f"Timeout while connecting to Atlantis API at {ATLANTIS_URL}")
        return {
            'status': 'error',
            'message': f"Timeout connecting to Atlantis API. Please check if the server is responding."
        }
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"Connection error while connecting to Atlantis API: {conn_err}", exc_info=True)
        return {
            'status': 'error',
            'message': f"Unable to connect to Atlantis API. Please check the server URL and network connection."
        }
    except Exception as req_err:
        logger.error(f"Error during Atlantis API request: {req_err}", exc_info=True)
        return {
            'status': 'error',
            'message': f"Error sending request to Atlantis: {str(req_err)}"
        }
    
    if response.status_code != 200:
        # If API call fails, log the error and return with proper error info
        error_message = f"Failed to trigger Atlantis plan: HTTP {response.status_code}"
        try:
            error_detail = response.json()
            logger.error(f"{error_message} - Details: {error_detail}")
        except Exception:
            # If response isn't valid JSON, log the raw text
            logger.error(f"{error_message} - Response: {response.text}")
        
        return {
            'status': 'error',
            'message': f"{error_message}. Check server logs for details."
        }
    
    # If everything went well, return the response
    return {
        'status': 'success',
        'response': response
    }

# Note: To use this in app.py, you should copy the code inside the function
# into your existing run_atlantis_plan function, ensuring proper indentation
