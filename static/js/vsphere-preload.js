/**
 * This function will preload data for all datacenters in the background
 * to make selecting datacenters and resource pools feel more responsive
 * @param {Object} cacheObject - The datacenter resources cache to populate
 */
function preloadAllDatacentersData(cacheObject) {
    // First, fetch all vSphere inventory to get datacenters
    console.log('Preloading vSphere inventory data in background');
    
    // Create a small status message (less intrusive than full progress bar)
    const statusMsg = document.createElement('div');
    statusMsg.className = 'preload-status';
    statusMsg.style.position = 'fixed';
    statusMsg.style.bottom = '10px';
    statusMsg.style.right = '10px';
    statusMsg.style.background = 'rgba(0,0,0,0.7)';
    statusMsg.style.color = '#fff';
    statusMsg.style.padding = '5px 10px';
    statusMsg.style.borderRadius = '3px';
    statusMsg.style.fontSize = '12px';
    statusMsg.style.zIndex = '1000';
    statusMsg.style.opacity = '0.8';
    statusMsg.textContent = 'Loading vSphere data in background...';
    document.body.appendChild(statusMsg);
    
    // Get all datacenters from the select dropdown
    const datacenterSelect = document.getElementById('vsphere_datacenter');
    if (!datacenterSelect) {
        console.error('Datacenter select element not found');
        statusMsg.remove();
        return;
    }
    
    const datacenters = Array.from(datacenterSelect.options)
        .filter(option => option.value)
        .map(option => option.value);
    
    if (datacenters.length === 0) {
        console.log('No datacenters found in the select dropdown');
        statusMsg.remove();
        return;
    }
    
    console.log(`Found ${datacenters.length} datacenters to preload`);
    
    // Create a queue to limit concurrent requests (to avoid overwhelming the server)
    const queue = [...datacenters];
    const maxConcurrent = 2; // Process 2 datacenters at a time
    let activeRequests = 0;
    let processedDatacenters = 0;
    
    // Function to process the next datacenter in the queue
    function processNextDatacenter() {
        if (queue.length === 0 || activeRequests >= maxConcurrent) return;
        
        activeRequests++;
        const dc = queue.shift();
        statusMsg.textContent = `Preloading data for ${dc} (${processedDatacenters}/${datacenters.length})`;
        
        console.log(`Preloading data for datacenter: ${dc}`);
        
        // Skip if we already have this datacenter in the cache
        if (cacheObject[dc] && cacheObject[dc].pools && cacheObject[dc].pools.length > 0) {
            console.log(`Using cached data for datacenter: ${dc}`);
            processedDatacenters++;
            activeRequests--;
            
            // Update status
            const progress = Math.round((processedDatacenters / datacenters.length) * 100);
            statusMsg.textContent = `Preloading vSphere data: ${progress}%`;
            
            // Process next datacenter
            processNextDatacenter();
            return;
        }
        
        // Get resource pools for this datacenter
        fetchResourcePoolsForDatacenter(dc)
            .then(pools => {
                console.log(`Preloaded ${pools.length} resource pools for ${dc}`);
                
                // Initialize cache for this datacenter
                if (!cacheObject[dc]) {
                    cacheObject[dc] = {
                        pools: pools,
                        datastoresByPool: {},
                        templatesByPool: {},
                        networksByPool: {}
                    };
                } else {
                    cacheObject[dc].pools = pools;
                }
                
                // If we have resource pools, consider preloading their resources too
                // but limit to first 2 pools to avoid too many requests
                const poolsToPreload = pools.slice(0, 2);
                
                // For each pool, prefetch key resources
                const poolPromises = poolsToPreload.map(pool => {
                    const poolId = pool.id || pool.name;
                    
                    // Prioritize templates - they're usually most relevant for VM creation
                    return fetchTemplatesForResourcePool(dc, poolId)
                        .then(templates => {
                            console.log(`Preloaded ${templates.length} templates for ${dc}/${pool.name}`);
                            cacheObject[dc].templatesByPool[poolId] = templates;
                        })
                        .catch(e => console.warn(`Error preloading templates for ${dc}/${pool.name}:`, e));
                });
                
                return Promise.allSettled(poolPromises);
            })
            .catch(error => {
                console.warn(`Error preloading data for datacenter ${dc}:`, error);
            })
            .finally(() => {
                processedDatacenters++;
                activeRequests--;
                
                // Update status
                const progress = Math.round((processedDatacenters / datacenters.length) * 100);
                statusMsg.textContent = `Preloading vSphere data: ${progress}%`;
                
                // Process next datacenter
                processNextDatacenter();
                
                // If we're done with all datacenters
                if (processedDatacenters >= datacenters.length) {
                    console.log('Finished preloading all datacenter data');
                    
                    // Save to local storage
                    try {
                        localStorage.setItem('vsphereResourcesCache', JSON.stringify(cacheObject));
                        localStorage.setItem('vsphereCacheTimestamp', new Date().getTime().toString());
                        console.log('Saved preloaded vSphere cache to local storage');
                    } catch (e) {
                        console.error('Error saving preloaded data to local storage:', e);
                    }
                    
                    // Remove the status message
                    setTimeout(() => {
                        statusMsg.style.transition = 'opacity 0.5s';
                        statusMsg.style.opacity = '0';
                        setTimeout(() => statusMsg.remove(), 500);
                    }, 1000);
                }
            });
    }
    
    // Start processing the queue (up to maxConcurrent requests)
    for (let i = 0; i < Math.min(maxConcurrent, queue.length); i++) {
        processNextDatacenter();
    }
}
