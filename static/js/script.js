/**
 * VM Provisioning Tool JavaScript
 * 
 * Handles dynamic behavior for the VM provisioning web application.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Server name preview
    initializeServerNamePreview();
    
    // Additional disks functionality
    initializeAdditionalDisks();
    
    // Copy functionality for receipts
    initializeCopyButtons();
    
    // Plan status checking
    initializePlanStatusCheck();
});

/**
 * Initialize server name preview functionality
 */
function initializeServerNamePreview() {
    const serverPrefixSelect = document.getElementById('server_prefix');
    const appNameInput = document.getElementById('app_name');
    const namePreview = document.getElementById('name_preview');
    
    if (serverPrefixSelect && appNameInput && namePreview) {
        const updateNamePreview = function() {
            const prefix = serverPrefixSelect.value || 'lin2xx';
            const appName = appNameInput.value || 'app';
            namePreview.textContent = `${prefix}-${appName}-10001`;
        };
        
        serverPrefixSelect.addEventListener('change', updateNamePreview);
        appNameInput.addEventListener('input', updateNamePreview);
        
        // Initial update
        updateNamePreview();
    }
}

/**
 * Initialize additional disks functionality
 */
function initializeAdditionalDisks() {
    const addDiskButton = document.getElementById('add_disk');
    const diskListContainer = document.querySelector('.disk-list');
    
    if (addDiskButton && diskListContainer) {
        let diskCount = 0;
        
        addDiskButton.addEventListener('click', function() {
            if (diskCount >= 3) {
                alert('Maximum of 3 additional disks allowed');
                return;
            }
            
            const diskItem = document.createElement('div');
            diskItem.className = 'disk-item';
            diskItem.innerHTML = `
                <div class="form-group">
                    <label for="additional_disk_size_${diskCount}">Size (GB):</label>
                    <select id="additional_disk_size_${diskCount}" name="additional_disk_size_${diskCount}">
                        <option value="50">50 GB</option>
                        <option value="100">100 GB</option>
                        <option value="200">200 GB</option>
                        <option value="500">500 GB</option>
                        <option value="1000">1 TB</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="additional_disk_type_${diskCount}">Type:</label>
                    <select id="additional_disk_type_${diskCount}" name="additional_disk_type_${diskCount}">
                        <option value="thin">Thin</option>
                        <option value="thick">Thick</option>
                    </select>
                </div>
                <button type="button" class="remove-disk" data-index="${diskCount}">Remove</button>
            `;
            
            diskListContainer.appendChild(diskItem);
            
            // Add remove event listener
            diskItem.querySelector('.remove-disk').addEventListener('click', function() {
                diskListContainer.removeChild(diskItem);
                diskCount--;
            });
            
            diskCount++;
        });
    }
}

/**
 * Initialize copy buttons for receipt and code blocks
 */
function initializeCopyButtons() {
    // Copy receipt text
    const copyReceiptButton = document.getElementById('copy-receipt');
    if (copyReceiptButton) {
        copyReceiptButton.addEventListener('click', function() {
            const receiptText = document.getElementById('receipt-text').innerText;
            
            navigator.clipboard.writeText(receiptText)
                .then(() => {
                    copyReceiptButton.textContent = 'Copied!';
                    setTimeout(() => {
                        copyReceiptButton.textContent = 'Copy Receipt';
                    }, 2000);
                })
                .catch(err => {
                    console.error('Failed to copy text: ', err);
                    alert('Failed to copy receipt. Please try again.');
                });
        });
    }
    
    // Copy code blocks
    const copyCodeButtons = document.querySelectorAll('.copy-code');
    copyCodeButtons.forEach(button => {
        button.addEventListener('click', function() {
            const codeBlock = this.closest('.code-container').querySelector('code');
            const codeText = codeBlock.innerText;
            
            navigator.clipboard.writeText(codeText)
                .then(() => {
                    this.textContent = 'Copied!';
                    setTimeout(() => {
                        this.textContent = 'Copy';
                    }, 2000);
                })
                .catch(err => {
                    console.error('Failed to copy code: ', err);
                    alert('Failed to copy code. Please try again.');
                });
        });
    });
}

/**
 * Initialize plan status checking for auto-refresh
 */
function initializePlanStatusCheck() {
    const planStatusSection = document.querySelector('.plan-status-section.planning');
    
    if (planStatusSection) {
        const requestId = planStatusSection.getAttribute('data-request-id');
        const timestamp = planStatusSection.getAttribute('data-timestamp');
        
        if (requestId && timestamp) {
            // Check every 5 seconds if plan is complete
            const checkInterval = setInterval(() => {
                fetch(`/check_plan_status/${requestId}_${timestamp}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.status !== 'planning') {
                            clearInterval(checkInterval);
                            window.location.reload();
                        }
                    })
                    .catch(error => {
                        console.error('Error checking plan status:', error);
                    });
            }, 5000);
        }
    }
}

/**
 * Download Terraform configuration
 */
function downloadConfig(requestId, timestamp) {
    fetch(`/download/${requestId}_${timestamp}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Create blob and download
                const blob = new Blob([data.content], { type: 'text/plain' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = data.filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
            } else {
                alert('Error downloading file: ' + data.message);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error downloading file');
        });
}

/**
 * Confirm action with a custom dialog
 */
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}
