#!/usr/bin/env python3
"""
Centralized Configuration Management for SSB Build Server Web

This module provides a centralized way to handle configuration settings
across the application. It includes:
- Environment variable loading and validation
- Sensible defaults
- Derived configuration values
- Validation of required configurations
- Secure handling of sensitive values

Usage:
    from config import config
    
    # Access configuration values
    server_url = config.get('ATLANTIS_URL')
    
    # Access with default value
    timeout = config.get('TIMEOUT', 30)
    
    # Access with type conversion
    debug_mode = config.get_bool('DEBUG', False)
    max_retries = config.get_int('MAX_RETRIES', 3)
    
    # Access sensitive values
    api_token = config.get_secret('ATLANTIS_TOKEN')
"""
import os
import sys
import logging
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union, TypeVar, Callable

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('config')

# Type variable for generic type conversion
T = TypeVar('T')

class Configuration:
    """
    Centralized configuration management with environment variable support.
    """
    # Map of configuration groups for better organization
    CONFIG_GROUPS = {
        'app': [
            'FLASK_SECRET_KEY', 'CONFIG_DIR', 'TERRAFORM_DIR', 'USERS_FILE',
            'DEBUG', 'TIMEOUT'
        ],
        'atlantis': [
            'ATLANTIS_URL', 'ATLANTIS_TOKEN', 'ATLANTIS_PORT',
            'ATLANTIS_CONFIG', 'ATLANTIS_REPO_ALLOWLIST'
        ],
        'vsphere': [
            'VSPHERE_USER', 'VSPHERE_PASSWORD', 'VSPHERE_SERVER',
            'RESOURCE_POOL_ID', 'DEV_RESOURCE_POOL_ID', 'DATASTORE_ID',
            'NETWORK_ID_PROD', 'NETWORK_ID_DEV', 'TEMPLATE_UUID'
        ],
        'netbox': [
            'NETBOX_TOKEN', 'NETBOX_URL'
        ],
        'github': [
            'GITHUB_USER', 'GITHUB_TOKEN', 'GIT_REPO_URL',
            'GIT_USERNAME', 'GIT_TOKEN', 'GH_WEBHOOK_SECRET'
        ]
    }
    
    # Sensitive values that should be masked in logs
    SENSITIVE_KEYS = {
        'FLASK_SECRET_KEY', 'VSPHERE_PASSWORD', 'ATLANTIS_TOKEN',
        'NETBOX_TOKEN', 'GITHUB_TOKEN', 'GIT_TOKEN'
    }
    
    # Default values for configuration
    DEFAULTS = {
        'CONFIG_DIR': 'configs',
        'TERRAFORM_DIR': 'terraform',
        'USERS_FILE': 'users.json',
        'DEBUG': 'False',
        'TIMEOUT': '120',
        'ATLANTIS_URL': 'http://atlantis:4141',
        'ATLANTIS_PORT': '4141',
        'ATLANTIS_REPO_ALLOWLIST': '*'
    }
    
    # Required configurations that must be set
    REQUIRED = {
        'FLASK_SECRET_KEY', 
        'ATLANTIS_TOKEN'
    }
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        self._config = {}
        self._load_from_env()
        self._validate_required()
    
    def _load_from_env(self):
        """Load configuration from environment variables and .env file."""
        # Load from environment variables
        for key in self._get_all_config_keys():
            value = os.environ.get(key, self.DEFAULTS.get(key, None))
            if value is not None:
                self._config[key] = value
        
        # Load from .env file if it exists
        env_file = Path('.env')
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            # Only set if not already set from environment
                            if key not in self._config:
                                self._config[key] = value
            except Exception as e:
                logger.warning(f"Error reading .env file: {str(e)}")
        
        # Log the configuration (safely)
        self._log_configuration()
    
    def _get_all_config_keys(self) -> Set[str]:
        """Get all configuration keys from all groups."""
        keys = set()
        for group_keys in self.CONFIG_GROUPS.values():
            keys.update(group_keys)
        return keys
    
    def _log_configuration(self):
        """Log the current configuration, masking sensitive values."""
        logger.info("Configuration loaded:")
        for group, keys in self.CONFIG_GROUPS.items():
            group_values = {}
            for key in keys:
                if key in self._config:
                    if key in self.SENSITIVE_KEYS:
                        # Mask sensitive values
                        value = '*' * 8
                    else:
                        value = self._config[key]
                    group_values[key] = value
            
            if group_values:
                logger.info(f"{group.upper()} configuration: {json.dumps(group_values)}")
    
    def _validate_required(self):
        """Validate that all required configurations are set."""
        missing = []
        for key in self.REQUIRED:
            if key not in self._config or not self._config[key]:
                missing.append(key)
                
        if missing:
            logger.warning(f"Missing required configuration values: {', '.join(missing)}")
            # Don't fail the application, but do warn that some functionality may be limited
    
    def get(self, key: str, default: Any = None) -> str:
        """
        Get a configuration value.
        
        Args:
            key: The configuration key
            default: Default value if the key is not found
            
        Returns:
            The configuration value as a string
        """
        return self._config.get(key, default)
    
    def get_int(self, key: str, default: Optional[int] = None) -> Optional[int]:
        """Get a configuration value as an integer."""
        value = self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning(f"Invalid integer value for {key}: {value}, using default: {default}")
            return default
    
    def get_bool(self, key: str, default: Optional[bool] = None) -> Optional[bool]:
        """Get a configuration value as a boolean."""
        value = self.get(key)
        if value is None:
            return default
        
        if isinstance(value, bool):
            return value
        
        # Convert string to boolean
        if value.lower() in ('true', 'yes', 'y', '1'):
            return True
        if value.lower() in ('false', 'no', 'n', '0'):
            return False
        
        logger.warning(f"Invalid boolean value for {key}: {value}, using default: {default}")
        return default
    
    def get_list(self, key: str, default: Optional[List[str]] = None, separator: str = ',') -> Optional[List[str]]:
        """Get a configuration value as a list."""
        value = self.get(key)
        if value is None:
            return default or []
        
        if isinstance(value, list):
            return value
        
        # Convert string to list
        return [item.strip() for item in value.split(separator) if item.strip()]
    
    def get_secret(self, key: str) -> Optional[str]:
        """
        Get a sensitive configuration value.
        This is the same as get() but adds extra logging protection.
        """
        # Ensure this key is marked as sensitive
        if key not in self.SENSITIVE_KEYS:
            self.SENSITIVE_KEYS.add(key)
            logger.info(f"Added {key} to sensitive keys")
        
        return self.get(key)
    
    def get_path(self, key: str, default: Optional[str] = None) -> Optional[Path]:
        """Get a configuration value as a Path object."""
        value = self.get(key)
        if value is None:
            return Path(default) if default else None
        return Path(value)
    
    def get_for_environment(self, key_suffix: str, environment: str) -> Optional[str]:
        """
        Get an environment-specific configuration value.
        
        For example, if environment is 'production', it will first look for
        KEY_PROD, then fall back to KEY.
        
        Args:
            key_suffix: The suffix of the configuration key (e.g., 'RESOURCE_POOL_ID')
            environment: The environment name (e.g., 'production', 'development')
            
        Returns:
            The configuration value for the specific environment
        """
        env_map = {
            'production': 'PROD',
            'development': 'DEV',
            'integration': 'INT',
            'training': 'TRN'
        }
        
        env_suffix = env_map.get(environment.lower(), '')
        if env_suffix:
            env_key = f"{key_suffix}_{env_suffix}"
            value = self.get(env_key)
            if value is not None:
                return value
        
        # Fall back to the generic key
        return self.get(key_suffix)
    
    def get_all(self) -> Dict[str, str]:
        """Get a copy of all configuration values."""
        return self._config.copy()
    
    def get_group(self, group: str) -> Dict[str, str]:
        """Get all configuration values for a specific group."""
        if group not in self.CONFIG_GROUPS:
            return {}
        
        return {key: self._config.get(key, self.DEFAULTS.get(key, '')) 
                for key in self.CONFIG_GROUPS[group] 
                if key in self._config}
    
    def set(self, key: str, value: Any):
        """Set a configuration value at runtime."""
        self._config[key] = str(value)
        # Also set in environment for child processes
        os.environ[key] = str(value)
        logger.info(f"Set configuration {key}={value if key not in self.SENSITIVE_KEYS else '*****'}")
    
    def save_to_env_file(self, path: str = '.env'):
        """
        Save the current configuration to a .env file.
        Groups will be used to organize the file.
        """
        try:
            # Create backup of current .env file
            if os.path.exists(path):
                backup_file = f"{path}.bak"
                import shutil
                shutil.copy2(path, backup_file)
                logger.info(f"Created backup of {path} at {backup_file}")
            
            # Write new .env file
            with open(path, 'w') as f:
                # Write header
                f.write("# SSB Build Server Web Environment Configuration\n")
                f.write("# Generated on " + 
                        __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S") + 
                        "\n\n")
                
                # Write each group
                for group, keys in self.CONFIG_GROUPS.items():
                    group_values = {k: self._config[k] for k in keys if k in self._config}
                    if group_values:
                        f.write(f"# {group.upper()} Configuration\n")
                        for key, value in group_values.items():
                            f.write(f"{key}={value}\n")
                        f.write("\n")
                
            logger.info(f"Saved configuration to {path}")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration to {path}: {str(e)}")
            return False

# Create singleton instance
config = Configuration()

if __name__ == "__main__":
    """When run as a script, print current configuration."""
    import argparse
    parser = argparse.ArgumentParser(description='SSB Build Server Web Configuration')
    parser.add_argument('--save', action='store_true', help='Save configuration to .env file')
    parser.add_argument('--group', help='Show only configuration for this group')
    args = parser.parse_args()
    
    if args.save:
        config.save_to_env_file()
    elif args.group:
        group_config = config.get_group(args.group)
        if group_config:
            print(f"\n{args.group.upper()} Configuration:")
            for key, value in group_config.items():
                masked_value = value if key not in config.SENSITIVE_KEYS else '*' * 8
                print(f"  {key}={masked_value}")
        else:
            print(f"No configuration found for group: {args.group}")
    else:
        # Print all configuration (except sensitive values)
        print("\nCurrent Configuration:")
        for group, keys in config.CONFIG_GROUPS.items():
            group_values = {}
            for key in keys:
                value = config.get(key)
                if value is not None:
                    masked_value = value if key not in config.SENSITIVE_KEYS else '*' * 8
                    group_values[key] = masked_value
            
            if group_values:
                print(f"\n{group.upper()} Configuration:")
                for key, value in group_values.items():
                    print(f"  {key}={value}")
