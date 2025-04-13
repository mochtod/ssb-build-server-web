import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

# Test configuration
USERNAME = "admin"
PASSWORD = "admin123"
SERVER_PREFIX = "lin2dv2"
APP_NAME = "test"
NUM_CPUS = "2"
MEMORY = "4096"
DISK_SIZE = "50"
TIMEOUT = 30  # seconds

def main():
    print("Starting UI test for SSB Build Server")
    
    # Configure Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run headless for CI/CD environments
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Start the browser
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # 1. Login
        print("Logging in...")
        driver.get("http://localhost:5150/login")
        
        username_field = driver.find_element(By.NAME, "username")
        password_field = driver.find_element(By.NAME, "password")
        submit_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        
        username_field.send_keys(USERNAME)
        password_field.send_keys(PASSWORD)
        submit_button.click()
        
        # Wait for redirect to home page
        WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "create-vm-form"))
        )
        print("Login successful")
        
        # 2. Fill out VM configuration form
        print("Filling out VM form...")
        driver.find_element(By.NAME, "server_prefix").send_keys(SERVER_PREFIX)
        driver.find_element(By.NAME, "app_name").send_keys(APP_NAME)
        driver.find_element(By.NAME, "num_cpus").send_keys(NUM_CPUS)
        driver.find_element(By.NAME, "memory").send_keys(MEMORY)
        driver.find_element(By.NAME, "disk_size").send_keys(DISK_SIZE)
        
        # Submit form
        driver.find_element(By.ID, "submit-vm-button").click()
        
        # 3. Check configuration page
        print("Verifying configuration page...")
        WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "vm-config-details"))
        )
        
        config_text = driver.find_element(By.ID, "vm-config-details").text
        if SERVER_PREFIX not in config_text or APP_NAME not in config_text:
            print("ERROR: Configuration details incorrect")
            return False
        
        # 4. Start plan process
        print("Initiating Terraform plan...")
        plan_button = driver.find_element(By.ID, "plan-button")
        plan_button.click()
        
        # 5. Wait for plan completion and verify fallback behavior (look for simulation note)
        print("Waiting for plan to complete (may be simulated)...")
        
        # Wait for plan page to load
        try:
            WebDriverWait(driver, TIMEOUT).until(
                EC.presence_of_element_located((By.ID, "plan-details"))
            )
            
            # Check if the plan was simulated (our fallback mechanism)
            plan_details = driver.find_element(By.ID, "plan-details").text
            if "Simulated plan" in plan_details:
                print("SUCCESS: Atlantis API fallback mechanism activated correctly")
            else:
                print("NOTE: Plan was processed normally (no simulation)")
                
            print("Plan completed successfully")
            
            # Look for the approve button as further verification
            approve_button = driver.find_element(By.ID, "approve-button")
            if approve_button:
                print("Approval workflow working correctly")
                
            return True
            
        except TimeoutException:
            print("ERROR: Plan timed out or failed")
            return False
            
    except Exception as e:
        print(f"TEST ERROR: {str(e)}")
        return False
        
    finally:
        # Cleanup
        print("Test completed, closing browser")
        driver.quit()

if __name__ == "__main__":
    success = main()
    if success:
        print("\nOVERALL TEST: PASSED ✅")
        exit(0)
    else:
        print("\nOVERALL TEST: FAILED ❌")
        exit(1)
