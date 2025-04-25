#!/usr/bin/env python
"""
Log monitor script for Flask/Redis/vSphere containers
Checks container logs for errors and warnings to facilitate UI testing
"""
import os
import subprocess
import time
import re
import sys

# ANSI color codes for better readability
RED = '\033[91m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

# Error and warning patterns to look for
ERROR_PATTERNS = [
    r'Error',
    r'ERROR',
    r'Exception',
    r'EXCEPTION',
    r'Failed',
    r'FAILED',
    r'ConnectionRefusedError',
    r'ConnectionError',
    r'Redis connection error',
    r'[Ee]rror connecting to vsphere',
    r'Template.*not found',
    r'templates.*missing'
]

WARNING_PATTERNS = [
    r'Warning',
    r'WARNING', 
    r'templates.*missing datacenter',
    r'datacenter_id.*missing',
    r'fallback.*template',
    r'WARN',
    r'DEPRECATED'
]

INFO_PATTERNS = [
    r'Redis connection',
    r'VSphere connection',
    r'template',
    r'datacenter',
    r'cluster',
    r'Successfully connected'
]

def run_docker_command(command):
    """Run a docker command and return the output"""
    try:
        result = subprocess.run(
            command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            shell=True,
            text=True
        )
        return result.stdout
    except Exception as e:
        print(f"{RED}Error running command: {command}{RESET}")
        print(f"{RED}{str(e)}{RESET}")
        return ""

def check_container_logs(container_name, lines=50):
    """Get logs from a specific container"""
    logs = run_docker_command(f"docker logs --tail={lines} {container_name} 2>&1")
    return logs

def check_all_containers():
    """Check logs from all relevant containers"""
    # Get list of running containers
    containers_output = run_docker_command("docker ps --format '{{.Names}}'")
    containers = containers_output.strip().split('\n')
    
    relevant_containers = [c for c in containers if any(name in c.lower() for name in 
                          ['web', 'redis', 'vsphere', 'atlantis'])]
    
    if not relevant_containers:
        print(f"{YELLOW}No relevant containers found running. Are your containers started?{RESET}")
        return
    
    print(f"{BLUE}{BOLD}Checking logs from {len(relevant_containers)} containers...{RESET}")
    
    for container in relevant_containers:
        container = container.strip()
        if not container:
            continue
            
        print(f"\n{BLUE}{BOLD}=== Logs from {container} ==={RESET}")
        logs = check_container_logs(container)
        
        if not logs:
            print(f"{YELLOW}No logs found for {container}{RESET}")
            continue
        
        # Split logs into lines for processing
        log_lines = logs.split('\n')
        
        # Process each line for errors and warnings
        error_found = False
        warning_found = False
        info_found = False
        
        for line in log_lines:
            # Check for errors
            if any(re.search(pattern, line) for pattern in ERROR_PATTERNS):
                print(f"{RED}{line}{RESET}")
                error_found = True
                continue
            
            # Check for warnings
            if any(re.search(pattern, line) for pattern in WARNING_PATTERNS):
                print(f"{YELLOW}{line}{RESET}")
                warning_found = True
                continue
                
            # Check for important info
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in INFO_PATTERNS):
                print(f"{GREEN}{line}{RESET}")
                info_found = True
        
        if not (error_found or warning_found or info_found):
            print(f"{GREEN}No errors or warnings found in logs{RESET}")

def monitor_logs_continuously():
    """Monitor logs continuously with updates every few seconds"""
    print(f"{BLUE}{BOLD}Starting continuous log monitoring. Press Ctrl+C to stop.{RESET}")
    try:
        while True:
            check_all_containers()
            print(f"\n{BLUE}{BOLD}=== Waiting 5 seconds before next check... ==={RESET}")
            time.sleep(5)
    except KeyboardInterrupt:
        print(f"\n{GREEN}Log monitoring stopped{RESET}")

def main():
    """Main function"""
    print(f"{BLUE}{BOLD}Container Log Monitor for UI Testing{RESET}")
    print(f"{BLUE}Looking for errors and warnings in container logs...{RESET}")
    
    if len(sys.argv) > 1 and sys.argv[1] == "--monitor":
        monitor_logs_continuously()
    else:
        check_all_containers()
        print(f"\n{BLUE}Run with --monitor flag to continuously monitor logs{RESET}")

if __name__ == "__main__":
    main()