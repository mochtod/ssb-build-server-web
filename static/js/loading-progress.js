/**
 * Loading Progress Bar Management
 * 
 * This file handles the global loading progress bar functionality
 * to provide users with visual feedback about background processes.
 */

// Progress bar elements
let progressContainer = null;
let progressBar = null;
let progressText = null;
let progressPercentage = null;

// Progress state
let currentTask = '';
let currentStatus = 'info';
let totalSteps = 0;
let completedSteps = 0;
let isProgressActive = false;

document.addEventListener('DOMContentLoaded', function() {
    initializeProgressBar();
    
    // Add a debug message to confirm the script is running
    console.log('Loading progress bar initialized and ready');
    
    // Test line removed for production
});

/**
 * Initialize the progress bar elements and variables
 */
function initializeProgressBar() {
    // Get progress bar elements
    progressContainer = document.getElementById('loading-progress-container');
    progressBar = document.getElementById('loading-progress-bar');
    progressText = document.getElementById('loading-progress-text');
    progressPercentage = document.getElementById('loading-progress-percentage');
    
    if (!progressContainer || !progressBar || !progressText || !progressPercentage) {
        console.error('Progress bar elements not found in the DOM');
        return;
    }
    
    // Ensure the container has the right styles to be visible
    progressContainer.style.position = 'relative';
    progressContainer.style.zIndex = '1000';
    progressContainer.style.marginBottom = '20px';
    
    console.log('Progress bar elements found and initialized');
}

/**
 * Start the progress bar for a task
 * @param {string} taskName - Name of the task
 * @param {number} steps - Total number of steps for this task
 * @param {string} status - Status type (info, warning, error, success)
 */
function startProgress(taskName, steps, status = 'info') {
    if (!progressContainer) return;
    
    // Reset progress
    currentTask = taskName;
    currentStatus = status;
    totalSteps = steps;
    completedSteps = 0;
    isProgressActive = true;
    
    // Update UI
    progressText.textContent = taskName;
    progressPercentage.textContent = '0%';
    progressBar.style.width = '0%';
    progressBar.className = `loading-progress-bar ${status}`;
    progressBar.classList.add('loading-active');
    
    // Show the container
    progressContainer.style.display = 'block';
    
    console.log(`Started progress tracking: ${taskName} (${steps} steps)`);
}

/**
 * Update the progress bar
 * @param {number} steps - Number of steps completed (default: 1)
 * @param {string} message - Optional message to display
 */
function updateProgress(steps = 1, message = null) {
    if (!isProgressActive || !progressContainer) return;
    
    // Update completed steps
    completedSteps += steps;
    
    // Calculate percentage and clamp between 0-100
    const percent = Math.min(Math.max(Math.floor((completedSteps / totalSteps) * 100), 0), 100);
    
    // Update UI
    progressBar.style.width = `${percent}%`;
    progressPercentage.textContent = `${percent}%`;
    
    // Update message if provided
    if (message) {
        progressText.textContent = message;
    }
    
    console.log(`Progress updated: ${percent}% (${completedSteps}/${totalSteps})`);
}

/**
 * Complete the progress bar
 * @param {string} message - Completion message
 * @param {string} status - Final status (success, error, warning)
 * @param {boolean} autoHide - Whether to auto-hide the bar after completion
 */
function completeProgress(message, status = 'success', autoHide = true) {
    if (!progressContainer) return;
    
    // Set to 100%
    progressBar.style.width = '100%';
    progressPercentage.textContent = '100%';
    progressText.textContent = message;
    
    // Update status
    progressBar.className = `loading-progress-bar ${status}`;
    progressBar.classList.remove('loading-active');
    
    isProgressActive = false;
    console.log(`Progress completed: ${message}`);
    
    // Auto-hide after delay if requested
    if (autoHide) {
        setTimeout(() => {
            hideProgress();
        }, 3000);
    }
}

/**
 * Hide the progress bar
 */
function hideProgress() {
    if (!progressContainer) return;
    progressContainer.style.display = 'none';
    isProgressActive = false;
}

/**
 * Set an error state for the progress bar
 * @param {string} errorMessage - Error message to display
 */
function setProgressError(errorMessage) {
    if (!progressContainer) return;
    
    progressText.textContent = errorMessage;
    progressBar.className = 'loading-progress-bar error';
    progressBar.classList.remove('loading-active');
    
    console.error(`Progress error: ${errorMessage}`);
}

/**
 * Update the status message (both in the progress bar and status area if exists)
 * @param {string} message - Status message to display
 * @param {string} status - Status type (info, warning, error, success)
 */
function updateStatusMessage(message, status = 'info') {
    // Update in progress bar if active
    if (isProgressActive && progressText) {
        progressText.textContent = message;
        progressBar.className = `loading-progress-bar ${status}`;
    }
    
    // Create a status message element if one doesn't exist
    let statusElement = document.getElementById('status-message');
    if (!statusElement) {
        statusElement = document.createElement('div');
        statusElement.id = 'status-message';
        statusElement.className = `status-message ${status}`;
        
        // Insert after the progress bar if it exists, otherwise after header
        const header = document.querySelector('header');
        if (header && header.nextElementSibling) {
            header.parentNode.insertBefore(statusElement, header.nextElementSibling);
        }
    }
    
    // Update status element
    statusElement.textContent = message;
    statusElement.className = `status-message ${status}`;
    
    // Make it visible
    statusElement.style.display = 'block';    
    // Auto-hide after delay for success messages
    if (status === 'success') {
        setTimeout(() => {
            statusElement.style.display = 'none';
        }, 5000);
    }
    
    console.log(`Status message updated: ${message} (${status})`);
}

/**
 * Test function to verify the progress bar is working
 * This can be removed after confirming the progress bar works
 */
function testProgressBar() {
    console.log('Running progress bar test');
    
    // Start with 10 steps
    startProgress('Testing progress bar functionality', 10, 'info');
    
    // Simulate progress steps with delays
    for (let i = 1; i <= 10; i++) {
        setTimeout(() => {
            updateProgress(1, `Test step ${i} of 10 completed`);
            
            // Complete on the last step
            if (i === 10) {
                setTimeout(() => {
                    completeProgress('Progress bar test completed successfully', 'success', false);
                }, 500);
            }
        }, i * 500); // 500ms between each step
    }
}
