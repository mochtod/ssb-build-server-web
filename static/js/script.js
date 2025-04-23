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
 * Load templates for a selected datacenter
 */
function loadTemplatesForDatacenter(server, datacenter) {
    // Set loading state
    templateSelect.disabled = true;
    setLoadingStatus(templateLoadingStatus, 'Loading templates for datacenter...', 'loading');
    
    // Fetch templates filtered for this datacenter
    fetch(`/api/vsphere/hierarchical?vsphere_server=${encodeURIComponent(server)}&datacenter_id=${encodeURIComponent(datacenter)}`)
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
                setLoadingStatus(templateLoadingStatus, 'Templates loaded for datacenter', 'success');
                
                // Auto-select RHEL9 template if available
                autoSelectRhel9Template();
            } else {
                throw new Error(data.error || 'No templates found for this datacenter');
            }
        })
        .catch(error => {
            console.error('Error loading templates for datacenter:', error);
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
