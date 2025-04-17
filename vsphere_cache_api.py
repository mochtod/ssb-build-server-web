"""
vSphere Cache API Endpoints

This module provides API endpoints for retrieving vSphere resources
from the Redis cache to display in the VM creation form.
"""

from flask import Blueprint, jsonify, request
import logging
import datetime
import traceback

# Import our enhanced Redis cache module
try:
    import vsphere_redis_cache_sync as vsphere_cache
    ENHANCED_CACHE_AVAILABLE = True
except ImportError:
    ENHANCED_CACHE_AVAILABLE = False
    logging.warning("Enhanced vSphere Redis cache module not available, falling back to standard cache")

# Import the standard cache functions
from app import get_cache, set_cache

# Create blueprint
vsphere_cache_api = Blueprint('vsphere_cache_api', __name__)

# Configure logging
logger = logging.getLogger(__name__)

@vsphere_cache_api.route('/api/vsphere-cache-status')
def api_vsphere_cache_status():
    """Get the current status of the vSphere cache."""
    try:
        if ENHANCED_CACHE_AVAILABLE:
            # Use enhanced cache module to get detailed stats
            cache_stats = vsphere_cache.get_cache_stats()
            sync_status = vsphere_cache.get_sync_status()
            
            # Check if we have resources in cache
            resources_available = False
            resource_counts = {}
            
            for resource_type in ['datacenters', 'resource_pools', 'datastores', 'templates', 'networks']:
                resource_count = cache_stats.get('resources', {}).get(resource_type, {}).get('count', 0)
                resource_counts[resource_type] = resource_count
                if resource_count > 0:
                    resources_available = True
            
            # Get last update time
            last_update = None
            if sync_status and 'timestamp' in sync_status:
                last_update = sync_status['timestamp']
            elif cache_stats and 'timestamp' in cache_stats:
                last_update = cache_stats['timestamp']
            
            return jsonify({
                'status': 'success' if resources_available else 'empty',
                'enhanced_cache': True,
                'resources_available': resources_available,
                'resource_counts': resource_counts,
                'last_update': last_update,
                'redis_memory_usage': cache_stats.get('redis', {}).get('used_memory_human', 'unknown')
            })
        else:
            # Fallback to standard cache
            vsphere_data = get_cache('vsphere_inventory')
            resources_available = bool(vsphere_data and 
                                       any(len(vsphere_data.get(res_type, [])) > 0 
                                          for res_type in ['datacenters', 'resource_pools', 'datastores', 'templates', 'networks']))
            
            # Get resource counts
            resource_counts = {
                resource_type: len(vsphere_data.get(resource_type, [])) if vsphere_data else 0
                for resource_type in ['datacenters', 'resource_pools', 'datastores', 'templates', 'networks']
            }
            
            # Get last update timestamp
            last_update = vsphere_data.get('cached_at', vsphere_data.get('last_update', datetime.datetime.now().isoformat())) if vsphere_data else None
            
            return jsonify({
                'status': 'success' if resources_available else 'empty',
                'enhanced_cache': False,
                'resources_available': resources_available,
                'resource_counts': resource_counts,
                'last_update': last_update
            })
            
    except Exception as e:
        logger.error(f"Error checking vSphere cache status: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f"Error checking cache status: {str(e)}",
            'traceback': traceback.format_exc()
        }), 500

@vsphere_cache_api.route('/api/vsphere-resource-pools')
def api_vsphere_resource_pools():
    """Get resource pools for a datacenter from cache."""
    try:
        datacenter = request.args.get('datacenter')
        if not datacenter:
            return jsonify({'status': 'error', 'message': 'Datacenter parameter required'}), 400
        
        if ENHANCED_CACHE_AVAILABLE:
            # Use enhanced cache to get resource pools
            resource_pools = vsphere_cache.get_cached_resource('resource_pools')
            
            # Filter resource pools by datacenter if needed
            # Note: This depends on how your data is structured - adjust as needed
            if resource_pools and isinstance(resource_pools[0], dict) and 'datacenter' in resource_pools[0]:
                resource_pools = [rp for rp in resource_pools if rp.get('datacenter') == datacenter]
            
            return jsonify({
                'status': 'success',
                'resource_pools': resource_pools,
                'count': len(resource_pools)
            })
        else:
            # Fallback to standard cache
            vsphere_data = get_cache('vsphere_inventory')
            if not vsphere_data:
                return jsonify({'status': 'error', 'message': 'No vSphere data in cache'}), 404
            
            # Get resource pools from inventory
            resource_pools = vsphere_data.get('resource_pools', [])
            
            # If we have datacenter-specific resources, use those instead
            if 'datacenter_resources' in vsphere_data and datacenter in vsphere_data['datacenter_resources']:
                dc_resource_pools = vsphere_data['datacenter_resources'][datacenter].get('resource_pools')
                if dc_resource_pools:
                    resource_pools = dc_resource_pools
            
            # Convert to list of dicts if they're just strings
            if resource_pools and isinstance(resource_pools[0], str):
                resource_pools = [{'name': rp, 'id': rp} for rp in resource_pools]
            
            return jsonify({
                'status': 'success',
                'resource_pools': resource_pools,
                'count': len(resource_pools)
            })
            
    except Exception as e:
        logger.error(f"Error getting resource pools from cache: {e}", exc_info=True)
        return jsonify({
            'status': 'error', 
            'message': f"Error getting resource pools: {str(e)}"
        }), 500

@vsphere_cache_api.route('/api/vsphere-datastores')
def api_vsphere_datastores():
    """Get datastores for a datacenter and resource pool from cache."""
    try:
        datacenter = request.args.get('datacenter')
        resource_pool = request.args.get('resource_pool')
        
        if not datacenter or not resource_pool:
            return jsonify({'status': 'error', 'message': 'Datacenter and resource_pool parameters required'}), 400
        
        if ENHANCED_CACHE_AVAILABLE:
            # Use enhanced cache to get datastores
            datastores = vsphere_cache.get_cached_resource('datastores')
            
            # Filter datastores by datacenter and resource pool if needed
            # This depends on how your data is structured - adjust as needed
            if datastores and isinstance(datastores[0], dict):
                if 'datacenter' in datastores[0]:
                    datastores = [ds for ds in datastores if ds.get('datacenter') == datacenter]
                if 'resource_pool' in datastores[0]:
                    datastores = [ds for ds in datastores if ds.get('resource_pool') == resource_pool]
            
            return jsonify({
                'status': 'success',
                'datastores': datastores,
                'count': len(datastores)
            })
        else:
            # Fallback to standard cache
            vsphere_data = get_cache('vsphere_inventory')
            if not vsphere_data:
                return jsonify({'status': 'error', 'message': 'No vSphere data in cache'}), 404
            
            # Get datastores from inventory
            datastores = vsphere_data.get('datastores', [])
            
            # If we have datacenter-specific resources, use those instead
            if 'datacenter_resources' in vsphere_data and datacenter in vsphere_data['datacenter_resources']:
                dc_datastores = vsphere_data['datacenter_resources'][datacenter].get('datastores')
                if dc_datastores:
                    datastores = dc_datastores
                    
                # Further filter by resource pool if available
                if resource_pool in vsphere_data['datacenter_resources'][datacenter].get('resource_pool_resources', {}):
                    rp_datastores = vsphere_data['datacenter_resources'][datacenter]['resource_pool_resources'][resource_pool].get('datastores')
                    if rp_datastores:
                        datastores = rp_datastores
            
            # Convert to list of dicts if they're just strings
            if datastores and isinstance(datastores[0], str):
                datastores = [{'name': ds, 'id': ds} for ds in datastores]
            
            return jsonify({
                'status': 'success',
                'datastores': datastores,
                'count': len(datastores)
            })
            
    except Exception as e:
        logger.error(f"Error getting datastores from cache: {e}", exc_info=True)
        return jsonify({
            'status': 'error', 
            'message': f"Error getting datastores: {str(e)}"
        }), 500

@vsphere_cache_api.route('/api/vsphere-templates')
def api_vsphere_templates():
    """Get templates for a datacenter and resource pool from cache."""
    try:
        datacenter = request.args.get('datacenter')
        resource_pool = request.args.get('resource_pool')
        
        if not datacenter or not resource_pool:
            return jsonify({'status': 'error', 'message': 'Datacenter and resource_pool parameters required'}), 400
        
        if ENHANCED_CACHE_AVAILABLE:
            # Use enhanced cache to get templates
            templates = vsphere_cache.get_cached_resource('templates')
            
            # Filter templates by datacenter and resource pool if needed
            if templates and isinstance(templates[0], dict):
                if 'datacenter' in templates[0]:
                    templates = [tpl for tpl in templates if tpl.get('datacenter') == datacenter]
                if 'resource_pool' in templates[0]:
                    templates = [tpl for tpl in templates if tpl.get('resource_pool') == resource_pool]
            
            return jsonify({
                'status': 'success',
                'templates': templates,
                'count': len(templates)
            })
        else:
            # Fallback to standard cache
            vsphere_data = get_cache('vsphere_inventory')
            if not vsphere_data:
                return jsonify({'status': 'error', 'message': 'No vSphere data in cache'}), 404
            
            # Get templates from inventory
            templates = vsphere_data.get('templates', [])
            
            # If we have datacenter-specific resources, use those instead
            if 'datacenter_resources' in vsphere_data and datacenter in vsphere_data['datacenter_resources']:
                dc_templates = vsphere_data['datacenter_resources'][datacenter].get('templates')
                if dc_templates:
                    templates = dc_templates
                    
                # Further filter by resource pool if available
                if resource_pool in vsphere_data['datacenter_resources'][datacenter].get('resource_pool_resources', {}):
                    rp_templates = vsphere_data['datacenter_resources'][datacenter]['resource_pool_resources'][resource_pool].get('templates')
                    if rp_templates:
                        templates = rp_templates
            
            # Convert to list of dicts if they're just strings
            if templates and isinstance(templates[0], str):
                templates = [{'name': tpl, 'id': tpl} for tpl in templates]
            
            return jsonify({
                'status': 'success',
                'templates': templates,
                'count': len(templates)
            })
            
    except Exception as e:
        logger.error(f"Error getting templates from cache: {e}", exc_info=True)
        return jsonify({
            'status': 'error', 
            'message': f"Error getting templates: {str(e)}"
        }), 500

@vsphere_cache_api.route('/api/vsphere-networks')
def api_vsphere_networks():
    """Get networks for a datacenter and resource pool from cache."""
    try:
        datacenter = request.args.get('datacenter')
        resource_pool = request.args.get('resource_pool')
        
        if not datacenter or not resource_pool:
            return jsonify({'status': 'error', 'message': 'Datacenter and resource_pool parameters required'}), 400
        
        if ENHANCED_CACHE_AVAILABLE:
            # Use enhanced cache to get networks
            networks = vsphere_cache.get_cached_resource('networks')
            
            # Filter networks by datacenter and resource pool if needed
            if networks and isinstance(networks[0], dict):
                if 'datacenter' in networks[0]:
                    networks = [net for net in networks if net.get('datacenter') == datacenter]
                if 'resource_pool' in networks[0]:
                    networks = [net for net in networks if net.get('resource_pool') == resource_pool]
            
            return jsonify({
                'status': 'success',
                'networks': networks,
                'count': len(networks)
            })
        else:
            # Fallback to standard cache
            vsphere_data = get_cache('vsphere_inventory')
            if not vsphere_data:
                return jsonify({'status': 'error', 'message': 'No vSphere data in cache'}), 404
            
            # Get networks from inventory
            networks = vsphere_data.get('networks', [])
            
            # If we have datacenter-specific resources, use those instead
            if 'datacenter_resources' in vsphere_data and datacenter in vsphere_data['datacenter_resources']:
                dc_networks = vsphere_data['datacenter_resources'][datacenter].get('networks')
                if dc_networks:
                    networks = dc_networks
                    
                # Further filter by resource pool if available
                if resource_pool in vsphere_data['datacenter_resources'][datacenter].get('resource_pool_resources', {}):
                    rp_networks = vsphere_data['datacenter_resources'][datacenter]['resource_pool_resources'][resource_pool].get('networks')
                    if rp_networks:
                        networks = rp_networks
            
            # Convert to list of dicts if they're just strings
            if networks and isinstance(networks[0], str):
                networks = [{'name': net, 'id': net} for net in networks]
            
            return jsonify({
                'status': 'success',
                'networks': networks,
                'count': len(networks)
            })
            
    except Exception as e:
        logger.error(f"Error getting networks from cache: {e}", exc_info=True)
        return jsonify({
            'status': 'error', 
            'message': f"Error getting networks: {str(e)}"
        }), 500
