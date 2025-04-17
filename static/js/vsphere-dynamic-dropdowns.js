/**
 * Dynamic vSphere Resource Loading
 * 
 * This JavaScript file handles the dynamic loading of vSphere resources
 * based on hierarchical dependencies:
 * - Datacenter -> Clusters/Resource Pools
 * - Cluster -> Datastores and Networks
 */

document.addEventListener('DOMContentLoaded', function() {
    initializeDynamicVSphereDropdowns();
});

/**
 * Initialize the dynamic loading for vSphere resources
 */
function initializeDynamicVSphereDropdowns() {
    const datacenterSelect = document.getElementById('vsphere_datacenter');
    const resourcePoolSelect = document.getElementById('vsphere_resource_pool');
    const datastoreSelect = document.getElementById('vsphere_datastore');
    const templateSelect = document.getElementById('vsphere_template');
    const networkSelect = document.getElementById('vsphere_network');
    const netboxIpRangeSelect = document.getElementById('netbox_ip_range');
    
    // Only initialize if we have the necessary elements
    if (!datacenterSelect || !resourcePoolSelect || !datastoreSelect) return;
    
    // Add loading indicator to selects
    addLoadingIndicator(resourcePoolSelect);
    addLoadingIndicator(datastoreSelect);
    addLoadingIndicator(templateSelect);
    if (networkSelect) addLoadingIndicator(networkSelect);

    // Try to restore cache from local storage if available
    let datacenterResourcesCache = {};
    try {
        const savedCache = localStorage.getItem('vsphereResourcesCache');
        if (savedCache) {
            datacenterResourcesCache = JSON.parse(savedCache);
            console.log('Restored vSphere resources cache from local storage');
            
            // Check if cache is still fresh (less than 1 hour old)
            const cacheTimestamp = localStorage.getItem('vsphereCacheTimestamp');
            const now = new Date().getTime();
            if (cacheTimestamp && (now - parseInt(cacheTimestamp) < 3600000)) {
                console.log('Using cached vSphere data (less than 1 hour old)');
            } else {
                // Cache is older than 1 hour, we'll still use it but refresh in background
                console.log('Cache is older than 1 hour, refreshing in background');
                setTimeout(() => preloadAllDatacentersData(datacenterResourcesCache), 1000);
            }
        } else {
            console.log('No vSphere cache found in local storage');
            // Preload data for all datacenters in the background
            setTimeout(() => preloadAllDatacentersData(datacenterResourcesCache), 500);
        }
    } catch (e) {
        console.error('Error restoring cache from local storage:', e);
        // If restoration fails, start fresh
        datacenterResourcesCache = {};
        setTimeout(() => preloadAllDatacentersData(datacenterResourcesCache), 500);
    }
    
    // Datacenter change triggers resource load
    datacenterSelect.addEventListener('change', function() {
        const selectedDC = this.value;
        
        console.log(`Datacenter selected: ${selectedDC}`);
        
        if (selectedDC) {
            // Reset dependent dropdowns
            resetDropdown(resourcePoolSelect, "Select Resource Pool...");
            resetDropdown(datastoreSelect, "Select Datastore...");
            resetDropdown(templateSelect, "Select Template...");
            if (networkSelect) resetDropdown(networkSelect, "Select Network...");
            
            // Show loading state for all dropdowns
            setDropdownLoading(resourcePoolSelect, true);
            setDropdownLoading(datastoreSelect, true);
            setDropdownLoading(templateSelect, true);
            if (networkSelect) setDropdownLoading(networkSelect, true);
            
            // Check if we already cached resources for this datacenter
            if (datacenterResourcesCache[selectedDC]) {
                console.log(`Using cached resources for datacenter: ${selectedDC}`);
                const resources = datacenterResourcesCache[selectedDC];
                
                // Populate resource pools dropdown
                populateDropdown(resourcePoolSelect, resources.pools, "Select Resource Pool...");
                setDropdownLoading(resourcePoolSelect, false);
                
                // Keep the other dropdowns disabled until resource pool selection
                setDropdownLoading(datastoreSelect, false);
                setDropdownLoading(templateSelect, false);
                if (networkSelect) setDropdownLoading(networkSelect, false);            } else {                // Fetch all resources for the selected datacenter and cache them
                console.log(`Fetching all resources for datacenter: ${selectedDC}`);
                
                // Make sure the progress container is visible
                if (progressContainer) {
                    progressContainer.style.display = 'block';
                }
                
                // Start progress tracking for resource pool loading
                startProgress(`Loading resources for ${selectedDC}`, 1, 'info');
                
                // First get the resource pools
                fetchResourcePoolsForDatacenter(selectedDC)
                    .then(pools => {
                        console.log(`Received ${pools.length} resource pools:`, pools);
                        
                        // Update progress to show resource pools loaded
                        updateProgress(1, `Found ${pools.length} resource pools in ${selectedDC}`);
                        
                        // If we have resource pools, start a new progress tracking for pre-fetching 
                        if (pools.length > 0) {
                            // We'll have 3 types of resources (datastores, templates, networks) for each pool
                            const totalPreFetchSteps = pools.length * 3;
                            startProgress(`Pre-fetching resources for ${pools.length} resource pools`, totalPreFetchSteps, 'info');
                        } else {
                            completeProgress(`No resource pools found in ${selectedDC}`, 'warning');
                        }
                        
                        // Initialize cache entry for this datacenter
                        datacenterResourcesCache[selectedDC] = {
                            pools: pools,
                            datastoresByPool: {},
                            templatesByPool: {},
                            networksByPool: {}
                        };
                        
                        // Populate resource pool dropdown
                        populateDropdown(resourcePoolSelect, pools, "Select Resource Pool...");
                        setDropdownLoading(resourcePoolSelect, false);
                        
                        // For each pool, pre-fetch and cache its resources
                        pools.forEach(pool => {
                            const poolId = pool.id || pool.name;
                            
                            // Fetch datastores
                            fetchDatastoresForResourcePool(selectedDC, poolId)
                                .then(datastores => {
                                    console.log(`Pre-cached ${datastores.length} datastores for pool: ${pool.name}`);
                                    datacenterResourcesCache[selectedDC].datastoresByPool[poolId] = datastores;
                                    updateProgress(1, `Loading resources: datastores for ${pool.name}`);
                                })
                                .catch(error => {
                                    console.error(`Error pre-caching datastores for pool ${pool.name}:`, error);
                                    updateProgress(1, `Error loading datastores for ${pool.name}`);
                                });
                            
                            // Fetch templates
                            fetchTemplatesForResourcePool(selectedDC, poolId)
                                .then(templates => {
                                    console.log(`Pre-cached ${templates.length} templates for pool: ${pool.name}`);
                                    datacenterResourcesCache[selectedDC].templatesByPool[poolId] = templates;
                                    updateProgress(1, `Loading resources: templates for ${pool.name}`);
                                })
                                .catch(error => {
                                    console.error(`Error pre-caching templates for pool ${pool.name}:`, error);
                                    updateProgress(1, `Error loading templates for ${pool.name}`);
                                });
                            
                            // Fetch networks
                            fetchNetworksForResourcePool(selectedDC, poolId)
                                .then(networks => {
                                    console.log(`Pre-cached ${networks.length} networks for pool: ${pool.name}`);
                                    datacenterResourcesCache[selectedDC].networksByPool[poolId] = networks;
                                    updateProgress(1, `Loading resources: networks for ${pool.name}`);
                                })
                                .catch(error => {
                                    console.error(`Error pre-caching networks for pool ${pool.name}:`, error);
                                    updateProgress(1, `Error loading networks for ${pool.name}`);
                                });
                        });        // Add completion handler for when all pre-fetching is done
                        Promise.allSettled(
                            pools.flatMap(pool => {
                                const poolId = pool.id || pool.name;
                                return [
                                    fetchDatastoresForResourcePool(selectedDC, poolId).catch(e => console.log(e)),
                                    fetchTemplatesForResourcePool(selectedDC, poolId).catch(e => console.log(e)),
                                    fetchNetworksForResourcePool(selectedDC, poolId).catch(e => console.log(e))
                                ];
                            })
                        ).then(() => {
                            // All pre-fetching completed (success or failure)
                            completeProgress(`All resources loaded for ${selectedDC}`, 'success', true);
                            
                            // Save updated cache to local storage
                            try {
                                localStorage.setItem('vsphereResourcesCache', JSON.stringify(datacenterResourcesCache));
                                localStorage.setItem('vsphereCacheTimestamp', new Date().getTime().toString());
                                console.log('Saved updated vSphere cache to local storage');
                            } catch (e) {
                                console.error('Error saving to local storage:', e);
                            }
                        });
                        
                        // Add global page status message
                        updateStatusMessage(`Loaded ${pools.length} resource pools for ${selectedDC}`, 'success');
                        
                        // Keep the other dropdowns disabled until resource pool selection
                        setDropdownLoading(datastoreSelect, false);
                        setDropdownLoading(templateSelect, false);
                        if (networkSelect) setDropdownLoading(networkSelect, false);
                    })
                    .catch(error => {
                        console.error('Error fetching resource pools:', error);
                        setProgressError(`Error loading resource pools: ${error.message}`);
                        updateStatusMessage(`Error loading resource pools: ${error.message}`, 'error');
                        setDropdownLoading(resourcePoolSelect, false);
                        setDropdownLoading(datastoreSelect, false);
                        setDropdownLoading(templateSelect, false);
                        if (networkSelect) setDropdownLoading(networkSelect, false);
                    });
            }
        }});
      
    // Resource pool change triggers populating dependent dropdowns from cache
    resourcePoolSelect.addEventListener('change', function() {
        const selectedPool = this.value;
        const selectedDC = datacenterSelect.value;
        
        console.log(`Resource pool selected: ${selectedPool} in datacenter: ${selectedDC}`);
          if (selectedPool && selectedDC) {
            // Update status message
            updateStatusMessage(`Loading resources for ${selectedPool}...`, 'info');
            
            // Reset dependent dropdowns
            resetDropdown(datastoreSelect, "Select Datastore...");
            resetDropdown(templateSelect, "Select Template...");
            if (networkSelect) resetDropdown(networkSelect, "Select Network...");
            
            // Show loading state
            setDropdownLoading(datastoreSelect, true);
            setDropdownLoading(templateSelect, true);
            if (networkSelect) setDropdownLoading(networkSelect, true);
              // Initialize cache structure if needed
            if (!datacenterResourcesCache[selectedDC]) {
                datacenterResourcesCache[selectedDC] = {
                    datastoresByPool: {},
                    templatesByPool: {},
                    networksByPool: {}
                };
            }
            
            // Check if we have both datastores and templates cached
            const datastoresCached = datacenterResourcesCache[selectedDC].datastoresByPool && 
                                   datacenterResourcesCache[selectedDC].datastoresByPool[selectedPool];
            const templatesCached = datacenterResourcesCache[selectedDC].templatesByPool && 
                                  datacenterResourcesCache[selectedDC].templatesByPool[selectedPool];
            
            // Debug cache state
            console.log(`Cache state - Datastores: ${datastoresCached ? 'Found' : 'Not found'}, Templates: ${templatesCached ? 'Found' : 'Not found'}`);
            
            if (datastoresCached && templatesCached) {
                // Use cached data
                console.log(`Using cached resources for pool: ${selectedPool}`);
                
                // Start a quick progress to show loading from cache
                startProgress(`Loading cached resources for ${selectedPool}`, 3, 'info');
                
                // Populate datastores
                const datastores = datacenterResourcesCache[selectedDC].datastoresByPool[selectedPool];
                console.log(`Populating datastores dropdown with ${datastores.length} items from cache`);
                populateDropdown(datastoreSelect, datastores, "Select Datastore...");
                setDropdownLoading(datastoreSelect, false);
                updateProgress(1, `Loading datastores from cache`);
                
                // Populate templates
                const templates = datacenterResourcesCache[selectedDC].templatesByPool[selectedPool];
                console.log(`Populating templates dropdown with ${templates.length} items from cache`);
                populateDropdown(templateSelect, templates, "Select Template...");
                setDropdownLoading(templateSelect, false);
                updateProgress(1, `Loading templates from cache`);
                
                // Populate networks if available
                if (networkSelect && datacenterResourcesCache[selectedDC].networksByPool && 
                    datacenterResourcesCache[selectedDC].networksByPool[selectedPool]) {
                    const networks = datacenterResourcesCache[selectedDC].networksByPool[selectedPool];
                    populateDropdown(networkSelect, networks, "Select Network...");
                    setDropdownLoading(networkSelect, false);
                    updateProgress(1, `Loading networks from cache`);
                } else {
                    updateProgress(1, `No networks available`);
                }
                
                // Complete the progress
                completeProgress(`Loaded all resources for ${selectedPool} from cache`, 'success', true);
                
                // Update status
                updateStatusMessage(`Loaded resources for ${selectedPool}`, 'success');
            } else {let completedRequests = 0;
                const totalRequests = networkSelect ? 3 : 2;
                
                // Start progress tracking for resource loading
                startProgress(`Loading resources for ${selectedPool}`, totalRequests, 'info');
                
                const updateProgress = () => {
                    completedRequests++;
                    const percent = Math.round((completedRequests / totalRequests) * 100);
                    
                    // Update progress message based on percent
                    if (completedRequests === totalRequests) {
                        completeProgress(`All resources loaded for ${selectedPool}`, 'success', true);
                        updateStatusMessage(`All resources loaded for ${selectedPool}`, 'success');
                    } else {
                        updateStatusMessage(`Loading resources: ${percent}% complete`, 'info');
                    }
                };// Fetch datastores if not cached
                if (!datacenterResourcesCache[selectedDC] || !datacenterResourcesCache[selectedDC].datastoresByPool[selectedPool]) {
                    console.log(`Fetching datastores for resource pool: ${selectedPool}`);
                    fetchDatastoresForResourcePool(selectedDC, selectedPool)
                        .then(datastores => {
                            console.log(`Received ${datastores.length} datastores:`, datastores);
                              // Cache the results
                            if (!datacenterResourcesCache[selectedDC]) {
                                datacenterResourcesCache[selectedDC] = {
                                    datastoresByPool: {},
                                    templatesByPool: {},
                                    networksByPool: {}
                                };
                            }
                            if (!datacenterResourcesCache[selectedDC].datastoresByPool) {
                                datacenterResourcesCache[selectedDC].datastoresByPool = {};
                            }
                            datacenterResourcesCache[selectedDC].datastoresByPool[selectedPool] = datastores;
                            
                            populateDropdown(datastoreSelect, datastores, "Select Datastore...");
                            setDropdownLoading(datastoreSelect, false);
                            updateProgress();
                        })
                        .catch(error => {
                            console.error('Error fetching datastores:', error);
                            setDropdownLoading(datastoreSelect, false);
                            updateStatusMessage(`Error loading datastores: ${error.message}`, 'error');
                            updateProgress();
                        });
                } else {
                    updateProgress();
                }
                
                // Fetch templates if not cached
                if (!datacenterResourcesCache[selectedDC] || !datacenterResourcesCache[selectedDC].templatesByPool[selectedPool]) {
                    console.log(`Fetching templates for resource pool: ${selectedPool}`);
                    fetchTemplatesForResourcePool(selectedDC, selectedPool)
                        .then(templates => {
                            console.log(`Received ${templates.length} templates:`, templates);
                              // Cache the results
                            if (!datacenterResourcesCache[selectedDC]) {
                                datacenterResourcesCache[selectedDC] = {
                                    datastoresByPool: {},
                                    templatesByPool: {},
                                    networksByPool: {}
                                };
                            }
                            if (!datacenterResourcesCache[selectedDC].templatesByPool) {
                                datacenterResourcesCache[selectedDC].templatesByPool = {};
                            }
                            datacenterResourcesCache[selectedDC].templatesByPool[selectedPool] = templates;
                            
                            populateDropdown(templateSelect, templates, "Select Template...");
                            setDropdownLoading(templateSelect, false);
                            updateProgress();
                        })
                        .catch(error => {
                            console.error('Error fetching templates:', error);
                            setDropdownLoading(templateSelect, false);
                            updateStatusMessage(`Error loading templates: ${error.message}`, 'error');
                            updateProgress();
                        });
                } else {
                    updateProgress();
                }
                  // Fetch networks if not cached
                if (networkSelect && (!datacenterResourcesCache[selectedDC] || !datacenterResourcesCache[selectedDC].networksByPool[selectedPool])) {
                    console.log(`Fetching networks for resource pool: ${selectedPool}`);
                    fetchNetworksForResourcePool(selectedDC, selectedPool)
                        .then(networks => {
                            console.log(`Received ${networks.length} networks:`, networks);
                            
                            // Cache the results
                            if (!datacenterResourcesCache[selectedDC]) {
                                datacenterResourcesCache[selectedDC] = { networksByPool: {} };
                            }
                            datacenterResourcesCache[selectedDC].networksByPool[selectedPool] = networks;
                            
                            populateDropdown(networkSelect, networks, "Select Network...");
                            setDropdownLoading(networkSelect, false);
                            updateProgress();
                        })
                        .catch(error => {
                            console.error('Error fetching networks:', error);
                            setDropdownLoading(networkSelect, false);
                            updateStatusMessage(`Error loading networks: ${error.message}`, 'error');
                            updateProgress();
                        });
                } else if (networkSelect) {
                    updateProgress();
                }
            }
        }
    });
}

/**
 * Add a loading indicator to a select element
 */
function addLoadingIndicator(selectElement) {
    // Create a container around the select for positioning
    const container = document.createElement('div');
    container.className = 'select-container';
    selectElement.parentNode.insertBefore(container, selectElement);
    container.appendChild(selectElement);
    
    // Add the loading spinner element
    const spinner = document.createElement('div');
    spinner.className = 'select-spinner';
    spinner.style.display = 'none';
    container.appendChild(spinner);
    
    // Add some basic styling
    container.style.position = 'relative';
    spinner.style.position = 'absolute';
    spinner.style.right = '10px';
    spinner.style.top = '50%';
    spinner.style.transform = 'translateY(-50%)';
    spinner.style.width = '16px';
    spinner.style.height = '16px';
    spinner.style.border = '2px solid rgba(0, 0, 0, 0.2)';
    spinner.style.borderTop = '2px solid #007bff';
    spinner.style.borderRadius = '50%';
    spinner.style.animation = 'spin 1s linear infinite';
    
    // Add the keyframes animation
    if (!document.getElementById('spinner-style')) {
        const style = document.createElement('style');
        style.id = 'spinner-style';
        style.textContent = `
            @keyframes spin {
                0% { transform: translateY(-50%) rotate(0deg); }
                100% { transform: translateY(-50%) rotate(360deg); }
            }
        `;
        document.head.appendChild(style);
    }
}

/**
 * Set the loading state of a dropdown
 */
function setDropdownLoading(selectElement, isLoading) {
    const container = selectElement.parentNode;
    const spinner = container.querySelector('.select-spinner');
    if (spinner) {
        spinner.style.display = isLoading ? 'block' : 'none';
    }
    selectElement.disabled = isLoading;
}

/**
 * Reset a dropdown to initial state
 */
function resetDropdown(selectElement, placeholderText) {
    selectElement.innerHTML = '';
    const placeholderOption = document.createElement('option');
    placeholderOption.value = '';
    placeholderOption.textContent = placeholderText;
    selectElement.appendChild(placeholderOption);
    selectElement.disabled = true;
}

/**
 * Populate a dropdown with options
 */
function populateDropdown(selectElement, items, placeholderText) {
    selectElement.innerHTML = '';
    
    // Add placeholder
    const placeholderOption = document.createElement('option');
    placeholderOption.value = '';
    placeholderOption.textContent = placeholderText;
    selectElement.appendChild(placeholderOption);
    
    // Filter out local datastores if this is the datastore dropdown
    let filteredItems = items;
    if (selectElement.id === 'vsphere_datastore' && items && items.length > 0) {
        filteredItems = items.filter(item => !item.name.includes('_local'));
        console.log(`Filtered out ${items.length - filteredItems.length} local datastores`);
    }
    
    // Add items
    if (filteredItems && filteredItems.length > 0) {
        filteredItems.forEach(item => {
            const option = document.createElement('option');
            option.value = item.id || item.name;
            option.textContent = item.name;
            selectElement.appendChild(option);
        });
        selectElement.disabled = false;
    } else {
        const noItemsOption = document.createElement('option');
        noItemsOption.value = '';
        noItemsOption.disabled = true;
        noItemsOption.textContent = `No ${placeholderText.toLowerCase().replace('select ', '').replace('...', '')} available`;
        selectElement.appendChild(noItemsOption);
    }
}

/**
 * Fetch resource pools for a datacenter
 */
function fetchResourcePoolsForDatacenter(datacenterName) {
    return fetch(`/api/vsphere/datacenter/${encodeURIComponent(datacenterName)}/pools`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        });
}

/**
 * Fetch datastores for a resource pool
 */
function fetchDatastoresForResourcePool(datacenterName, resourcePoolName) {
    return fetch(`/api/vsphere/datacenter/${encodeURIComponent(datacenterName)}/pool/${encodeURIComponent(resourcePoolName)}/datastores`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        });
}

/**
 * Fetch templates for a resource pool
 */
function fetchTemplatesForResourcePool(datacenterName, resourcePoolName) {
    return fetch(`/api/vsphere/datacenter/${encodeURIComponent(datacenterName)}/pool/${encodeURIComponent(resourcePoolName)}/templates`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        });
}

/**
 * Fetch networks for a resource pool
 */
function fetchNetworksForResourcePool(datacenterName, resourcePoolName) {
    return fetch(`/api/vsphere/datacenter/${encodeURIComponent(datacenterName)}/pool/${encodeURIComponent(resourcePoolName)}/networks`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        });
}
