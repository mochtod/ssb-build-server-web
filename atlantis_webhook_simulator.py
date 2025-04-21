#!/usr/bin/env python3
"""
Atlantis Webhook Simulator

This script continuously simulates GitHub webhook events by sending
pre-configured webhook payloads to the Atlantis server.
It's designed to run indefinitely and automatically restart with the VM.
"""

import json
import time
import random
import logging
import requests
import os
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('atlantis_webhook_simulator.log')
    ]
)

logger = logging.getLogger("atlantis-webhook-simulator")

# Configuration
ATLANTIS_WEBHOOK_URL = "http://localhost:4141/events"  # Local webhook URL
ATLANTIS_API_SECRET = os.environ.get('ATLANTIS_TOKEN', 'your-atlantis-api-secret')
GITHUB_WEBHOOK_SECRET = os.environ.get('GH_WEBHOOK_SECRET', 'your-webhook-secret')
PAYLOAD_FILES = [
    "test-payload.json",
    "test-payload-updated.json"
]
MIN_INTERVAL = 60  # Minimum seconds between webhook events
MAX_INTERVAL = 180  # Maximum seconds between webhook events
MAX_RETRIES = 5     # Maximum number of retries when connection fails
RETRY_DELAY = 10    # Seconds to wait between retries

def load_payload(filename):
    """Load a webhook payload from a JSON file."""
    try:
        with open(filename, 'r') as f:
            payload = json.load(f)
            # Update timestamp and random commit hash to make each payload unique
            payload['timestamp'] = datetime.now().isoformat()
            payload['head_commit'] = f"{random.getrandbits(32):08x}"
            return payload
    except Exception as e:
        logger.error(f"Failed to load payload from {filename}: {e}")
        return None

def send_webhook(payload):
    """Send a webhook payload to the Atlantis server."""
    headers = {
        'Content-Type': 'application/json',
        'X-GitHub-Event': 'pull_request',
        'X-GitHub-Delivery': f"{random.getrandbits(64):016x}",
        'X-Hub-Signature': 'sha1=fake',  # Signature validation is bypassed in our setup
        'X-Atlantis-Token': ATLANTIS_API_SECRET
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                ATLANTIS_WEBHOOK_URL,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Webhook delivered successfully: HTTP {response.status_code}")
                return True
            else:
                logger.warning(f"Webhook failed: HTTP {response.status_code}, Response: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed (attempt {attempt+1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error("Max retries exceeded. Moving on.")
                return False

def main():
    """Main function to continuously send webhook events."""
    logger.info("Atlantis webhook simulator started")
    
    try:
        while True:
            # Select a random payload file
            payload_file = random.choice(PAYLOAD_FILES)
            logger.info(f"Selected payload file: {payload_file}")
            
            # Load the payload
            payload = load_payload(payload_file)
            if payload:
                # Update the project name with a timestamp to make it unique
                timestamp = int(time.time())
                payload['project_name'] = f"test-vm-{timestamp}"
                
                # Send the webhook
                send_webhook(payload)
            
            # Sleep for a random interval before sending the next webhook
            sleep_time = random.randint(MIN_INTERVAL, MAX_INTERVAL)
            logger.info(f"Sleeping for {sleep_time} seconds before next webhook")
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        logger.info("Webhook simulator stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise

if __name__ == "__main__":
    main()