/**
 * Cache Loading Indicator
 * 
 * This JavaScript file handles displaying a loading indicator while the vSphere resource cache
 * is being populated in the background.
 */

document.addEventListener('DOMContentLoaded', function() {
    initializeCacheLoadingIndicator();
});

/**
 * Initialize the cache loading indicator
 */
function initializeCacheLoadingIndicator() {
    // Check if we're on the index page and logged in
    const formElement = document.querySelector('form.vm-form');
    if (!formElement) return;
    
    // Create a loading overlay container
    const loadingOverlay = document.createElement('div');
    loadingOverlay.className = 'cache-loading-overlay';
    loadingOverlay.style.display = 'none';
    
    // Create spinner and message
    const loadingContent = document.createElement('div');
    loadingContent.className = 'cache-loading-content';
    
    const spinner = document.createElement('div');
    spinner.className = 'cache-loading-spinner';
    
    const message = document.createElement('div');
    message.className = 'cache-loading-message';
    message.textContent = 'Loading vSphere resources...';
    
    // Append elements
    loadingContent.appendChild(spinner);
    loadingContent.appendChild(message);
    loadingOverlay.appendChild(loadingContent);
    
    // Add styles
    const style = document.createElement('style');
    style.textContent = `
        .cache-loading-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.7);
            z-index: 1000;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        
        .cache-loading-content {
            background-color: #222;
            padding: 30px;
            border-radius: 5px;
            text-align: center;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
        }
        
        .cache-loading-spinner {
            width: 50px;
            height: 50px;
            border: 5px solid rgba(255, 255, 255, 0.1);
            border-top: 5px solid #007bff;
            border-radius: 50%;
            margin: 0 auto 20px;
            animation: spin 1s linear infinite;
        }
        
        .cache-loading-message {
            color: #fff;
            font-size: 18px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    `;
    document.head.appendChild(style);
    document.body.appendChild(loadingOverlay);
    
    // Show loading indicator immediately
    showCacheLoadingIndicator();
    
    // Check if vSphere inventory is ready
    checkVSphereInventoryStatus();
}

/**
 * Show the cache loading indicator
 */
function showCacheLoadingIndicator() {
    const overlay = document.querySelector('.cache-loading-overlay');
    if (overlay) {
        overlay.style.display = 'flex';
        // Disable form interaction while loading
        const formElement = document.querySelector('form.vm-form');
        if (formElement) {
            formElement.classList.add('form-loading');
            const inputs = formElement.querySelectorAll('input, select, button');
            inputs.forEach(input => {
                input.disabled = true;
            });
        }
    }
}

/**
 * Hide the cache loading indicator
 */
function hideCacheLoadingIndicator() {
    const overlay = document.querySelector('.cache-loading-overlay');
    if (overlay) {
        overlay.style.display = 'none';
        // Re-enable form interaction
        const formElement = document.querySelector('form.vm-form');
        if (formElement) {
            formElement.classList.remove('form-loading');
            const inputs = formElement.querySelectorAll('input, select, button');
            inputs.forEach(input => {
                input.disabled = false;
            });
        }
    }
}

/**
 * Check if vSphere inventory is available
 */
function checkVSphereInventoryStatus() {
    fetch('/api/vsphere-inventory')
        .then(response => {
            if (!response.ok) {
                // If not ready, check again in 2 seconds
                setTimeout(checkVSphereInventoryStatus, 2000);
                return;
            }
            return response.json();
        })
        .then(data => {
            if (data && data.datacenters && data.datacenters.length > 0) {
                // If we have data, hide the loading indicator
                hideCacheLoadingIndicator();
            } else {
                // Try again in 2 seconds
                setTimeout(checkVSphereInventoryStatus, 2000);
            }
        })
        .catch(error => {
            console.error('Error checking vSphere inventory status:', error);
            // Try again in 2 seconds even if error
            setTimeout(checkVSphereInventoryStatus, 2000);
        });
}
