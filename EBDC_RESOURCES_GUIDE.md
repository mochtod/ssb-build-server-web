# EBDC Resources Guide

## Overview

This guide describes the implementation of the EBDC-specific resource retrieval functionality added to the SSB Build Server Web application. This functionality allows users to specifically target resources from the EBDC NONPROD and EBDC PROD datacenters, and automatically filters out local datastores.

## Features Implemented

1. **EBDC-Specific Resource Retrieval**: A new function in `vsphere_cluster_resources.py` called `get_ebdc_resources()` that:
   - Targets only EBDC NONPROD and EBDC PROD datacenters
   - Retrieves all clusters within these datacenters
   - For each cluster, loads all associated resources (resource pools, datastores, networks, templates)
   - Filters out local datastores (containing "_local" in their names)
   - Organizes everything into an easy-to-use hierarchical structure

2. **API Endpoint**: A new API endpoint in `app.py` at `/api/vsphere/ebdc_resources` that:
   - Returns all EBDC resources in a JSON format
   - Makes the data available to the UI for selection workflows
   - Also filters out local datastores automatically

3. **Environment Configuration**: Updated Docker Compose file to:
   - Set `VSPHERE_DATACENTERS=EBDC NONPROD,EBDC PROD` by default
   - Ensure both web and Atlantis containers target the same datacenters

4. **Cluster-Based Resource Selection**: Enhanced the existing cluster-based API to:
   - Filter out local datastores in `/api/vsphere/clusters/<cluster_id>/resources`
   - Maintain consistency across different API endpoints

5. **Test & Simulation Functionality**: Added:
   - Simulation mode for testing without real vSphere credentials
   - Test scripts to verify EBDC resource loading
   - API testing script to validate the new endpoint

## How to Use

### Using EBDC-Specific API Endpoint

```javascript
// Frontend JavaScript
fetch('/api/vsphere/ebdc_resources')
  .then(response => response.json())
  .then(data => {
    // Data contains datacenters, each with clusters and their resources
    const datacenters = data.datacenters;
    
    // Example: Populate a datacenter dropdown
    const datacenterSelect = document.getElementById('datacenter-select');
    datacenters.forEach(dc => {
      const option = document.createElement('option');
      option.value = dc.name;
      option.textContent = dc.name;
      datacenterSelect.appendChild(option);
    });
    
    // When a datacenter is selected, show its clusters
    datacenterSelect.addEventListener('change', (e) => {
      const selectedDC = datacenters.find(dc => dc.name === e.target.value);
      populateClusters(selectedDC.clusters);
    });
  });

// Function to populate clusters based on selected datacenter
function populateClusters(clusters) {
  const clusterSelect = document.getElementById('cluster-select');
  clusterSelect.innerHTML = ''; // Clear existing options
  
  clusters.forEach(cluster => {
    const option = document.createElement('option');
    option.value = cluster.id;
    option.textContent = cluster.name;
    clusterSelect.appendChild(option);
  });
  
  // When a cluster is selected, show its resources
  clusterSelect.addEventListener('change', (e) => {
    const selectedCluster = clusters.find(c => c.id === e.target.value);
    populateResources(selectedCluster);
  });
}

// Function to show resources for a selected cluster
function populateResources(cluster) {
  // Populate resource pools
  populateResourceSelect('resource-pool-select', cluster.resource_pools);
  
  // Populate datastores (already filtered, no _local datastores)
  populateResourceSelect('datastore-select', cluster.datastores);
  
  // Populate networks
  populateResourceSelect('network-select', cluster.networks);
}

// Generic function to populate a select element with resources
function populateResourceSelect(selectId, resources) {
  const select = document.getElementById(selectId);
  select.innerHTML = ''; // Clear existing options
  
  resources.forEach(resource => {
    const option = document.createElement('option');
    option.value = resource.id;
    option.textContent = resource.name;
    select.appendChild(option);
  });
}
```

### Using from Python Code

```python
# Import the function directly
from vsphere_cluster_resources import get_ebdc_resources

# Get all EBDC resources (with automated _local datastore filtering)
resources = get_ebdc_resources(force_refresh=False)  # Use force_refresh=True to bypass cache

# Access the data
datacenters = resources.get('datacenters')  # List of datacenter names
clusters = resources.get('clusters')  # List of all clusters across both datacenters
clusters_by_dc = resources.get('clusters_by_datacenter')  # Dictionary of clusters grouped by datacenter
resources_by_cluster = resources.get('resources')  # Dictionary of resources for each cluster

# Example: Print all clusters in EBDC NONPROD
nonprod_clusters = clusters_by_dc.get('EBDC NONPROD', [])
for cluster in nonprod_clusters:
    print(f"Cluster: {cluster['name']} (ID: {cluster['id']})")
    
    # Get resources for this cluster
    cluster_resources = resources_by_cluster.get(cluster['id'], {})
    
    # Print datastores (filtered, no _local datastores)
    datastores = cluster_resources.get('datastores', [])
    print(f"  Datastores: {len(datastores)}")
    for ds in datastores[:3]:  # Show first 3
        print(f"    - {ds['name']} (Free: {ds.get('free_gb', 'N/A')} GB)")
```

## Testing

Two test scripts are provided:

1. **test_ebdc_resources.py**: Tests the `get_ebdc_resources()` function directly
   ```bash
   python test_ebdc_resources.py
   ```

2. **test_ebdc_api.py**: Tests the API endpoint `/api/vsphere/ebdc_resources`
   ```bash
   # To just test the API (server must be running)
   python test_ebdc_api.py
   
   # To start the Flask app and test the API
   START_FLASK_APP=true python test_ebdc_api.py
   ```

## Running with Docker Compose

The Docker Compose file has been updated to include the VSPHERE_DATACENTERS environment variable. To run the application:

```bash
# Start the containers
docker-compose up -d

# Check logs
docker-compose logs web
docker-compose logs atlantis
```

## Simulation Mode

For testing without real vSphere credentials, you can use the simulation mode:

```bash
# Set dummy credentials
export VSPHERE_SERVER=vsphere-server
export VSPHERE_USER=vsphere-username
export VSPHERE_PASSWORD=vsphere-password
export VSPHERE_DATACENTERS="EBDC NONPROD,EBDC PROD"

# Run any test script or the application
python test_ebdc_resources.py
```

The code will automatically detect the dummy credentials and enter simulation mode, providing sample data for testing purposes.
