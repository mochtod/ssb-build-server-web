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

    // Elements
    const vsphereSection = document.getElementById('vsphere-section');
    const vsphereLoading = document.getElementById('vsphere-loading');
    const vsphereErrorMessage = document.getElementById('vsphere-error-message');
    const retryButton = document.getElementById('retry-vsphere-load');
    
    const vsphereServerSelect = document.getElementById('vsphere_server');
    const datacenterSelect = document.getElementById('datacenter');
    const clusterSelect = document.getElementById('cluster');
    const datastoreClusterSelect = document.getElementById('datastore_cluster');
    const networkSelect = document.getElementById('network');
    const templateSelect = document.getElementById('template');
    
    const serverLoadingStatus = document.getElementById('server-loading-status');
    const datacenterLoadingStatus = document.getElementById('datacenter-loading-status');
    const clusterLoadingStatus = document.getElementById('cluster-loading-status');
    const datastoreLoadingStatus = document.getElementById('datastore-loading-status');
    const networkLoadingStatus = document.getElementById('network-loading-status');
    const templateLoadingStatus = document.getElementById('template-loading-status');
    
    // Initialize the form elements
    initializeVSphereMenus();
    initializeServerNamePreview();
    initializeAdditionalDisks();
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

/**
 * Initialize vSphere menu dropdowns and handle loading states
 */
function initializeVSphereMenus() {
    // Add event listeners for the "Use Cached Data" button
    const useCachedDataBtn = document.getElementById('use-cached-data');
    if (useCachedDataBtn) {
        useCachedDataBtn.addEventListener('click', function() {
            vsphereErrorMessage.style.display = 'none';
            loadCachedVSphereData();
        });
    }
    
    // Set initial loading states
    setLoadingStatus(serverLoadingStatus, 'Connecting to vSphere...', 'loading');
    
    // Update the loading detail and progress bar
    const loadingDetail = document.getElementById('loading-detail');
    const loadingProgressBar = document.getElementById('loading-progress-bar');
    
    // First try to use cached data if available
    loadCachedVSphereData();
    
    // Server selection change handler
    vsphereServerSelect.addEventListener('change', function() {
        const selectedServer = this.value;
        
        if (!selectedServer) {
            resetDropdowns();
            return;
        }
        
        // Load datacenters for selected server
        loadDatacentersForServer(selectedServer);
    });
    
    // Datacenter selection change handler
    datacenterSelect.addEventListener('change', function() {
        const selectedDatacenter = this.value;
        const selectedServer = vsphereServerSelect.value;
        
        if (!selectedDatacenter || !selectedServer) {
            resetClusterAndBelow();
            return;
        }
        
        // Load clusters for selected datacenter
        loadClustersForDatacenter(selectedServer, selectedDatacenter);
        
        // Also load networks as they depend on datacenter
        loadNetworksForDatacenter(selectedServer, selectedDatacenter);
    });
    
    // Cluster selection change handler
    clusterSelect.addEventListener('change', function() {
        const selectedCluster = this.value;
        const selectedDatacenter = datacenterSelect.value;
        const selectedServer = vsphereServerSelect.value;
        
        if (!selectedCluster || !selectedDatacenter || !selectedServer) {
            resetDatastoreClusters();
            return;
        }
        
        // Load datastore clusters for selected cluster
        loadDatastoreClustersForCluster(selectedServer, selectedDatacenter, selectedCluster);
    });
    
    // Retry button handler
    if (retryButton) {
        retryButton.addEventListener('click', function() {
            vsphereErrorMessage.style.display = 'none';
            vsphereLoading.style.display = 'flex';
            triggerEssentialSync();
        });
    }
}

/**
 * Load cached vSphere data to populate the UI
 */
function loadCachedVSphereData() {
    // Show loading
    vsphereLoading.style.display = 'flex';
    vsphereErrorMessage.style.display = 'none';
    
    const loadingDetail = document.getElementById('loading-detail');
    loadingDetail.textContent = 'Loading cached data...';

    // Fetch servers from cache
    fetch('/api/vsphere/servers')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.data && data.data.vsphere_servers) {
                // Hide the main loading indicator
                vsphereLoading.style.display = 'none';
                
                // Populate the server dropdown
                populateSelect(vsphereServerSelect, data.data.vsphere_servers);
                setLoadingStatus(serverLoadingStatus, 'Server list loaded', 'success');
                
                // Enable server dropdown
                vsphereServerSelect.disabled = false;
                
                // Check cache status
                return fetch('/api/vsphere-cache/status');
            } else {
                throw new Error(data.error || 'No vSphere servers found');
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.status) {
                // Check if essential data is cached
                const cacheStatus = data.status.cache_status;
                const datacentersExist = cacheStatus.datacenters.exists;
                const clustersExist = cacheStatus.clusters.exists;
                const templatesExist = cacheStatus.templates.exists;
                
                // If essential data is missing, initiate a background sync
                if (!datacentersExist || !clustersExist || !templatesExist) {
                    console.log('Essential data missing, triggering essential sync');
                    triggerEssentialSync();
                } else {
                    console.log('Using cached data');
                }
            }
        })
        .catch(error => {
            console.error('Error loading cached vSphere data:', error);
            vsphereLoading.style.display = 'none';
            vsphereErrorMessage.style.display = 'block';
            vsphereErrorMessage.textContent = `Error loading vSphere data: ${error.message}`;
            setLoadingStatus(serverLoadingStatus, 'Failed to load servers', 'error');
        });
}

/**
 * Trigger a sync of essential vSphere data
 */
function triggerEssentialSync() {
    const loadingDetail = document.getElementById('loading-detail');
    const loadingProgressBar = document.getElementById('loading-progress-bar');
    
    loadingDetail.textContent = 'Syncing essential data...';
    vsphereLoading.style.display = 'flex';
    vsphereErrorMessage.style.display = 'none';
    
    // Set progress bar to indeterminate state
    loadingProgressBar.style.width = '10%';
    loadingProgressBar.classList.add('indeterminate');
    
    // Trigger the essential sync
    fetch('/api/vsphere-cache/sync-essential', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            loadingDetail.textContent = 'Essential data loaded, syncing additional data...';
            
            // Start monitoring progress of background sync
            monitorSyncProgress();
            
            // Load the essential data into the UI
            loadCachedVSphereData();
        } else {
            throw new Error(data.error || 'Failed to sync essential data');
        }
    })
    .catch(error => {
        console.error('Error syncing essential vSphere data:', error);
        vsphereLoading.style.display = 'none';
        vsphereErrorMessage.style.display = 'block';
        vsphereErrorMessage.textContent = `Error syncing vSphere data: ${error.message}`;
        setLoadingStatus(serverLoadingStatus, 'Failed to sync data', 'error');
    });
}

/**
 * Monitor the progress of a vSphere sync operation
 */
function monitorSyncProgress() {
    const loadingDetail = document.getElementById('loading-detail');
    const loadingProgressBar = document.getElementById('loading-progress-bar');
    
    // Start checking progress
    const progressInterval = setInterval(() => {
        fetch('/api/vsphere-cache/progress')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.progress) {
                    const progress = data.progress;
                    const progressPct = progress.progress || 0;
                    const status = progress.status || 'unknown';
                    const message = progress.message || 'Syncing...';
                    
                    // Update progress bar
                    loadingProgressBar.classList.remove('indeterminate');
                    loadingProgressBar.style.width = `${progressPct}%`;
                    
                    // Update loading detail
                    loadingDetail.textContent = message;
                    
                    // If sync is complete or failed, stop checking
                    if (status === 'complete' || status === 'error') {
                        clearInterval(progressInterval);
                        
                        if (status === 'complete') {
                            // Successfully completed full sync
                            loadingDetail.textContent = 'Sync complete!';
                            setTimeout(() => {
                                vsphereLoading.style.display = 'none';
                            }, 1000);
                        } else {
                            // Error occurred, but we can still use partial data
                            loadingDetail.textContent = 'Sync error, using partial data';
                            setTimeout(() => {
                                vsphereLoading.style.display = 'none';
                            }, 2000);
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Error monitoring sync progress:', error);
                clearInterval(progressInterval);
            });
    }, 2000); // Check every 2 seconds
    
    // Set a timeout to stop checking after 5 minutes
    setTimeout(() => {
        clearInterval(progressInterval);
    }, 5 * 60 * 1000);
}

/**
 * Load datacenters for a selected vSphere server
 */
function loadDatacentersForServer(server) {
    // Reset dependent dropdowns
    resetClusterAndBelow();
    
    // Set loading state
    datacenterSelect.disabled = true;
    setLoadingStatus(datacenterLoadingStatus, 'Loading datacenters...', 'loading');
    
    // Fetch datacenters
    fetch(`/api/vsphere/hierarchical?vsphere_server=${encodeURIComponent(server)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.data && data.data.datacenters) {
                // Populate dropdown
                populateSelect(datacenterSelect, data.data.datacenters);
                datacenterSelect.disabled = false;
                setLoadingStatus(datacenterLoadingStatus, 'Datacenters loaded', 'success');
                
                // Also load templates as they depend on server
                loadTemplatesForServer(server);
            } else {
                throw new Error(data.error || 'No datacenters found');
            }
        })
        .catch(error => {
            console.error('Error loading datacenters:', error);
            setLoadingStatus(datacenterLoadingStatus, 'Failed to load datacenters', 'error');
        });
}

/**
 * Load clusters for a selected datacenter
 */
function loadClustersForDatacenter(server, datacenter) {
    // Reset dependent dropdowns
    resetDatastoreClusters();
    
    // Set loading state
    clusterSelect.disabled = true;
    setLoadingStatus(clusterLoadingStatus, 'Loading clusters...', 'loading');
    
    // Fetch clusters
    fetch(`/api/vsphere/hierarchical?vsphere_server=${encodeURIComponent(server)}&datacenter_id=${encodeURIComponent(datacenter)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.data && data.data.clusters) {
                // Populate dropdown
                populateSelect(clusterSelect, data.data.clusters);
                clusterSelect.disabled = false;
                setLoadingStatus(clusterLoadingStatus, 'Clusters loaded', 'success');
            } else {
                throw new Error(data.error || 'No clusters found');
            }
        })
        .catch(error => {
            console.error('Error loading clusters:', error);
            setLoadingStatus(clusterLoadingStatus, 'Failed to load clusters', 'error');
        });
}

/**
 * Load datastore clusters for a selected cluster
 */
function loadDatastoreClustersForCluster(server, datacenter, cluster) {
    // Set loading state
    datastoreClusterSelect.disabled = true;
    setLoadingStatus(datastoreLoadingStatus, 'Loading datastores...', 'loading');
    
    // Fetch datastore clusters
    fetch(`/api/vsphere/hierarchical?vsphere_server=${encodeURIComponent(server)}&datacenter_id=${encodeURIComponent(datacenter)}&cluster_id=${encodeURIComponent(cluster)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.data && data.data.datastore_clusters) {
                // Populate dropdown
                populateSelect(datastoreClusterSelect, data.data.datastore_clusters);
                datastoreClusterSelect.disabled = false;
                setLoadingStatus(datastoreLoadingStatus, 'Datastores loaded', 'success');
            } else {
                throw new Error(data.error || 'No datastore clusters found');
            }
        })
        .catch(error => {
            console.error('Error loading datastore clusters:', error);
            setLoadingStatus(datastoreLoadingStatus, 'Failed to load datastores', 'error');
        });
}

/**
 * Load networks for a selected datacenter
 */
function loadNetworksForDatacenter(server, datacenter) {
    // Set loading state
    networkSelect.disabled = true;
    setLoadingStatus(networkLoadingStatus, 'Loading networks...', 'loading');
    
    // Fetch networks
    fetch(`/api/vsphere/hierarchical?vsphere_server=${encodeURIComponent(server)}&datacenter_id=${encodeURIComponent(datacenter)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.data && data.data.networks) {
                // Populate dropdown
                populateSelect(networkSelect, data.data.networks);
                networkSelect.disabled = false;
                setLoadingStatus(networkLoadingStatus, 'Networks loaded', 'success');
            } else {
                throw new Error(data.error || 'No networks found');
            }
        })
        .catch(error => {
            console.error('Error loading networks:', error);
            setLoadingStatus(networkLoadingStatus, 'Failed to load networks', 'error');
        });
}

/**
 * Load templates for a selected server
 */
function loadTemplatesForServer(server) {
    // Set loading state
    templateSelect.disabled = true;
    setLoadingStatus(templateLoadingStatus, 'Loading templates...', 'loading');
    
    // Fetch templates
    fetch(`/api/vsphere/hierarchical?vsphere_server=${encodeURIComponent(server)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.data && data.data.templates) {
                // Populate dropdown
                populateSelect(templateSelect, data.data.templates);
                templateSelect.disabled = false;
                setLoadingStatus(templateLoadingStatus, 'Templates loaded', 'success');
                
                // Auto-select RHEL9 template if available
                autoSelectRhel9Template();
            } else {
                throw new Error(data.error || 'No templates found');
            }
        })
        .catch(error => {
            console.error('Error loading templates:', error);
            setLoadingStatus(templateLoadingStatus, 'Failed to load templates', 'error');
        });
}

/**
 * Auto-select RHEL9 template if available
 */
function autoSelectRhel9Template() {
    for (let i = 0; i < templateSelect.options.length; i++) {
        const option = templateSelect.options[i];
        if (option.text.toLowerCase().includes('rhel9')) {
            templateSelect.selectedIndex = i;
            break;
        }
    }
}

/**
 * Set loading status message with appropriate styling
 */
function setLoadingStatus(element, message, status = 'default') {
    if (!element) return;
    
    // Remove all status classes
    element.classList.remove('loading', 'success', 'error', 'warning');
    
    // Set message and add appropriate class
    element.textContent = message;
    
    if (status !== 'default') {
        element.classList.add(status);
    }
}

/**
 * Populate select dropdown from an array of objects
 */
function populateSelect(selectElement, options, valueKey = 'id', textKey = 'name') {
    if (!selectElement) return;
    
    // Save current selection if any
    const currentValue = selectElement.value;
    
    // Clear all options except the first (placeholder)
    while (selectElement.options.length > 1) {
        selectElement.remove(1);
    }
    
    // Check if options is empty or undefined
    if (!options || options.length === 0) {
        const noDataOption = document.createElement('option');
        noDataOption.value = "";
        noDataOption.text = "No data available";
        noDataOption.disabled = true;
        selectElement.appendChild(noDataOption);
        return;
    }
    
    // Add new options
    options.forEach(option => {
        const optionElement = document.createElement('option');
        optionElement.value = option[valueKey] || '';
        optionElement.text = option[textKey] || 'Unnamed';
        selectElement.appendChild(optionElement);
    });
    
    // Try to restore previous selection
    if (currentValue) {
        selectElement.value = currentValue;
    }
}

/**
 * Reset all dropdowns to initial state
 */
function resetDropdowns() {
    // Reset datacenter and below
    resetDatacenterAndBelow();
}

/**
 * Reset datacenter dropdown and its dependents
 */
function resetDatacenterAndBelow() {
    // Reset datacenter
    datacenterSelect.innerHTML = '<option value="">Select Datacenter</option>';
    datacenterSelect.disabled = true;
    setLoadingStatus(datacenterLoadingStatus, 'Waiting for server selection...', 'default');
    
    // Also reset dependent dropdowns
    resetClusterAndBelow();
    
    // Reset templates
    templateSelect.innerHTML = '<option value="">Select Template</option>';
    templateSelect.disabled = true;
    setLoadingStatus(templateLoadingStatus, 'Waiting for server selection...', 'default');
}

/**
 * Reset cluster dropdown and its dependents
 */
function resetClusterAndBelow() {
    // Reset cluster
    clusterSelect.innerHTML = '<option value="">Select Cluster</option>';
    clusterSelect.disabled = true;
    setLoadingStatus(clusterLoadingStatus, 'Waiting for datacenter selection...', 'default');
    
    // Also reset dependent dropdowns
    resetDatastoreClusters();
    
    // Reset networks
    networkSelect.innerHTML = '<option value="">Select Network</option>';
    networkSelect.disabled = true;
    setLoadingStatus(networkLoadingStatus, 'Waiting for datacenter selection...', 'default');
}

/**
 * Reset datastore cluster dropdown
 */
function resetDatastoreClusters() {
    datastoreClusterSelect.innerHTML = '<option value="">Select Datastore Cluster</option>';
    datastoreClusterSelect.disabled = true;
    setLoadingStatus(datastoreLoadingStatus, 'Waiting for cluster selection...', 'default');
}
