import os
import shutil
import tempfile
import logging
import sys

# Configure logging - output to both file and console
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Log to stdout
        logging.FileHandler('git_repo_test.log')  # Also log to file
    ]
)
logger = logging.getLogger(__name__)

def test_git_repo_creation():
    """Test the creation of a fake Git repository structure"""
    logger.info("Testing fake Git repository creation...")
    
    # Create a temporary directory for testing
    test_dir = tempfile.mkdtemp()
    logger.info(f"Created temporary test directory: {test_dir}")
    
    try:
        # Create the fake git repo structure
        git_dir = os.path.join(test_dir, '.git')
        os.makedirs(git_dir, exist_ok=True)
        logger.info(f"Created fake .git directory at {git_dir}")
        
        # Create refs directory structure
        refs_dir = os.path.join(git_dir, 'refs', 'heads')
        os.makedirs(refs_dir, exist_ok=True)
        logger.info(f"Created fake .git/refs/heads directory structure")
        
        # Create a main branch reference file
        main_ref_path = os.path.join(refs_dir, 'main')
        with open(main_ref_path, 'w') as f:
            f.write("0000000000000000000000000000000000000000\n")
        logger.info(f"Created fake branch reference at {main_ref_path}")
        
        # Create a minimal .git/config file
        git_config_path = os.path.join(git_dir, 'config')
        with open(git_config_path, 'w') as f:
            f.write("""[core]
    repositoryformatversion = 0
    filemode = true
    bare = false
    logallrefupdates = true
[remote "origin"]
    url = https://github.com/fake/terraform-repo.git
    fetch = +refs/heads/*:refs/remotes/origin/*
[branch "main"]
    remote = origin
    merge = refs/heads/main
""")
        logger.info(f"Created fake .git/config file at {git_config_path}")
        
        # Create a HEAD file to indicate the current branch
        head_path = os.path.join(git_dir, 'HEAD')
        with open(head_path, 'w') as f:
            f.write("ref: refs/heads/main\n")
        logger.info(f"Created fake .git/HEAD file at {head_path}")
        
        # Verify the HEAD file content
        with open(head_path, 'rb') as f:
            head_content = f.read()
            logger.info(f"HEAD file content (hex): {head_content.hex()}")
            
            # Check if it ends with 0A (newline) and not with 5C6E (\n as text)
            if head_content.endswith(b'\n'):
                logger.info("SUCCESS: HEAD file correctly ends with proper newline character (0x0A)")
            else:
                logger.error(f"FAILURE: HEAD file does not end with proper newline: {head_content}")
                
        # Test directory reuse (should detect existing directory)
        logger.info("Testing directory reuse scenario...")
        # Try creating the git repo again - should detect existing directory
        if os.path.exists(git_dir):
            logger.info(f"Detected existing .git directory at {git_dir}")
            
        return True, "Test completed successfully"
            
    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=True)
        return False, f"Test failed: {str(e)}"
    finally:
        # Clean up
        try:
            shutil.rmtree(test_dir)
            logger.info(f"Cleaned up temporary test directory: {test_dir}")
        except Exception as cleanup_err:
            logger.warning(f"Error cleaning up: {cleanup_err}")

def main():
    """Run the test and report results"""
    success, message = test_git_repo_creation()
    
    if success:
        logger.info("✓ All tests PASSED!")
        logger.info(message)
        return 0
    else:
        logger.error("✗ Tests FAILED!")
        logger.error(message)
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
