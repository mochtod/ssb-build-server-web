/**
 * vSphere Sync Status Checker
 * 
 * This script checks the status of vSphere synchronization and shows a progress bar
 * while waiting for it to complete.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on the main page where we need the vsphere sync status
    const datacenterSelect = document.getElementById('vsphere_datacenter');
    if (!datacenterSelect) return;
    
    // Start checking vSphere sync status
    checkVSphereSyncStatus();
});

/**
 * Check vSphere synchronization status and show progress
 */
function checkVSphereSyncStatus() {
    // Start progress bar for vSphere sync
    startProgress('Synchronizing vSphere data...', 100, 'info');
    let progress = 0;
    let completed = false;
    let hasStartedProgress = false;
    
    // Function to update the progress bar animation
    function updateSyncProgress() {
        if (completed) return;
        
        // Increment progress slowly (max 95% until we know it's really done)
        if (progress < 95) {
            // Initial jump to 10% to show activity
            if (!hasStartedProgress) {
                progress = 10;
                hasStartedProgress = true;
            } else {
                // Slow down progress as we approach 95%
                const increment = Math.max(1, Math.floor((95 - progress) / 10));
                progress += increment;
            }
            
            // Update the progress bar
            const progressBar = document.getElementById('loading-progress-bar');
            if (progressBar) {
                progressBar.style.width = `${progress}%`;
                const progressText = document.getElementById('loading-progress-percentage');
                if (progressText) {
                    progressText.textContent = `${progress}%`;
                }
            }
        }
    }

    // Start with initial progress update
    updateSyncProgress();
    
    // Setup an interval to update progress regularly
    const progressInterval = setInterval(updateSyncProgress, 1500);
    
    // Check status API every few seconds
    function checkStatus() {
        fetch('/api/vsphere-sync-status')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.completed) {
                    // Stop the progress animation
                    clearInterval(progressInterval);
                    completed = true;
                    
                    if (data.status === 'success') {
                        // Complete the progress bar
                        completeProgress(data.message, 'success', true);
                        
                        // If we have data, reload the page to show the dropdown values
                        if (data.has_data) {
                            // Wait a moment before refreshing the select options
                            setTimeout(() => {
                                const datacenterSelect = document.getElementById('vsphere_datacenter');
                                if (datacenterSelect) {
                                    // Trigger a change event on the datacenter select to load resource pools
                                    const event = new Event('change');
                                    datacenterSelect.dispatchEvent(event);
                                }
                            }, 500);
                        }
                    } else {
                        // Show error
                        setProgressError(data.message);
                        
                        // Add a retry button
                        const progressContainer = document.getElementById('loading-progress-container');
                        if (progressContainer) {
                            const retryButton = document.createElement('button');
                            retryButton.className = 'btn btn-sm btn-warning mt-2';
                            retryButton.textContent = 'Retry Sync';
                            retryButton.onclick = function() {
                                // Reload the page to try again
                                window.location.reload();
                            };
                            progressContainer.appendChild(retryButton);
                        }
                    }
                } else {
                    // Still in progress, check again after a delay
                    setTimeout(checkStatus, 2000);
                }
            })
            .catch(error => {
                console.error('Error checking vSphere sync status:', error);
                // Still try again after a longer delay
                setTimeout(checkStatus, 5000);
            });
    }
    
    // Start checking status
    checkStatus();
}
