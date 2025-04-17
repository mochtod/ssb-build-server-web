/**
 * vSphere Cache Display Handler
 * 
 * This script manages the display of vSphere resources from the Redis cache
 * to ensure proper presentation in the VM creation form.
 */

// Global state to track selected values and cache status
const vsphereCacheState = {
    isLoading: false,
    resourcesLoaded: false,
    selectedDC: '',
    selectedPool: '',
    dataRefreshTimestamp: null
};

document.addEventListener('DOMContentLoaded', function() {
    initVSphereCacheDisplay();
});

/**
 * Initialize the vSphere cache display handler
 */
function initVSphereCacheDisplay() {
    // Get form elements
    const dcSelect = document.getElementById('vsphere_datacenter');
    const poolSelect = document.getElementById('vsphere_resource_pool');
    const datastoreSelect = document.getElementById('vsphere_datastore');
    const templateSelect = document.getElementById('vsphere_template');
    const networkSelect = document.getElementById('vsphere_network');
    
    if (!dcSelect) return; // Not on the VM creation page
    
    // Add listener for datacenter selection changes
    dcSelect.addEventListener('change', function() {
        const selectedDC = this.value;
        if (!selectedDC) return;
        
        vsphereCacheState.selectedDC = selectedDC;
        vsphereCacheState.selectedPool = '';
        
        // Enable resource pool select and clear other selects
        poolSelect.disabled = false;
        loadResourcePoolsFromCache(selectedDC);
        
        // Disable and clear other selects until resource pool is selected
        datastoreSelect.disabled = true;
        datastoreSelect.innerHTML = '<option value="">Select Datastore...</option>';
        
        templateSelect.disabled = true;
        templateSelect.innerHTML = '<option value="">Select Template...</option>';
        
        networkSelect.disabled = true;
        networkSelect.innerHTML = '<option value="">Select Network...</option>';
    });
    
    // Add listener for resource pool selection changes
    poolSelect.addEventListener('change', function() {
        const selectedPool = this.value;
        if (!selectedPool) return;
        
        vsphereCacheState.selectedPool = selectedPool;
        
        // Enable and load dependent selects
        datastoreSelect.disabled = false;
        templateSelect.disabled = false;
        networkSelect.disabled = false;
        
        loadDatastoresFromCache(vsphereCacheState.selectedDC, selectedPool);
        loadTemplatesFromCache(vsphereCacheState.selectedDC, selectedPool);
        loadNetworksFromCache(vsphereCacheState.selectedDC, selectedPool);
    });
    
    // Check if we have cached data
    checkCacheStatus();
}

/**
 * Check the status of the vSphere cache
 */
function checkCacheStatus() {
    fetch('/api/vsphere-cache-status')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                vsphereCacheState.resourcesLoaded = true;
                vsphereCacheState.dataRefreshTimestamp = data.last_update;
                
                // Update cache info display if present
                const cacheInfo = document.getElementById('vsphere-cache-info');
                if (cacheInfo) {
                    const lastUpdate = new Date(data.last_update);
                    cacheInfo.innerHTML = `<small>Cache last updated: ${lastUpdate.toLocaleString()}</small>`;
                }
                
                // Hide loading indicator if present
                const loadingIndicator = document.getElementById('loading-progress-container');
                if (loadingIndicator) {
                    loadingIndicator.style.display = 'none';
                }
            } else {
                console.warn('vSphere cache status check failed:', data.message);
            }
        })
        .catch(error => {
            console.error('Error checking cache status:', error);
        });
}

/**
 * Load resource pools from cache for the selected datacenter
 */
function loadResourcePoolsFromCache(datacenter) {
    const poolSelect = document.getElementById('vsphere_resource_pool');
    if (!poolSelect) return;
    
    // Show loading indicator
    poolSelect.innerHTML = '<option value="">Loading resource pools...</option>';
    
    fetch(`/api/vsphere-resource-pools?datacenter=${encodeURIComponent(datacenter)}`)
        .then(response => response.json())
        .then(data => {
            // Clear select
            poolSelect.innerHTML = '<option value="">Select Resource Pool...</option>';
            
            // Add resource pools to select
            if (data.resource_pools && data.resource_pools.length > 0) {
                data.resource_pools.forEach(pool => {
                    const option = document.createElement('option');
                    option.value = pool.id || pool.name;
                    option.textContent = pool.name;
                    poolSelect.appendChild(option);
                });
                
                console.log(`Loaded ${data.resource_pools.length} resource pools from cache`);
            } else {
                // No resource pools found
                poolSelect.innerHTML = '<option value="">No resource pools available</option>';
                console.warn('No resource pools found in cache for datacenter:', datacenter);
            }
        })
        .catch(error => {
            console.error('Error loading resource pools from cache:', error);
            poolSelect.innerHTML = '<option value="">Error loading resource pools</option>';
        });
}

/**
 * Load datastores from cache for the selected datacenter and resource pool
 */
function loadDatastoresFromCache(datacenter, resourcePool) {
    const datastoreSelect = document.getElementById('vsphere_datastore');
    if (!datastoreSelect) return;
    
    // Show loading indicator
    datastoreSelect.innerHTML = '<option value="">Loading datastores...</option>';
    
    fetch(`/api/vsphere-datastores?datacenter=${encodeURIComponent(datacenter)}&resource_pool=${encodeURIComponent(resourcePool)}`)
        .then(response => response.json())
        .then(data => {
            // Clear select
            datastoreSelect.innerHTML = '<option value="">Select Datastore...</option>';
            
            // Add datastores to select, sorting by available space
            if (data.datastores && data.datastores.length > 0) {
                // Sort datastores by free space (largest first)
                const sortedDatastores = [...data.datastores].sort((a, b) => {
                    const aFree = a.free_gb || 0;
                    const bFree = b.free_gb || 0;
                    return bFree - aFree;
                });
                
                sortedDatastores.forEach(ds => {
                    const option = document.createElement('option');
                    option.value = ds.id || ds.name;
                    
                    // Add free space info if available
                    let displayText = ds.name;
                    if (ds.free_gb !== undefined) {
                        displayText += ` (${ds.free_gb.toFixed(0)} GB free)`;
                    }
                    
                    option.textContent = displayText;
                    datastoreSelect.appendChild(option);
                });
                
                console.log(`Loaded ${data.datastores.length} datastores from cache`);
            } else {
                // No datastores found
                datastoreSelect.innerHTML = '<option value="">No datastores available</option>';
                console.warn('No datastores found in cache for selected resource pool');
            }
        })
        .catch(error => {
            console.error('Error loading datastores from cache:', error);
            datastoreSelect.innerHTML = '<option value="">Error loading datastores</option>';
        });
}

/**
 * Load templates from cache for the selected datacenter and resource pool
 */
function loadTemplatesFromCache(datacenter, resourcePool) {
    const templateSelect = document.getElementById('vsphere_template');
    if (!templateSelect) return;
    
    // Show loading indicator
    templateSelect.innerHTML = '<option value="">Loading templates...</option>';
    
    fetch(`/api/vsphere-templates?datacenter=${encodeURIComponent(datacenter)}&resource_pool=${encodeURIComponent(resourcePool)}`)
        .then(response => response.json())
        .then(data => {
            // Clear select
            templateSelect.innerHTML = '<option value="">Select Template...</option>';
            
            // Add templates to select
            if (data.templates && data.templates.length > 0) {
                // Sort templates alphabetically
                const sortedTemplates = [...data.templates].sort((a, b) => {
                    const aName = typeof a === 'string' ? a : (a.name || '');
                    const bName = typeof b === 'string' ? b : (b.name || '');
                    return aName.localeCompare(bName);
                });
                
                sortedTemplates.forEach(template => {
                    const option = document.createElement('option');
                    const templateName = typeof template === 'string' ? template : (template.name || '');
                    const templateId = typeof template === 'string' ? template : (template.id || template.name || '');
                    
                    option.value = templateId;
                    option.textContent = templateName;
                    templateSelect.appendChild(option);
                });
                
                console.log(`Loaded ${data.templates.length} templates from cache`);
            } else {
                // No templates found
                templateSelect.innerHTML = '<option value="">No templates available</option>';
                console.warn('No templates found in cache for selected resource pool');
            }
        })
        .catch(error => {
            console.error('Error loading templates from cache:', error);
            templateSelect.innerHTML = '<option value="">Error loading templates</option>';
        });
}

/**
 * Load networks from cache for the selected datacenter and resource pool
 */
function loadNetworksFromCache(datacenter, resourcePool) {
    const networkSelect = document.getElementById('vsphere_network');
    if (!networkSelect) return;
    
    // Show loading indicator
    networkSelect.innerHTML = '<option value="">Loading networks...</option>';
    
    fetch(`/api/vsphere-networks?datacenter=${encodeURIComponent(datacenter)}&resource_pool=${encodeURIComponent(resourcePool)}`)
        .then(response => response.json())
        .then(data => {
            // Clear select
            networkSelect.innerHTML = '<option value="">Select Network...</option>';
            
            // Add networks to select
            if (data.networks && data.networks.length > 0) {
                // Sort networks alphabetically
                const sortedNetworks = [...data.networks].sort((a, b) => {
                    const aName = typeof a === 'string' ? a : (a.name || '');
                    const bName = typeof b === 'string' ? b : (b.name || '');
                    return aName.localeCompare(bName);
                });
                
                sortedNetworks.forEach(network => {
                    const option = document.createElement('option');
                    const networkName = typeof network === 'string' ? network : (network.name || '');
                    const networkId = typeof network === 'string' ? network : (network.id || network.name || '');
                    
                    option.value = networkId;
                    option.textContent = networkName;
                    networkSelect.appendChild(option);
                });
                
                console.log(`Loaded ${data.networks.length} networks from cache`);
            } else {
                // No networks found
                networkSelect.innerHTML = '<option value="">No networks available</option>';
                console.warn('No networks found in cache for selected resource pool');
            }
        })
        .catch(error => {
            console.error('Error loading networks from cache:', error);
            networkSelect.innerHTML = '<option value="">Error loading networks</option>';
        });
}
