/**
 * VM Provisioning Tool JavaScript
 * 
 * Handles dynamic behavior for the VM provisioning web application.
 */

// Apply theme as early as possible to prevent flash of wrong theme
(function() {
    // Try to get theme from localStorage first
    let savedTheme = localStorage.getItem('theme');
    
    // If theme not in localStorage, try to get it from cookie
    if (!savedTheme) {
        const themeCookie = document.cookie.split('; ').find(row => row.startsWith('theme='));
        if (themeCookie) {
            savedTheme = themeCookie.split('=')[1];
        }
    }
    
    // If still no theme, default to light
    savedTheme = savedTheme || 'light';
    
    // Apply theme immediately
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-mode');
    }
})();

document.addEventListener('DOMContentLoaded', function() {
    // Server name preview
    initializeServerNamePreview();
    
    // Additional disks functionality
    initializeAdditionalDisks();
    
    // Copy functionality for receipts
    initializeCopyButtons();
    
    // Plan status checking
    initializePlanStatusCheck();
    
    // Theme toggle functionality
    initializeThemeToggle();
    
    // VSphere resource loading
    initializeResourceLoading();
});

/**
 * Initialize theme toggle functionality
 */
function initializeThemeToggle() {
    const themeToggleBtn = document.getElementById('theme-toggle');
    const themeIconDark = document.getElementById('theme-icon-dark');
    const themeIconLight = document.getElementById('theme-icon-light');
    const themeText = document.getElementById('theme-text');
    
    if (themeToggleBtn && themeIconDark && themeIconLight && themeText) {
        // Check for saved theme preference or use default
        const savedTheme = localStorage.getItem('theme') || 'light';
        
        // Apply the saved theme
        setTheme(savedTheme);
        
        // Handle theme toggle click
        themeToggleBtn.addEventListener('click', function() {
            // Check current theme
            const isDarkMode = document.body.classList.contains('dark-mode');
            
            // Determine new theme
            const newTheme = isDarkMode ? 'light' : 'dark';
            
            // Set theme in UI
            setTheme(newTheme);
            
            // Store theme preference in localStorage
            localStorage.setItem('theme', newTheme);
            
            // Also update server-side cookie
            fetch(`/set_theme/${newTheme}`, { 
                method: 'GET',
                credentials: 'same-origin'
            }).catch(error => {
                console.error('Error setting theme cookie:', error);
            });
        });
    }
    
    /**
     * Set theme and update UI elements
     * @param {string} theme - 'dark' or 'light'
     */
    function setTheme(theme) {
        if (theme === 'dark') {
            document.body.classList.add('dark-mode');
            themeIconDark.style.display = 'none';
            themeIconLight.style.display = 'inline-block';
            themeText.textContent = 'Light Mode'; // Shows what mode will be switched to
        } else {
            document.body.classList.remove('dark-mode');
            themeIconDark.style.display = 'inline-block';
            themeIconLight.style.display = 'none';
            themeText.textContent = 'Dark Mode'; // Shows what mode will be switched to
        }
    }
}

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

/**
 * Initialize VSphere resource loading functionality with cluster-centric approach
 * - First loads available clusters
 * - When a cluster is selected, fetches resources specific to that cluster
 * - Displays resources in a hierarchical way
 */
function initializeResourceLoading() {
    // Check if we're on a page with the cluster selection dropdown
    const clusterSelect = document.getElementById('cluster');
    const resourceStatusElement = document.getElementById('resource_status');
    
    // Only proceed if we have the cluster select
    if (clusterSelect) {
        // Add loading indicator to the page
        const loadingIndicator = document.createElement('div');
        loadingIndicator.id = 'resources-loading-indicator';
        loadingIndicator.className = 'notification info';
        loadingIndicator.innerHTML = '<i class="fa fa-sync fa-spin"></i> Loading clusters...';
        
        // Insert loading indicator
        const resourceStatus = document.querySelector('.resource-status');
        if (resourceStatus) {
            resourceStatus.appendChild(loadingIndicator);
        }
        
        // Fetch clusters immediately
        fetchClusters();
        
        // Set up event listener for cluster selection
        clusterSelect.addEventListener('change', function() {
            const clusterId = this.value;
            if (clusterId) {
                loadClusterResources(clusterId);
            } else {
                // Hide all resource sections if no cluster is selected
                document.getElementById('resource_pool_container').style.display = 'none';
                document.getElementById('datastores_container').style.display = 'none';
                document.getElementById('networks_templates_container').style.display = 'none';
                
                if (resourceStatusElement) {
                    resourceStatusElement.textContent = 'Select a cluster to view available resources.';
                }
            }
        });
    }
    
    /**
     * Fetch all available clusters from the API
     */
    function fetchClusters() {
        fetch('/api/vsphere/clusters')
            .then(response => response.json())
            .then(data => {
                if (data.clusters && data.clusters.length > 0) {
                    // Update the cluster dropdown
                    updateClusterDropdown(clusterSelect, data.clusters);
                    
                    // Hide loading indicator
                    const loadingIndicator = document.getElementById('resources-loading-indicator');
                    if (loadingIndicator) {
                        loadingIndicator.style.display = 'none';
                    }
                    
                    // Update status display
                    if (resourceStatusElement) {
                        resourceStatusElement.textContent = `${data.clusters.length} clusters loaded. Select a cluster to continue.`;
                    }
                    
                    console.log(`Loaded ${data.clusters.length} clusters`);
                } else {
                    // Show error message if no clusters found
                    if (resourceStatusElement) {
                        resourceStatusElement.textContent = 'No clusters found. Please check vSphere connection.';
                    }
                }
            })
            .catch(error => {
                console.error('Error fetching clusters:', error);
                
                // Update status to show error
                if (resourceStatusElement) {
                    resourceStatusElement.textContent = 'Error loading clusters. Please refresh the page or contact an administrator.';
                }
            });
    }
    
    /**
     * Load resources for a specific cluster
     */
    function loadClusterResources(clusterId) {
        // Show loading message
        if (resourceStatusElement) {
            resourceStatusElement.textContent = 'Loading resources for selected cluster...';
        }
        
        // Add loading indicator
        const loadingIndicator = document.getElementById('resources-loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.innerHTML = '<i class="fa fa-sync fa-spin"></i> Loading cluster resources...';
            loadingIndicator.style.display = 'block';
        }
        
        // Fetch resources for the selected cluster
        fetch(`/api/vsphere/clusters/${clusterId}/resources`)
            .then(response => response.json())
            .then(data => {
                // Update resource pools (should be only one per cluster)
                if (data.resource_pools && data.resource_pools.length > 0) {
                    const resourcePoolSelect = document.getElementById('resource_pool');
                    updateResourceDropdown(resourcePoolSelect, data.resource_pools);
                    document.getElementById('resource_pool_container').style.display = 'flex';
                    
                    // If there's only one resource pool, select it automatically
                    if (data.resource_pools.length === 1) {
                        resourcePoolSelect.value = data.resource_pools[0].id;
                    }
                }
                
                // Update datastores
                if (data.datastores && data.datastores.length > 0) {
                    const datastoreSelect = document.getElementById('datastore');
                    updateResourceDropdown(datastoreSelect, data.datastores, 'free_gb');
                    document.getElementById('datastores_container').style.display = 'flex';
                }
                
                // Update networks and templates
                if (data.networks && data.networks.length > 0 && 
                    data.templates && data.templates.length > 0) {
                    const networkSelect = document.getElementById('network');
                    const templateSelect = document.getElementById('template');
                    
                    updateResourceDropdown(networkSelect, data.networks);
                    updateResourceDropdown(templateSelect, data.templates);
                    
                    document.getElementById('networks_templates_container').style.display = 'flex';
                }
                
                // Hide loading indicator
                if (loadingIndicator) {
                    loadingIndicator.style.display = 'none';
                }
                
                // Update status display
                if (resourceStatusElement) {
                    const clusterName = data.cluster_name || 'selected cluster';
                    resourceStatusElement.textContent = `Resources loaded for ${clusterName}. Found ${data.datastores.length} datastores, ${data.networks.length} networks, and ${data.templates.length} templates.`;
                }
                
                console.log(`Loaded resources for cluster ${clusterId}`);
            })
            .catch(error => {
                console.error(`Error fetching resources for cluster ${clusterId}:`, error);
                
                // Update status to show error
                if (resourceStatusElement) {
                    resourceStatusElement.textContent = 'Error loading cluster resources. Please try another cluster or refresh the page.';
                }
                
                // Hide loading indicator
                if (loadingIndicator) {
                    loadingIndicator.style.display = 'none';
                }
            });
    }
    
    /**
     * Update the cluster dropdown with the fetched clusters
     */
    function updateClusterDropdown(selectElement, clusterList) {
        if (!selectElement || !clusterList) return;
        
        // Clear existing options (except the first empty option)
        while (selectElement.options.length > 1) {
            selectElement.remove(1);
        }
        
        // Sort clusters by name
        clusterList.sort((a, b) => a.name.localeCompare(b.name));
        
        // Add all clusters to the dropdown
        clusterList.forEach(cluster => {
            const option = document.createElement('option');
            option.value = cluster.id;
            option.textContent = cluster.name;
            
            // Add datacenter info if available
            if (cluster.datacenter) {
                option.textContent += ` (${cluster.datacenter})`;
            }
            
            selectElement.add(option);
        });
    }
    
    /**
     * Update a resource dropdown with the fetched resources
     */
    function updateResourceDropdown(selectElement, resourceList, extraInfoField = null) {
        if (!selectElement || !resourceList) return;
        
        // Get the current selected value
        const currentValue = selectElement.value;
        
        // Clear existing options (except the first empty option)
        while (selectElement.options.length > 1) {
            selectElement.remove(1);
        }
        
        // Sort resources by name
        resourceList.sort((a, b) => a.name.localeCompare(b.name));
        
        // Add all resources to the dropdown
        resourceList.forEach(resource => {
            const option = document.createElement('option');
            option.value = resource.id;
            
            // Basic text is just the resource name
            let optionText = resource.name;
            
            // Add extra information if specified and available
            if (extraInfoField && resource[extraInfoField] !== undefined) {
                if (extraInfoField === 'free_gb') {
                    optionText += ` (${resource[extraInfoField]} GB free)`;
                } else {
                    optionText += ` (${resource[extraInfoField]})`;
                }
            }
            
            option.textContent = optionText;
            selectElement.add(option);
        });
        
        // Restore the previously selected value if it exists
        if (currentValue && selectElement.querySelector(`option[value="${currentValue}"]`)) {
            selectElement.value = currentValue;
        }
    }
}
