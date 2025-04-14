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

    // If still no theme, default to dark
    savedTheme = savedTheme || 'dark';

    // Apply theme immediately
    if (savedTheme === 'light') {
        document.body.classList.remove('dark-theme');
        document.body.classList.add('light-mode');
    } else {
        document.body.classList.add('dark-theme');
        document.body.classList.remove('light-mode');
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

    // Initialize accordions for expandable sections
    initializeAccordions();

    // Initialize form debugging
    initializeFormDebugging();

    console.log('DEBUG: All initialization functions completed');
});

/**
 * Initialize theme toggle functionality
 */
function initializeThemeToggle() {
    const themeToggleBtn = document.getElementById('theme-toggle');
    
    if (themeToggleBtn) {
        const themeIconDark = document.getElementById('theme-icon-dark');
        const themeIconLight = document.getElementById('theme-icon-light');
        const themeText = document.getElementById('theme-text');

        // Check for saved theme preference or use default
        const savedTheme = localStorage.getItem('theme') || 'dark';

        // Apply the saved theme
        setTheme(savedTheme);

        // Handle theme toggle click
        themeToggleBtn.addEventListener('click', function() {
            // Check current theme
            const isDarkTheme = document.body.classList.contains('dark-theme');

            // Determine new theme
            const newTheme = isDarkTheme ? 'light' : 'dark';

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

        /**
         * Set theme and update UI elements
         * @param {string} theme - 'dark' or 'light'
         */
        function setTheme(theme) {
            if (theme === 'light') {
                document.body.classList.remove('dark-theme');
                document.body.classList.add('light-mode');
                if (themeIconDark && themeIconLight && themeText) {
                    themeIconDark.style.display = 'inline-block';
                    themeIconLight.style.display = 'none';
                    themeText.textContent = 'Dark Mode'; // Shows what mode will be switched to
                }
            } else {
                document.body.classList.add('dark-theme');
                document.body.classList.remove('light-mode');
                if (themeIconDark && themeIconLight && themeText) {
                    themeIconDark.style.display = 'none';
                    themeIconLight.style.display = 'inline-block';
                    themeText.textContent = 'Light Mode'; // Shows what mode will be switched to
                }
            }
        }
    }
}

/**
 * Initialize accordion functionality for expandable sections
 */
function initializeAccordions() {
    const accordions = document.querySelectorAll('.accordion');

    accordions.forEach(accordion => {
        const header = accordion.querySelector('.accordion-header');

        if (header) {
            header.addEventListener('click', () => {
                // Toggle active class on accordion
                accordion.classList.toggle('active');

                // Find the content section
                const content = accordion.querySelector('.accordion-content');

                // Toggle max-height based on active state
                if (accordion.classList.contains('active')) {
                    // Set max-height to a value larger than the content will be
                    content.style.maxHeight = '500px';
                } else {
                    // Reset max-height to 0 to close the accordion
                    content.style.maxHeight = '0';
                }
            });
        }
    });
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
                    console.error('Failed to copy text:', err);
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
                    console.error('Failed to copy code:', err);
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
 * Initialize form submission debugging
 */
function initializeFormDebugging() {
    const createVmForm = document.querySelector('form[action="/submit"]');

    if (createVmForm) {
        console.log('DEBUG: Form submission debugging initialized');

        createVmForm.addEventListener('submit', function(e) {
            // Prevent form submission to check data
            e.preventDefault();

            console.log('DEBUG: Form submission attempted');

            // Check if all required fields are filled
            const requiredFields = [
                'server_prefix', 'app_name', 'datacenter',
                'cluster', 'resource_pool', 'datastore', 'network'
            ];

            let missingFields = [];
            requiredFields.forEach(field => {
                const element = document.getElementById(field);
                if (!element || !element.value) {
                    missingFields.push(field);
                    console.error(`DEBUG: Required field missing: ${field}`);
                }
            });

            if (missingFields.length > 0) {
                alert(`Please fill in all required fields: ${missingFields.join(', ')}`);
                return;
            }

            // Check VSphere resources
            const resourceData = {
                datacenter: document.getElementById('datacenter').value,
                cluster: document.getElementById('cluster').value,
                resource_pool: document.getElementById('resource_pool').value,
                datastore: document.getElementById('datastore').value,
                network: document.getElementById('network').value,
                template: document.getElementById('template').value || 'No template selected'
            };

            console.log('DEBUG: Resource data:', resourceData);

            // Log all form data
            const formData = new FormData(this);
            const formValues = {};
            for (let [key, value] of formData.entries()) {
                formValues[key] = value;
            }
            console.log('DEBUG: All form values:', formValues);

            // Continue with form submission
            console.log('DEBUG: Form submission proceeding');
            this.submit();
        });
    }
}

/**
 * Initialize VSphere resource loading functionality with datacenter-to-cluster hierarchical approach
 * - First loads available datacenters
 * - When a datacenter is selected, fetches clusters specific to that datacenter
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
            document.getElementById('templates_container').style.display = 'none';

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
                    document.getElementById('templates_container').style.display = 'none';

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
            .then(response => response.json())
            .then(data => {
                // Update resource pools (should be only one per cluster)
                if (data.resource_pools && data.resource_pools.length > 0) {
                    const resourcePoolSelect = document.getElementById('resource_pool');
                    updateResourceDropdown(resourcePoolSelect, data.resource_pools);
                    document.getElementById('resource_pool_container').style.display = 'flex';

                    // If there's only one resource pool select it automatically
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

                // Update networks (now handled separately)
                if (data.networks && data.networks.length > 0) {
                    const networkSelect = document.getElementById('network');
                    updateResourceDropdown(networkSelect, data.networks);
                    document.getElementById('networks_container').style.display = 'flex';
                }

                // Templates (now shown as requested)
                if (data.templates && data.templates.length > 0) {
                    const templateSelect = document.getElementById('template');
                    updateResourceDropdown(templateSelect, data.templates);
                    document.getElementById('templates_container').style.display = 'flex';
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
