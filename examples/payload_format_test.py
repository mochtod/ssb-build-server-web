#!/usr/bin/env python3
"""
Payload Format Test for Atlantis API.

This script validates the format of the Atlantis apply API payload without
sending it to the server. It confirms that the original issue (missing 'dir' field)
is fixed in the payload generation.
"""
import os
import json
import sys
import argparse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Test Atlantis API payload format')
    parser.add_argument('--orig', action='store_true', help='Test original (broken) payload format')
    parser.add_argument('--fixed', action='store_true', help='Test fixed payload format')
    parser.add_argument('--strict', action='store_true', help='Require exact field set match (not just inclusion)')
    
    args = parser.parse_args()
    if not (args.orig or args.fixed):
        args.fixed = True  # Default to fixed format if none specified
    return args

def generate_original_payload():
    """Generate the original payload format that was missing the 'dir' field"""
    # This is the original format before the fix, missing the 'dir' field
    payload = {
        'repo': {
            'owner': 'fake',
            'name': 'terraform-repo',
            'clone_url': 'https://github.com/fake/terraform-repo.git'
        },
        'pull_request': {
            'num': 1,
            'branch': 'main',
            'author': 'Test User'
        },
        'head_commit': 'abcd1234',
        'pull_num': 1,
        'pull_author': 'Test User',
        'repo_rel_dir': 'test-dir',
        'workspace': 'development',
        'project_name': 'test-project',
        'plan_id': 'sim-test12345',
        'comment': 'Testing Atlantis apply API',
        'user': 'Test User',
        'verbose': True,
        'cmd': 'apply',
        'terraform_files': {
            'main.tf': 'output "test" { value = "Hello, World!" }'
        }
    }
    return payload

def generate_fixed_payload():
    """Generate the fixed payload format that includes the 'dir' field"""
    # This is the fixed format that includes the 'dir' field
    payload = {
        'repo': {
            'owner': 'fake',
            'name': 'terraform-repo',
            'clone_url': 'https://github.com/fake/terraform-repo.git'
        },
        'pull_request': {
            'num': 1,
            'branch': 'main',
            'author': 'Test User'
        },
        'head_commit': 'abcd1234',
        'pull_num': 1,
        'pull_author': 'Test User',
        'repo_rel_dir': 'test-dir',
        'workspace': 'development',
        'project_name': 'test-project',
        'plan_id': 'sim-test12345',
        'comment': 'Testing Atlantis apply API',
        'user': 'Test User',
        'verbose': True,
        'cmd': 'apply',
        'dir': '.',  # This field is added in the fix
        'terraform_files': {
            'main.tf': 'output "test" { value = "Hello, World!" }'
        }
    }
    return payload

def validate_payload(payload, strict=False):
    """Validate that the payload has all required fields"""
    required_fields = [
        'repo', 'pull_request', 'head_commit', 'pull_num', 'pull_author',
        'repo_rel_dir', 'workspace', 'project_name', 'plan_id', 'comment',
        'user', 'cmd', 'dir'
    ]
    
    # Check for missing required fields
    missing_fields = [field for field in required_fields if field not in payload]
    
    # Check for expected nested fields
    if 'repo' in payload:
        repo_fields = ['owner', 'name', 'clone_url']
        missing_repo_fields = [field for field in repo_fields if field not in payload['repo']]
        if missing_repo_fields:
            missing_fields.append(f"repo.{missing_repo_fields}")
    
    if 'pull_request' in payload:
        pr_fields = ['num', 'branch', 'author']
        missing_pr_fields = [field for field in pr_fields if field not in payload['pull_request']]
        if missing_pr_fields:
            missing_fields.append(f"pull_request.{missing_pr_fields}")
    
    # If strict, also check that no extra fields are present
    extra_fields = []
    if strict:
        extra_fields = [field for field in payload if field not in required_fields + ['terraform_files', 'verbose']]
    
    # Return validation results
    return {
        'valid': len(missing_fields) == 0 and len(extra_fields) == 0,
        'missing_fields': missing_fields,
        'extra_fields': extra_fields
    }

def main():
    args = parse_args()
    
    if args.orig:
        logger.info("Testing ORIGINAL payload format (before fix)")
        payload = generate_original_payload()
    else:
        logger.info("Testing FIXED payload format (after fix)")
        payload = generate_fixed_payload()
    
    # Print payload
    logger.info("Generated Payload:")
    pretty_payload = json.dumps(payload, indent=2)
    print(pretty_payload)
    
    # Validate payload
    validation = validate_payload(payload, args.strict)
    
    # Print validation results
    if validation['valid']:
        logger.info("Payload format is VALID! ✓")
        print("\n✅ All required fields are present in the correct format.")
    else:
        logger.error("Payload format is INVALID! ✗")
        
        if validation['missing_fields']:
            print("\n❌ Missing required fields:")
            for field in validation['missing_fields']:
                print(f"  - {field}")
        
        if validation['extra_fields']:
            print("\n⚠️ Extra fields (not in required list):")
            for field in validation['extra_fields']:
                print(f"  - {field}")
    
    return 0 if validation['valid'] else 1

if __name__ == "__main__":
    sys.exit(main())
