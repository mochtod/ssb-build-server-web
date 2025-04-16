# This is the corrected snippet from app.py
# Replace the exception handling section in run_atlantis_plan function

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
