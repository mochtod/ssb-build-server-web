/**
 * VM Provisioning Tool JavaScript
 * 
 * Handles dynamic behavior for the VM provisioning web application.
 */

// Theme handling functionality
function setTheme(theme) {
    if (theme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
        localStorage.setItem('theme', 'light');
        if (document.getElementById('theme-toggle')) {
            document.getElementById('theme-toggle').checked = true;
        }
    } else {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme', 'dark');
        if (document.getElementById('theme-toggle')) {
            document.getElementById('theme-toggle').checked = false;
        }
    }
}

function initializeTheme() {
    // Get saved theme from localStorage
    const savedTheme = localStorage.getItem('theme');
    
    // Apply the saved theme or default to dark
    setTheme(savedTheme || 'dark');
    
    // Set up theme toggle if it exists
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.checked = savedTheme === 'light';
        themeToggle.addEventListener('change', function() {
            setTheme(this.checked ? 'light' : 'dark');
        });
    }
}

// Global variables for vSphere elements
let vsphereSection;
let vsphereLoading;
let vsphereErrorMessage;
let retryButton;

let vsphereServerSelect;
let datacenterSelect;
let clusterSelect;
let datastoreClusterSelect;
let networkSelect;
let templateSelect;

let serverLoadingStatus;
let datacenterLoadingStatus;
let clusterLoadingStatus;
let datastoreLoadingStatus;
let networkLoadingStatus;
let templateLoadingStatus;

// Debug configuration
const debugConfig = {
    enabled: true,  // Set to true to enable debug logs
    verboseVSphere: true
};

document.addEventListener('DOMContentLoaded', function() {
    console.log("DOM loaded - initializing application");
    
    // Add debug output to help diagnose issues
    const addDebugMessage = (message) => {
        console.log(`[DEBUG] ${message}`);
        
        // Create debug panel if it doesn't exist
        if (!document.getElementById('debug-panel')) {
            const debugPanel = document.createElement('div');
            debugPanel.id = 'debug-panel';
            debugPanel.className = 'debug-panel';
            debugPanel.innerHTML = `
                <div class="debug-header">
                    <div class="debug-title">Debug Information</div>
                    <button onclick="document.getElementById('debug-panel').remove()">Close</button>
                </div>
                <div class="debug-content" id="debug-content"></div>
            `;
            
            // Append to the end of main content instead of first card
            const mainElement = document.querySelector('main');
            if (mainElement) {
                mainElement.appendChild(debugPanel);
            } else {
                // Fallback to appending to first card if main not found
                const firstCard = document.querySelector('.card');
                if (firstCard) {
                    firstCard.appendChild(debugPanel);
                }
            }
        }
        
        // Only show debug messages when debug is enabled
        if (!debugConfig.enabled) return;
        
        // Add message to debug content
        const debugContent = document.getElementById('debug-content');
        const p = document.createElement('p');
        p.textContent = message;
        debugContent.appendChild(p);
        
        // Scroll to bottom
        debugContent.scrollTop = debugContent.scrollHeight;
    };

    // Initialize standard UI elements
    addDebugMessage("Initializing standard UI elements...");
    initializeServerNamePreview();
    initializeAdditionalDisks();
    initializeCopyButtons();
    initializePlanStatusCheck();
    initializeTheme();

    // Check if we're on the Create VM page (index.html) by looking for vSphere section
    vsphereSection = document.getElementById('vsphere-section');
    
    // Only initialize vSphere elements if we're on the Create VM page
    if (vsphereSection) {
        addDebugMessage("Found vSphere section, initializing elements...");
        
        // Ensure the section is visible
        vsphereSection.style.display = 'block';
        
        // Initialize loading indicators
        vsphereLoading = document.getElementById('vsphere-loading');
        vsphereErrorMessage = document.getElementById('vsphere-error-message');
        retryButton = document.getElementById('retry-vsphere-load');
        
        // Initialize select elements
        vsphereServerSelect = document.getElementById('vsphere_server');
        datacenterSelect = document.getElementById('datacenter');
        clusterSelect = document.getElementById('cluster');
        datastoreClusterSelect = document.getElementById('datastore_cluster');
        networkSelect = document.getElementById('network');
        templateSelect = document.getElementById('template');
        
        // Initialize loading status elements
        serverLoadingStatus = document.getElementById('server-loading-status');
        datacenterLoadingStatus = document.getElementById('datacenter-loading-status');
        clusterLoadingStatus = document.getElementById('cluster-loading-status');
        datastoreLoadingStatus = document.getElementById('datastore-loading-status');
        networkLoadingStatus = document.getElementById('network-loading-status');
        templateLoadingStatus = document.getElementById('template-loading-status');
        
        // Initialize the menus
        addDebugMessage("Initializing vSphere menus and loading data...");
        initializeVSphereMenus();
    } else if (debugConfig.verboseVSphere) {
        // Only log this message when verbose vSphere debugging is enabled
        addDebugMessage("vSphere section not found - not initializing vSphere elements on this page");
    }
});

/**
 * Create the vSphere section if it doesn't exist
 */
function createVSphereSection() {
    // Find the section where vSphere should be inserted
    const vmIdentificationSection = document.querySelector('.form-section');
    if (!vmIdentificationSection) {
        console.error("Cannot find VM Identification section to insert vSphere section after");
        return;
    }
    
    // Create the new vSphere section
    const vsphereSectionHtml = `
    <div class="form-section" id="vsphere-section">
        <h3>vSphere Configuration</h3>
        <div id="vsphere-loading" class="loading-indicator">
            <div class="spinner"></div>
            <p>Loading vSphere data... <span id="loading-detail">Initializing</span></p>
            <div class="progress-container">
                <div class="progress-bar" id="loading-progress-bar"></div>
            </div>
        </div>
        
        <div id="vsphere-error-message" class="alert alert-error" style="display: none;">
            Error loading vSphere data. <button id="retry-vsphere-load" class="btn-small">Retry</button>
            <button id="use-cached-data" class="btn-small">Use Cached Data</button>
        </div>
        
        <div class="form-row">
            <div class="form-group">
                <label for="vsphere_server">vSphere Server:</label>
                <select id="vsphere_server" name="vsphere_server" required>
                    <option value="">Select vSphere Server</option>
                    <option value="virtualcenter.chrobinson.com">virtualcenter.chrobinson.com PROD</option>
                </select>
                <div class="loading-status" id="server-loading-status">Connecting...</div>
            </div>
        </div>
        
        <div class="form-row">
            <div class="form-group">
                <label for="datacenter">Datacenter:</label>
                <select id="datacenter" name="datacenter" required>
                    <option value="">Select Datacenter</option>
                </select>
                <div class="loading-status" id="datacenter-loading-status">Waiting for server selection...</div>
            </div>
        </div>
        
        <div class="form-row">
            <div class="form-group">
                <label for="cluster">Cluster:</label>
                <select id="cluster" name="cluster" required>
                    <option value="">Select Cluster</option>
                </select>
                <div class="loading-status" id="cluster-loading-status">Waiting for datacenter selection...</div>
            </div>
        </div>
        
        <div class="form-row">
            <div class="form-group">
                <label for="datastore_cluster">Datastore Cluster:</label>
                <select id="datastore_cluster" name="datastore_cluster" required>
                    <option value="">Select Datastore Cluster</option>
                </select>
                <div class="loading-status" id="datastore-loading-status">Waiting for cluster selection...</div>
            </div>
        </div>
        
        <div class="form-row">
            <div class="form-group">
                <label for="network">Network:</label>
                <select id="network" name="network" required>
                    <option value="">Select Network</option>
                </select>
                <div class="loading-status" id="network-loading-status">Waiting for datacenter selection...</div>
            </div>
        </div>
        
        <div class="form-row">
            <div class="form-group">
                <label for="template">Template:</label>
                <select id="template" name="template" required>
                    <option value="">Select Template</option>
                </select>
                <div class="loading-status" id="template-loading-status">Waiting for datacenter selection...</div>
            </div>
        </div>
    </div>`;
    
    // Insert after VM Identification section
    vmIdentificationSection.insertAdjacentHTML('afterend', vsphereSectionHtml);
    
    // Initialize the newly created vSphere section
    vsphereSection = document.getElementById('vsphere-section');
    vsphereLoading = document.getElementById('vsphere-loading');
    vsphereErrorMessage = document.getElementById('vsphere-error-message');
    retryButton = document.getElementById('retry-vsphere-load');
    
    vsphereServerSelect = document.getElementById('vsphere_server');
    datacenterSelect = document.getElementById('datacenter');
    clusterSelect = document.getElementById('cluster');
    datastoreClusterSelect = document.getElementById('datastore_cluster');
    networkSelect = document.getElementById('network');
    templateSelect = document.getElementById('template');
    
    serverLoadingStatus = document.getElementById('server-loading-status');
    datacenterLoadingStatus = document.getElementById('datacenter-loading-status');
    clusterLoadingStatus = document.getElementById('cluster-loading-status');
    datastoreLoadingStatus = document.getElementById('datastore-loading-status');
    networkLoadingStatus = document.getElementById('network-loading-status');
    templateLoadingStatus = document.getElementById('template-loading-status');
    
    // Initialize vSphere menus
    console.log("Created and initialized vSphere section");
    initializeVSphereMenus();
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
 * Initialize vSphere menu dropdowns and handle loading states
 */
function initializeVSphereMenus() {
    console.log('Initializing vSphere menus');
    
    // Add event listeners for the "Use Cached Data" button
    const useCachedDataBtn = document.getElementById('use-cached-data');
    if (useCachedDataBtn) {
        useCachedDataBtn.addEventListener('click', function() {
            vsphereErrorMessage.style.display = 'none';
            loadCachedVSphereData();
        });
    }
    
    // Set initial loading states
    if (serverLoadingStatus) {
        setLoadingStatus(serverLoadingStatus, 'Connecting to vSphere...', 'loading');
    }
    
    // Update the loading detail and progress bar
    const loadingDetail = document.getElementById('loading-detail');
    const loadingProgressBar = document.getElementById('loading-progress-bar');
    
    // First try to use cached data if available
    if (window.initialVSphereData) {
        console.log('Found initial vSphere data in window, using this data');
        // Use the data passed from the server
        populateFromInitialData();
    } else {
        console.log('No initial vSphere data found, fetching from API');
        loadCachedVSphereData();
    }
    
    // Server selection change handler
    if (vsphereServerSelect) {
        vsphereServerSelect.addEventListener('change', function() {
            const selectedServer = this.value;
            
            if (!selectedServer) {
                resetDropdowns();
                return;
            }
            
            // Load datacenters for selected server
            loadDatacentersForServer(selectedServer);
        });
    }
    
    // Datacenter selection change handler
    if (datacenterSelect) {
        datacenterSelect.addEventListener('change', function() {
            const selectedDatacenter = this.value;
            const selectedServer = vsphereServerSelect ? vsphereServerSelect.value : '';
            
            if (!selectedDatacenter || !selectedServer) {
                resetClusterAndBelow();
                return;
            }
            
            // Load clusters for selected datacenter
            loadClustersForDatacenter(selectedServer, selectedDatacenter);
            
            // Also load networks as they depend on datacenter
            loadNetworksForDatacenter(selectedServer, selectedDatacenter);
            
            // Load templates filtered for this datacenter
            loadTemplatesForDatacenter(selectedServer, selectedDatacenter);
        });
    }
    
    // Cluster selection change handler
    if (clusterSelect) {
        clusterSelect.addEventListener('change', function() {
            const selectedCluster = this.value;
            const selectedDatacenter = datacenterSelect ? datacenterSelect.value : '';
            const selectedServer = vsphereServerSelect ? vsphereServerSelect.value : '';
            
            if (!selectedCluster || !selectedDatacenter || !selectedServer) {
                resetDatastoreClusters();
                return;
            }
            
            // Load datastore clusters for selected cluster
            loadDatastoreClustersForCluster(selectedServer, selectedDatacenter, selectedCluster);
        });
    }
    
    // Retry button handler
    if (retryButton) {
        retryButton.addEventListener('click', function() {
            if (vsphereErrorMessage) vsphereErrorMessage.style.display = 'none';
            if (vsphereLoading) vsphereLoading.style.display = 'flex';
            triggerEssentialSync();
        });
    }
}

/**
 * Populate dropdowns from initialVSphereData passed from server
 */
function populateFromInitialData() {
    console.log('Populating from initial data');
    
    if (!window.initialVSphereData) {
        console.error('No initial data available');
        return;
    }
    
    // Hide loading indicators
    if (vsphereLoading) {
        vsphereLoading.style.display = 'none';
    }
    
    // Populate server dropdown
    if (vsphereServerSelect && window.initialVSphereData.vsphere_servers) {
        populateSelect(vsphereServerSelect, window.initialVSphereData.vsphere_servers);
        vsphereServerSelect.disabled = false;
        if (serverLoadingStatus) {
            setLoadingStatus(serverLoadingStatus, 'Server list loaded', 'success');
        }
    }
    
    // Populate datacenter dropdown
    if (datacenterSelect && window.initialVSphereData.datacenters) {
        populateSelect(datacenterSelect, window.initialVSphereData.datacenters);
        datacenterSelect.disabled = false;
        if (datacenterLoadingStatus) {
            setLoadingStatus(datacenterLoadingStatus, 'Datacenters loaded', 'success');
        }
    }
    
    // Populate cluster dropdown
    if (clusterSelect && window.initialVSphereData.clusters) {
        populateSelect(clusterSelect, window.initialVSphereData.clusters);
        clusterSelect.disabled = false;
        if (clusterLoadingStatus) {
            setLoadingStatus(clusterLoadingStatus, 'Clusters loaded', 'success');
        }
    }
    
    // Populate datastore cluster dropdown
    if (datastoreClusterSelect && window.initialVSphereData.datastore_clusters) {
        populateSelect(datastoreClusterSelect, window.initialVSphereData.datastore_clusters);
        datastoreClusterSelect.disabled = false;
        if (datastoreLoadingStatus) {
            setLoadingStatus(datastoreLoadingStatus, 'Datastore clusters loaded', 'success');
        }
    }
    
    // Populate network dropdown
    if (networkSelect && window.initialVSphereData.networks) {
        populateSelect(networkSelect, window.initialVSphereData.networks);
        networkSelect.disabled = false;
        if (networkLoadingStatus) {
            setLoadingStatus(networkLoadingStatus, 'Networks loaded', 'success');
        }
    }
    
    // Populate template dropdown
    if (templateSelect && window.initialVSphereData.templates) {
        populateSelect(templateSelect, window.initialVSphereData.templates);
        templateSelect.disabled = false;
        if (templateLoadingStatus) {
            setLoadingStatus(templateLoadingStatus, 'Templates loaded', 'success');
        }
        
        // Auto-select RHEL9 template if available
        autoSelectRhel9Template();
    }
    
    console.log('Completed populating dropdowns from initial data');
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

    // Fetch from hierarchical endpoint instead of servers-specific endpoint
    // This ensures we're getting data directly from Redis cache
    fetch('/api/vsphere/hierarchical')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.data) {
                // Hide the main loading indicator
                vsphereLoading.style.display = 'none';
                
                // Populate the server dropdown if servers data exists
                if (data.data.vsphere_servers) {
                    populateSelect(vsphereServerSelect, data.data.vsphere_servers);
                    setLoadingStatus(serverLoadingStatus, 'Server list loaded', 'success');
                    
                    // Enable server dropdown
                    vsphereServerSelect.disabled = false;
                }
                else {
                    // Fallback to default servers if none returned
                    const defaultServers = [
                        { id: "virtualcenter.chrobinson.com", name: "virtualcenter.chrobinson.com PROD" }
                    ];
                    populateSelect(vsphereServerSelect, defaultServers);
                    vsphereServerSelect.disabled = false;
                    setLoadingStatus(serverLoadingStatus, 'Using default server list', 'warning');
                }
                
                // Check cache status to see if we need a background sync
                return fetch('/api/vsphere-cache/status');
            } else {
                throw new Error(data.error || 'No vSphere data found in cache');
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
                const datacentersExist = cacheStatus && cacheStatus.datacenters && cacheStatus.datacenters.exists;
                const clustersExist = cacheStatus && cacheStatus.clusters && cacheStatus.clusters.exists;
                const templatesExist = cacheStatus && cacheStatus.templates && cacheStatus.templates.exists;
                
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
            
            // Even in case of error, still populate with default server
            const defaultServers = [
                { id: "virtualcenter.chrobinson.com", name: "virtualcenter.chrobinson.com PROD" }
            ];
            populateSelect(vsphereServerSelect, defaultServers);
            vsphereServerSelect.disabled = false;
            setLoadingStatus(serverLoadingStatus, 'Using default server list', 'warning');
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
    
    // Log for debugging
    if (debugConfig.enabled) {
        console.log(`Loading datacenters for server: ${server}`);
    }
    
    // Fetch datacenters
    const apiUrl = `/api/vsphere/hierarchical?vsphere_server=${encodeURIComponent(server)}`;
    
    if (debugConfig.enabled) {
        console.log(`Fetch URL: ${apiUrl}`);
    }
    
    fetch(apiUrl)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // Debug: Log response data
            if (debugConfig.enabled) {
                console.log('API Response:', data);
                console.log(`Received datacenters: ${data.data && data.data.datacenters ? data.data.datacenters.length : 0}`);
                
                if (data.data && data.data.datacenters) {
                    console.log(`First few datacenters:`, data.data.datacenters.slice(0, 3));
                }
            }
            
            if (data.success && data.data && data.data.datacenters && data.data.datacenters.length > 0) {
                // Populate dropdown
                populateSelect(datacenterSelect, data.data.datacenters);
                datacenterSelect.disabled = false;
                setLoadingStatus(datacenterLoadingStatus, 'Datacenters loaded', 'success');
                
                // Also load templates as they depend on server
                loadTemplatesForServer(server);
            } else {
                // No datacenters found or empty array
                if (debugConfig.enabled) {
                    console.warn(`No datacenters found for server ${server}`);
                    if (data.data) {
                        console.warn('Data returned:', data.data);
                    }
                }
                
                datacenterSelect.innerHTML = '<option value="">No datacenters found</option>';
                datacenterSelect.disabled = true;
                setLoadingStatus(datacenterLoadingStatus, 'No datacenters found', 'warning');
                
                // Show error message with retry button
                vsphereErrorMessage.style.display = 'block';
                vsphereErrorMessage.innerHTML = `No datacenters found for server ${server}. Please check Redis cache. <button id="retry-vsphere-load" class="btn-small">Retry</button>`;
                
                // Re-attach retry event listener
                document.getElementById('retry-vsphere-load').addEventListener('click', function() {
                    vsphereErrorMessage.style.display = 'none';
                    triggerEssentialSync();
                });
            }
        })
        .catch(error => {
            console.error('Error loading datacenters:', error);
            setLoadingStatus(datacenterLoadingStatus, 'Failed to load datacenters', 'error');
            
            // Debug: Log the error details
            if (debugConfig.enabled) {
                console.error('Datacenter loading error details:', error);
            }
            
            // Show error message with retry button
            vsphereErrorMessage.style.display = 'block';
            vsphereErrorMessage.innerHTML = `Error loading datacenters: ${error.message}. <button id="retry-vsphere-load" class="btn-small">Retry</button>`;
            
            // Re-attach retry event listener
            document.getElementById('retry-vsphere-load').addEventListener('click', function() {
                vsphereErrorMessage.style.display = 'none';
                triggerEssentialSync();
            });
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
    
    // Debug: Log request parameters
    if (debugConfig.enabled) {
        console.log(`Loading clusters for datacenter ${datacenter} on server ${server}`);
    }
    
    // Fetch clusters
    const apiUrl = `/api/vsphere/hierarchical?vsphere_server=${encodeURIComponent(server)}&datacenter_id=${encodeURIComponent(datacenter)}`;
    
    if (debugConfig.enabled) {
        console.log(`Fetch URL: ${apiUrl}`);
    }
    
    fetch(apiUrl)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // Debug: Log response data
            if (debugConfig.enabled) {
                console.log('API Response:', data);
                console.log(`Received clusters: ${data.data.clusters ? data.data.clusters.length : 0}`);
            }
            
            if (data.success && data.data && data.data.clusters && data.data.clusters.length > 0) {
                // Populate dropdown
                populateSelect(clusterSelect, data.data.clusters);
                clusterSelect.disabled = false;
                setLoadingStatus(clusterLoadingStatus, 'Clusters loaded', 'success');
            } else {
                // No clusters found or empty array
                if (debugConfig.enabled) {
                    console.warn(`No clusters found for datacenter ${datacenter}`);
                    if (data.data && Array.isArray(data.data.clusters)) {
                        console.warn('Empty clusters array returned');
                    } else {
                        console.warn('Invalid clusters data structure:', data.data ? data.data.clusters : 'undefined');
                    }
                }
                
                clusterSelect.innerHTML = '<option value="">No clusters found</option>';
                clusterSelect.disabled = true;
                setLoadingStatus(clusterLoadingStatus, 'No clusters found', 'warning');
            }
        })
        .catch(error => {
            console.error('Error loading clusters:', error);
            setLoadingStatus(clusterLoadingStatus, 'Failed to load clusters', 'error');
            
            // Debug: Log the error details
            if (debugConfig.enabled) {
                console.error('Cluster loading error details:', error);
            }
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
 * Load templates for a selected datacenter with improved error handling
 */
function loadTemplatesForDatacenter(server, datacenter) {
    // Set loading state
    templateSelect.disabled = true;
    setLoadingStatus(templateLoadingStatus, 'Loading templates for datacenter...', 'loading');
    
    // Add debug logging
    console.log(`Loading templates for datacenter ${datacenter} on server ${server}`);
    
    // Fetch templates filtered for this datacenter
    fetch(`/api/vsphere/hierarchical?vsphere_server=${encodeURIComponent(server)}&datacenter_id=${encodeURIComponent(datacenter)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status} - ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            // Check if there's a warning in the data (this means fallbacks were used)
            if (data.warning) {
                // Show the warning in the UI instead of silently using fallbacks
                vsphereErrorMessage.style.display = 'block';
                vsphereErrorMessage.innerHTML = `Warning: ${data.warning}<br>
                    <button id="retry-vsphere-load" class="btn-small">Retry</button>`;
                
                // Re-attach retry event listener
                document.getElementById('retry-vsphere-load').addEventListener('click', function() {
                    vsphereErrorMessage.style.display = 'none';
                    triggerEssentialSync();
                });
            }
            
            if (data.success && data.data) {
                // Log template data for debugging
                console.log(`Received ${data.data.templates ? data.data.templates.length : 0} templates`);
                
                if (data.data.templates && data.data.templates.length > 0) {
                    // Check if these are fallback templates by inspecting IDs
                    const hasFallbackTemplates = data.data.templates.some(t => 
                        t.id.includes('fallback') || t.name.includes('fallback'));
                    
                    if (hasFallbackTemplates) {
                        // Alert the user that these are fallback templates that won't work for real deployments
                        setLoadingStatus(templateLoadingStatus, 
                            'WARNING: Using placeholder templates (not deployable)', 'error');
                        
                        // Show an error message
                        vsphereErrorMessage.style.display = 'block';
                        vsphereErrorMessage.innerHTML = `Error: The templates returned are placeholder values that cannot be used for real deployments. 
                            This usually indicates a connection issue with vSphere or Redis cache.<br>
                            <button id="retry-vsphere-load" class="btn-small">Retry</button>`;
                        
                        // Re-attach retry event listener
                        document.getElementById('retry-vsphere-load').addEventListener('click', function() {
                            vsphereErrorMessage.style.display = 'none';
                            triggerEssentialSync();
                        });
                    } else {
                        // Real templates found, populate the dropdown
                        populateSelect(templateSelect, data.data.templates);
                        templateSelect.disabled = false;
                        setLoadingStatus(templateLoadingStatus, 'Templates loaded for datacenter', 'success');
                        
                        // Auto-select RHEL9 template if available
                        autoSelectRhel9Template();
                    }
                } else {
                    // No templates found - show error
                    setLoadingStatus(templateLoadingStatus, 'Error: No templates found for this datacenter', 'error');
                    templateSelect.disabled = true;
                    
                    // Show error message with more info
                    vsphereErrorMessage.style.display = 'block';
                    vsphereErrorMessage.innerHTML = `Error: No templates found for datacenter "${datacenter}". 
                        This could indicate a configuration issue or that templates haven't been synchronized.<br>
                        <button id="retry-vsphere-load" class="btn-small">Retry with full sync</button>`;
                    
                    // Re-attach retry event listener
                    document.getElementById('retry-vsphere-load').addEventListener('click', function() {
                        vsphereErrorMessage.style.display = 'none';
                        triggerEssentialSync();
                    });
                }
            } else {
                throw new Error(data.error || 'No templates found for this datacenter');
            }
        })
        .catch(error => {
            console.error('Error loading templates for datacenter:', error);
            setLoadingStatus(templateLoadingStatus, `Error: ${error.message}`, 'error');
            
            // Show detailed error message
            vsphereErrorMessage.style.display = 'block';
            vsphereErrorMessage.innerHTML = `Failed to load templates: ${error.message}<br>
                <p>This is likely due to one of the following issues:</p>
                <ul>
                    <li>vSphere server is unreachable</li>
                    <li>Redis cache is not running or reachable</li>
                    <li>Template cache has not been populated</li>
                </ul>
                <button id="retry-vsphere-load" class="btn-small">Retry with full sync</button>`;
            
            // Re-attach retry event listener
            document.getElementById('retry-vsphere-load').addEventListener('click', function() {
                vsphereErrorMessage.style.display = 'none';
                triggerEssentialSync();
            });
        });
}

/**
 * Load all templates as a fallback when datacenter-specific templates aren't available
 */
function loadAllTemplates(server) {
    setLoadingStatus(templateLoadingStatus, 'Loading all templates...', 'loading');
    
    // Fetch all templates without datacenter filter
    fetch(`/api/vsphere/hierarchical?vsphere_server=${encodeURIComponent(server)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.data && data.data.templates && data.data.templates.length > 0) {
                console.log(`Loaded ${data.data.templates.length} templates as fallback`);
                // Populate dropdown
                populateSelect(templateSelect, data.data.templates);
                templateSelect.disabled = false;
                setLoadingStatus(templateLoadingStatus, 'All templates loaded', 'success');
                
                // Auto-select RHEL9 template if available
                autoSelectRhel9Template();
            } else {
                // If still no templates, create static fallback templates
                console.warn("No templates found at all, using static fallbacks");
                const fallbackTemplates = [
                    { id: 'vm-fallback-rhel9', name: 'rhel9-template (fallback)' },
                    { id: 'vm-fallback-win', name: 'windows-template (fallback)' }
                ];
                populateSelect(templateSelect, fallbackTemplates);
                templateSelect.disabled = false;
                setLoadingStatus(templateLoadingStatus, 'Using fallback templates', 'warning');
                
                // Auto-select RHEL9 template
                for (let i = 0; i < templateSelect.options.length; i++) {
                    if (templateSelect.options[i].text.toLowerCase().includes('rhel9')) {
                        templateSelect.selectedIndex = i;
                        break;
                    }
                }
            }
        })
        .catch(error => {
            console.error('Error loading all templates:', error);
            setLoadingStatus(templateLoadingStatus, 'Failed to load any templates', 'error');
            
            // Add fallback templates directly to the dropdown in case of complete failure
            const fallbackTemplates = [
                { id: 'vm-fallback-rhel9', name: 'rhel9-template (fallback)' },
                { id: 'vm-fallback-win', name: 'windows-template (fallback)' }
            ];
            populateSelect(templateSelect, fallbackTemplates);
            templateSelect.disabled = false;
        });
}

/**
 * Auto-select RHEL9 template if available (improved with fuzzy matching)
 */
function autoSelectRhel9Template() {
    // Check if we have any templates first
    if (templateSelect.options.length <= 1) {
        console.log("No templates to auto-select");
        return;
    }
    
    // First try to find exact match containing "rhel9"
    for (let i = 0; i < templateSelect.options.length; i++) {
        const optionText = templateSelect.options[i].text.toLowerCase();
        if (optionText.includes('rhel9')) {
            templateSelect.selectedIndex = i;
            console.log(`Auto-selected RHEL9 template: ${templateSelect.options[i].text}`);
            return;
        }
    }
    
    // If no exact match, try variations like "rhel" and "9"
    for (let i = 0; i < templateSelect.options.length; i++) {
        const optionText = templateSelect.options[i].text.toLowerCase();
        if (optionText.includes('rhel') && optionText.includes('9')) {
            templateSelect.selectedIndex = i;
            console.log(`Auto-selected RHEL template: ${templateSelect.options[i].text}`);
            return;
        }
    }
    
    // If still no match, try just "rhel"
    for (let i = 0; i < templateSelect.options.length; i++) {
        const optionText = templateSelect.options[i].text.toLowerCase();
        if (optionText.includes('rhel')) {
            templateSelect.selectedIndex = i;
            console.log(`Auto-selected generic RHEL template: ${templateSelect.options[i].text}`);
            return;
        }
    }
    
    // If all else fails, select the first option after the placeholder
    if (templateSelect.options.length > 1) {
        templateSelect.selectedIndex = 1;
        console.log(`Selected first available template: ${templateSelect.options[1].text}`);
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
    if (!selectElement) {
        console.error("Cannot populate select: element is null or undefined");
        return;
    }
    
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
        console.warn(`No options provided for select: ${selectElement.id || 'unnamed'}`);
        return;
    }
    
    console.log(`Populating ${selectElement.id} with ${options.length} options`);
    
    // Add new options
    options.forEach(option => {
        if (!option) {
            console.warn("Null or undefined option encountered in populateSelect");
            return; // Skip this iteration
        }
        
        const optionValue = option[valueKey];
        const optionText = option[textKey];
        
        if (optionValue === undefined || optionValue === null) {
            console.warn(`Option missing ${valueKey} value:`, option);
            return; // Skip this iteration
        }
        
        const optionElement = document.createElement('option');
        optionElement.value = optionValue;
        optionElement.text = optionText || 'Unnamed';
        selectElement.appendChild(optionElement);
    });
    
    // Try to restore previous selection
    if (currentValue) {
        // Check if the current value still exists in the options
        const valueExists = Array.from(selectElement.options).some(opt => opt.value === currentValue);
        if (valueExists) {
            selectElement.value = currentValue;
            console.log(`Restored previous selection: ${currentValue} in ${selectElement.id}`);
        } else {
            console.log(`Previous selection ${currentValue} no longer exists in ${selectElement.id}`);
        }
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

/**
 * Initialize VSphere resource loading functionality with datacenter-to-cluster hierarchical approach
 * - First loads available datacenters
 * - When a datacenter is selected, fetches clusters specific to that datacenter
 *   and also loads templates since they are datacenter-specific, not cluster-specific
 * - When a cluster is selected, fetches resources specific to that cluster
 * - Displays resources in a hierarchical way
 */
function initializeResourceLoading() {
    // Check if we're on a page with the datacenter selection dropdown
    const datacenterSelect = document.getElementById('datacenter');
    const clusterSelect = document.getElementById('cluster');
    const clusterContainer = document.getElementById('cluster_container');
    const resourceStatusElement = document.getElementById('resource_status');

    // Only proceed if we have the datacenter select
    if (datacenterSelect) {
        // Add loading indicator to the page
        const loadingIndicator = document.createElement('div');
        loadingIndicator.id = 'resources-loading-indicator';
        loadingIndicator.className = 'notification info';
        loadingIndicator.innerHTML = '<i class="fa fa-sync fa-spin"></i> Loading datacenters...';

        // Insert loading indicator
        const resourceStatus = document.querySelector('.resource-status');
        if (resourceStatus) {
            resourceStatus.appendChild(loadingIndicator);
        }

        // Fetch datacenters immediately
        fetchDatacenters();

        // Set up event listener for datacenter selection
        datacenterSelect.addEventListener('change', function() {
            const datacenterName = this.value;

            // Clear and hide cluster selection and all resource sections
            if (clusterSelect) {
                // Keep only the first option (placeholder)
                while (clusterSelect.options.length > 1) {
                    clusterSelect.remove(1);
                }
                clusterSelect.value = '';
            }

            // Hide all dependent containers
            document.getElementById('resource_pool_container').style.display = 'none';
            document.getElementById('datastores_container').style.display = 'none';
            document.getElementById('networks_container').style.display = 'none';
            
            // Important: We don't hide templates here since they depend on datacenter, not cluster
            // This allows templates to be selected as soon as a datacenter is chosen

            if (datacenterName) {
                // Show cluster container
                if (clusterContainer) {
                    clusterContainer.style.display = 'flex';
                }

                // Update status
                if (resourceStatusElement) {
                    resourceStatusElement.textContent = `Loading clusters for datacenter "${datacenterName}"...`;
                }

                // Show loading indicator
                if (loadingIndicator) {
                    loadingIndicator.innerHTML = '<i class="fa fa-sync fa-spin"></i> Loading clusters...';
                    loadingIndicator.style.display = 'block';
                }

                // Fetch clusters for selected datacenter
                fetchClustersForDatacenter(datacenterName);
                
                // Load templates based on datacenter selection
                loadTemplatesForDatacenter(datacenterName);
                
                // Show templates container since templates are available at datacenter level
                document.getElementById('templates_container').style.display = 'flex';
            } else {
                // Hide cluster container if no datacenter selected
                if (clusterContainer) {
                    clusterContainer.style.display = 'none';
                }

                // Update status
                if (resourceStatusElement) {
                    resourceStatusElement.textContent = 'Select a datacenter to view available clusters.';
                }

                // Hide loading indicator
                if (loadingIndicator) {
                    loadingIndicator.style.display = 'none';
                }
                
                // Hide templates container when no datacenter is selected
                document.getElementById('templates_container').style.display = 'none';
            }
        });

        // Set up event listener for cluster selection
        if (clusterSelect) {
            clusterSelect.addEventListener('change', function() {
                const clusterId = this.value;
                if (clusterId) {
                    loadClusterResources(clusterId);
                } else {
                    // Hide all resource sections if no cluster is selected
                    document.getElementById('resource_pool_container').style.display = 'none';
                    document.getElementById('datastores_container').style.display = 'none';
                    document.getElementById('networks_container').style.display = 'none';
                    
                    // Important: We don't hide templates here as they are tied to datacenter, not cluster
                    // This allows templates to remain visible even if no cluster is selected

                    if (resourceStatusElement) {
                        resourceStatusElement.textContent = 'Select a cluster to view available resources.';
                    }
                }
            });
        }
    }

    /**
     * Fetch all available datacenters from the API
     */
    function fetchDatacenters() {
        fetch('/api/vsphere/datacenters')
            .then(response => response.json())
            .then(data => {
                if (data.datacenters && data.datacenters.length > 0) {
                    // Update the datacenter dropdown
                    updateDatacenterDropdown(datacenterSelect, data.datacenters);

                    // Hide loading indicator
                    const loadingIndicator = document.getElementById('resources-loading-indicator');
                    if (loadingIndicator) {
                        loadingIndicator.style.display = 'none';
                    }

                    // Update status display
                    if (resourceStatusElement) {
                        resourceStatusElement.textContent = `${data.datacenters.length} datacenters loaded. Select a datacenter to continue.`;
                    }

                    console.log(`Loaded ${data.datacenters.length} datacenters`);
                } else {
                    // Show error message if no datacenters found
                    if (resourceStatusElement) {
                        resourceStatusElement.textContent = 'No datacenters found. Please check vSphere connection.';
                    }
                }
            })
            .catch(error => {
                console.error('Error fetching datacenters:', error);

                // Update status to show error
                if (resourceStatusElement) {
                    resourceStatusElement.textContent = 'Error loading datacenters. Please refresh the page or contact an administrator.';
                }

                // Hide loading indicator
                const loadingIndicator = document.getElementById('resources-loading-indicator');
                if (loadingIndicator) {
                    loadingIndicator.style.display = 'none';
                }
            });
    }

    /**
     * Fetch clusters for a specific datacenter
     */
    function fetchClustersForDatacenter(datacenterName) {
        fetch(`/api/vsphere/datacenters/${encodeURIComponent(datacenterName)}/clusters`)
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
                        resourceStatusElement.textContent = `${data.clusters.length} clusters loaded for datacenter "${datacenterName}". Select a cluster to continue.`;
                    }

                    console.log(`Loaded ${data.clusters.length} clusters for datacenter ${datacenterName}`);
                } else {
                    // Show message if no clusters found for this datacenter
                    if (resourceStatusElement) {
                        resourceStatusElement.textContent = `No clusters found in datacenter "${datacenterName}". Please select a different datacenter.`;
                    }

                    // Hide loading indicator
                    const loadingIndicator = document.getElementById('resources-loading-indicator');
                    if (loadingIndicator) {
                        loadingIndicator.style.display = 'none';
                    }
                }
            })
            .catch(error => {
                console.error(`Error fetching clusters for datacenter ${datacenterName}:`, error);

                // Update status to show error
                if (resourceStatusElement) {
                    resourceStatusElement.textContent = `Error loading clusters for datacenter "${datacenterName}". Please refresh or select a different datacenter.`;
                }

                // Hide loading indicator
                const loadingIndicator = document.getElementById('resources-loading-indicator');
                if (loadingIndicator) {
                    loadingIndicator.style.display = 'none';
                }
            });
    }

    /**
     * Load templates for a specific datacenter
     */
    function loadTemplatesForDatacenter(datacenterName) {
        // Show loading indicator for templates
        const loadingIndicator = document.getElementById('resources-loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.innerHTML = '<i class="fa fa-sync fa-spin"></i> Loading templates...';
            loadingIndicator.style.display = 'block';
        }

        // Fetch templates for the datacenter directly
        fetch(`/api/vsphere/datacenters/${encodeURIComponent(datacenterName)}/templates`)
            .then(response => response.json())
            .then(data => {
                // Check if we have templates in the response
                if (data.templates && data.templates.length > 0) {
                    // Get the template dropdown
                    const templateSelect = document.getElementById('template');
                    
                    // Update the template dropdown with the templates
                    updateResourceDropdown(templateSelect, data.templates);
                    
                    // Show the templates container
                    document.getElementById('templates_container').style.display = 'flex';
                    
                    // Update the resource status
                    if (resourceStatusElement) {
                        resourceStatusElement.textContent += ` Found ${data.templates.length} templates for datacenter "${datacenterName}".`;
                    }

                    console.log(`Loaded ${data.templates.length} templates for datacenter ${datacenterName}`);
                } else {
                    console.warn(`No templates found for datacenter ${datacenterName}`);
                    
                    // Try to get templates from all available templates
                    fetch('/api/vsphere/templates')
                        .then(response => response.json())
                        .then(fallbackData => {
                            const templateSelect = document.getElementById('template');
                            
                            if (fallbackData.success && fallbackData.templates && fallbackData.templates.length > 0) {
                                // Update templates with all available templates as fallback
                                updateResourceDropdown(templateSelect, fallbackData.templates);
                                document.getElementById('templates_container').style.display = 'flex';
                                
                                console.log(`Using ${fallbackData.templates.length} templates from fallback`);
                                
                                if (resourceStatusElement) {
                                    resourceStatusElement.textContent += ` No specific templates found for this datacenter. Showing all available templates.`;
                                }
                            } else {
                                // No templates available at all
                                document.getElementById('templates_container').style.display = 'none';
                                
                                if (resourceStatusElement) {
                                    resourceStatusElement.textContent += ` No templates found. This may prevent VM creation.`;
                                }
                            }
                        })
                        .catch(fallbackError => {
                            console.error('Error fetching fallback templates:', fallbackError);
                            document.getElementById('templates_container').style.display = 'none';
                        });
                }
                
                // Hide loading indicator
                if (loadingIndicator) {
                    loadingIndicator.style.display = 'none';
                }
            })
            .catch(error => {
                console.error(`Error fetching templates for datacenter ${datacenterName}:`, error);
                
                // Show error in status
                if (resourceStatusElement) {
                    resourceStatusElement.textContent += ` Error loading templates: ${error.message}`;
                }
                
                // Hide loading indicator
                if (loadingIndicator) {
                    loadingIndicator.style.display = 'none';
                }
                
                // Hide templates container on error
                document.getElementById('templates_container').style.display = 'none';
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

        // Fetch resources for the selected cluster using the hierarchical loader endpoint
        fetch(`/api/vsphere/hierarchical/clusters/${clusterId}/resources`)
            .then(response => {
                if (!response.ok) {
                    // Try to parse error from response body, otherwise use status text
                    return response.json().catch(() => null).then(errorData => {
                        throw new Error(errorData?.error || response.statusText || `HTTP error! status: ${response.status}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                // Check if the backend returned an error within the JSON
                if (data.error) {
                    throw new Error(data.error);
                }

                let resourcesFound = false; // Flag to track if any resources were actually loaded

                // Update resource pools
                if (data.resource_pools && data.resource_pools.length > 0) {
                    const resourcePoolSelect = document.getElementById('resource_pool');
                    updateResourceDropdown(resourcePoolSelect, data.resource_pools);
                    document.getElementById('resource_pool_container').style.display = 'flex';
                    resourcesFound = true;
                    if (data.resource_pools.length === 1) {
                        resourcePoolSelect.value = data.resource_pools[0].id;
                    }
                } else {
                    document.getElementById('resource_pool_container').style.display = 'none'; // Ensure it's hidden if empty
                }

                // Update datastores
                if (data.datastores && data.datastores.length > 0) {
                    const datastoreSelect = document.getElementById('datastore');
                    updateResourceDropdown(datastoreSelect, data.datastores, 'free_gb');
                    document.getElementById('datastores_container').style.display = 'flex';
                    resourcesFound = true;
                } else {
                    document.getElementById('datastores_container').style.display = 'none';
                }

                // Update networks
                if (data.networks && data.networks.length > 0) {
                    const networkSelect = document.getElementById('network');
                    updateResourceDropdown(networkSelect, data.networks);
                    document.getElementById('networks_container').style.display = 'flex';
                    resourcesFound = true;
                } else {
                    document.getElementById('networks_container').style.display = 'none';
                }

                // Note: We don't update templates here as they're already loaded at the datacenter level
                // Templates container remains visible regardless of cluster selection

                // Hide loading indicator
                if (loadingIndicator) {
                    loadingIndicator.style.display = 'none';
                }

                // Update status display based on whether resources were found
                if (resourceStatusElement) {
                    const clusterName = data.cluster_name || 'selected cluster';
                    if (resourcesFound) {
                        resourceStatusElement.textContent = `Resources loaded for ${clusterName}. Found ${data.datastores?.length || 0} datastores, ${data.networks?.length || 0} networks.`;
                        
                        // Add note about templates already being loaded
                        if (document.getElementById('templates_container').style.display === 'flex') {
                            resourceStatusElement.textContent += ' Templates are available based on datacenter selection.';
                        }
                    } else {
                        resourceStatusElement.textContent = `No resources (datastores, networks) found for cluster ${clusterName}. Check vSphere configuration or select another cluster.`;
                    }
                }

                console.log(`Loaded resources for cluster ${clusterId}. Found resources: ${resourcesFound}`);
            })
            .catch(error => {
                console.error(`Error fetching or processing resources for cluster ${clusterId}:`, error);

                // Update status to show a more specific error
                if (resourceStatusElement) {
                    resourceStatusElement.textContent = `Error loading resources: ${error.message}. Please try another cluster or refresh.`;
                }

                // Hide loading indicator
                if (loadingIndicator) {
                    loadingIndicator.style.display = 'none';
                }

                // Ensure all resource sections are hidden on error
                document.getElementById('resource_pool_container').style.display = 'none';
                document.getElementById('datastores_container').style.display = 'none';
                document.getElementById('networks_container').style.display = 'none';
                
                // Important: We leave templates visible if they were already loaded
            });
    }

    /**
     * Update the datacenter dropdown with the fetched datacenters
     */
    function updateDatacenterDropdown(selectElement, datacenterList) {
        if (!selectElement || !datacenterList) return;

        // Clear existing options (except the first empty option)
        while (selectElement.options.length > 1) {
            selectElement.remove(1);
        }

        // Sort datacenters by name
        datacenterList.sort((a, b) => a.name.localeCompare(b.name));

        // Add all datacenters to the dropdown
        datacenterList.forEach(datacenter => {
            const option = document.createElement('option');
            option.value = datacenter.name;
            option.textContent = datacenter.name;
            selectElement.add(option);
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
