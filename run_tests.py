#!/usr/bin/env python3
"""
Test Runner Script

This script runs all the tests for the SSB Build Server Web application
and generates a report of the results.
"""
import os
import sys
import time
import unittest
import logging
import argparse
import json
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_unit_tests():
    """
    Run all unit tests in the project.
    """
    logger.info("Running unit tests...")
    
    # Discover and run unit tests
    test_suite = unittest.defaultTestLoader.discover('.', pattern='test_*.py')
    test_runner = unittest.TextTestRunner(verbosity=2)
    result = test_runner.run(test_suite)
    
    return {
        'total': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'skipped': len(result.skipped) if hasattr(result, 'skipped') else 0,
        'success': result.wasSuccessful()
    }

def run_integration_test():
    """
    Run the integration test script.
    """
    logger.info("Running integration tests...")
    
    # Setup the path
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    try:
        # Import and run the test directly
        from test_integration import IntegrationTest
        test_suite = unittest.TestLoader().loadTestsFromTestCase(IntegrationTest)
        test_runner = unittest.TextTestRunner(verbosity=2)
        result = test_runner.run(test_suite)
        
        return {
            'total': result.testsRun,
            'failures': len(result.failures),
            'errors': len(result.errors),
            'skipped': len(result.skipped) if hasattr(result, 'skipped') else 0,
            'success': result.wasSuccessful()
        }
    except Exception as e:
        logger.error(f"Error running integration tests: {str(e)}")
        return {
            'total': 0,
            'failures': 0,
            'errors': 1,
            'skipped': 0,
            'success': False,
            'error_message': str(e)
        }

def run_docker_health_check():
    """
    Run a health check on the dockerized application.
    """
    logger.info("Running Docker health check...")
    
    try:
        import requests
        import docker
        
        # Check if Docker is running
        client = docker.from_env()
        containers = client.containers.list()
        
        # Look for our containers
        flask_container = None
        atlantis_container = None
        
        for container in containers:
            if 'web' in container.name:
                flask_container = container
            elif 'atlantis' in container.name:
                atlantis_container = container
        
        if not flask_container or not atlantis_container:
            logger.warning("Could not find the application containers")
            return {
                'success': False,
                'message': "Application containers not found"
            }
        
        # Check Flask app health
        flask_healthy = False
        try:
            # Get the container's network settings
            flask_port = None
            for port, binding in flask_container.ports.items():
                if port.startswith('5150'):
                    flask_port = binding[0]['HostPort']
                    break
            
            if flask_port:
                response = requests.get(f"http://localhost:{flask_port}/healthz", timeout=5)
                flask_healthy = response.status_code == 200
        except Exception as e:
            logger.error(f"Error checking Flask health: {str(e)}")
        
        # Check Atlantis health
        atlantis_healthy = False
        try:
            # Get the container's network settings
            atlantis_port = None
            for port, binding in atlantis_container.ports.items():
                if port.startswith('4141'):
                    atlantis_port = binding[0]['HostPort']
                    break
            
            if atlantis_port:
                response = requests.get(f"http://localhost:{atlantis_port}/healthz", timeout=5)
                atlantis_healthy = response.status_code == 200
        except Exception as e:
            logger.error(f"Error checking Atlantis health: {str(e)}")
        
        return {
            'success': flask_healthy and atlantis_healthy,
            'flask_healthy': flask_healthy,
            'atlantis_healthy': atlantis_healthy
        }
    except ImportError:
        logger.warning("Docker or requests package not available, skipping Docker health check")
        return {
            'success': False,
            'message': "Docker or requests package not available"
        }
    except Exception as e:
        logger.error(f"Error running Docker health check: {str(e)}")
        return {
            'success': False,
            'message': str(e)
        }

def generate_report(unit_test_results, integration_test_results, docker_health_results):
    """
    Generate a report of the test results.
    """
    logger.info("Generating test report...")
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'unit_tests': unit_test_results,
        'integration_tests': integration_test_results,
        'docker_health': docker_health_results,
        'overall_success': (
            unit_test_results.get('success', False) and 
            integration_test_results.get('success', False) and 
            docker_health_results.get('success', False)
        )
    }
    
    # Write the report to a file
    with open('test_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    # Print a summary to the console
    print("\n" + "="*80)
    print("TEST REPORT")
    print("="*80)
    print(f"Timestamp: {report['timestamp']}")
    print(f"Overall Success: {report['overall_success']}")
    print("\nUnit Tests:")
    print(f"  Total: {unit_test_results.get('total', 0)}")
    print(f"  Failures: {unit_test_results.get('failures', 0)}")
    print(f"  Errors: {unit_test_results.get('errors', 0)}")
    print(f"  Skipped: {unit_test_results.get('skipped', 0)}")
    print(f"  Success: {unit_test_results.get('success', False)}")
    print("\nIntegration Tests:")
    print(f"  Total: {integration_test_results.get('total', 0)}")
    print(f"  Failures: {integration_test_results.get('failures', 0)}")
    print(f"  Errors: {integration_test_results.get('errors', 0)}")
    print(f"  Skipped: {integration_test_results.get('skipped', 0)}")
    print(f"  Success: {integration_test_results.get('success', False)}")
    print("\nDocker Health Check:")
    print(f"  Success: {docker_health_results.get('success', False)}")
    if 'flask_healthy' in docker_health_results:
        print(f"  Flask Healthy: {docker_health_results['flask_healthy']}")
    if 'atlantis_healthy' in docker_health_results:
        print(f"  Atlantis Healthy: {docker_health_results['atlantis_healthy']}")
    if 'message' in docker_health_results:
        print(f"  Message: {docker_health_results['message']}")
    print("="*80)
    
    return report

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Run tests for the SSB Build Server Web application.')
    parser.add_argument('--skip-unit', action='store_true', help='Skip unit tests')
    parser.add_argument('--skip-integration', action='store_true', help='Skip integration tests')
    parser.add_argument('--skip-docker', action='store_true', help='Skip Docker health check')
    args = parser.parse_args()
    
    # Run the tests
    unit_test_results = {'success': True, 'total': 0, 'skipped': 'all'} if args.skip_unit else run_unit_tests()
    integration_test_results = {'success': True, 'total': 0, 'skipped': 'all'} if args.skip_integration else run_integration_test()
    docker_health_results = {'success': True, 'skipped': True} if args.skip_docker else run_docker_health_check()
    
    # Generate and return the report
    report = generate_report(unit_test_results, integration_test_results, docker_health_results)
    
    # Exit with a non-zero code if any tests failed
    if not report['overall_success']:
        sys.exit(1)

if __name__ == '__main__':
    main()
