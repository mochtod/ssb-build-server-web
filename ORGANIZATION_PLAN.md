# Project Organization Plan

## Completed Actions

1. **Fixed Critical Application Issue**
   - Fixed the logger definition issue in app.py by adding proper initialization before use
   - Cleaned up backup files (.bak, .original, .new, .fixed)

2. **Created Organized Test Structure**
   - Created 'tests' directory with subdirectories for different test types
   - Created test runner for unified test execution

3. **Started Moving Files**
   - Created 'old_tests' directory and moved all test_*.py files there
   - Created 'examples' directory and moved some example files there

## Recommended Organization Structure

For a cleaner project structure, organize files as follows:

```
ssb-build-server-web-1/
├── app.py                    # Main application entry point
├── requirements.txt          # Dependencies
├── Dockerfile                # Container definition
├── docker-compose.yml        # Multi-container setup
├── README.md                 # Project documentation
├── TESTING_IMPROVEMENTS.md   # Testing documentation
├── cline_docs/               # Project documentation directory
├── core/                     # Core application modules
│   ├── __init__.py
│   ├── config.py             # Configuration handling
│   ├── error_handler.py      # Error handling
│   ├── logger.py             # Logging configuration
│   ├── middleware.py         # Flask middleware
├── vsphere/                  # VSphere integration
│   ├── __init__.py
│   ├── vsphere_utils.py
│   ├── vsphere_redis_cache.py
│   ├── vsphere_hierarchical_loader.py
│   ├── vsphere_optimized_loader.py
│   ├── vsphere_cluster_resources.py
│   ├── vsphere_resource_functions.py
│   ├── vsphere_resource_validator.py
│   ├── vsphere_minimal_resources.py
│   ├── vsphere_location_utils.py
├── atlantis/                 # Atlantis integration
│   ├── __init__.py
│   ├── atlantis_api.py
│   ├── fix_atlantis_apply.py
│   ├── container_discovery.py
│   ├── terraform_validator.py
├── netbox/                   # NetBox integration
│   ├── __init__.py
│   ├── netbox_api.py
├── static/                   # Static web assets
│   ├── css/
│   ├── js/
├── templates/                # HTML templates
├── terraform/                # Terraform configuration
│   ├── .gitkeep
├── vm-workspace/             # VM workspace files
├── tests/                    # Test directory
│   ├── unit/
│   ├── integration/
│   ├── performance/
│   ├── atlantis/
│   ├── payload/
├── examples/                 # Example code
├── old_tests/                # Old test files (for reference)
```

## Implementation Steps

To continue organizing the project:

1. **Core Application Files**
   ```bash
   mkdir core
   move config.py error_handler.py logger.py middleware.py core\
   ```

2. **VSphere Integration**
   ```bash
   mkdir vsphere
   move vsphere_*.py vsphere\
   ```

3. **Atlantis Integration**
   ```bash
   mkdir atlantis
   move atlantis_api.py fix_atlantis_apply.py container_discovery.py terraform_validator.py atlantis\
   ```

4. **NetBox Integration**
   ```bash
   mkdir netbox
   move netbox_api.py netbox\
   ```

5. **Update Imports**
   After moving files, update import statements in app.py to reflect the new structure.

## Benefits

This organization:
1. Groups related functionality together
2. Makes the project easier to navigate
3. Separates core logic from integrations
4. Provides a clean and modular structure
5. Makes future development more maintainable

Following this organization scheme will make the codebase more maintainable and easier to understand for new developers.
