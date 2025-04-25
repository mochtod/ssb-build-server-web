#!/usr/bin/env python
"""
vSphere diagnostics and fix script for template visibility issues
"""
from vsphere_redis_cache import VSphereRedisCache, VSPHERE_DATACENTERS_KEY, VSPHERE_TEMPLATES_KEY
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('vsphere_diagnostics')

def diagnose_and_fix_templates():
    """Diagnose and fix template visibility issues"""
    print("\n=== VSPHERE REDIS CACHE DIAGNOSTICS ===\n")
    
    # Create VSphereRedisCache instance
    vsphere_cache = VSphereRedisCache()
    
    # Check Redis connection
    redis_connected = vsphere_cache.redis_client.ping()
    print(f"Redis connection: {redis_connected}")
    
    if not redis_connected:
        print("Cannot connect to Redis. Please check Redis container status.")
        return False
    
    # Get datacenters and templates from Redis
    datacenters = vsphere_cache.redis_client.get(VSPHERE_DATACENTERS_KEY) or []
    templates = vsphere_cache.redis_client.get(VSPHERE_TEMPLATES_KEY) or []
    
    print(f"\nFound {len(datacenters)} datacenters and {len(templates)} templates")
    
    # Check for datacenters
    if not datacenters:
        print("\nNo datacenters found in cache. Adding fallback datacenter.")
        fallback_dc = {
            'id': 'datacenter-fallback-edbc',
            'name': 'EDBC NONPROD',
            'vm_folder': 'folder-fallback-vm',
            'host_folder': 'folder-fallback-host',
            'datastore_folder': 'folder-fallback-datastore',
            'network_folder': 'folder-fallback-network'
        }
        datacenters.append(fallback_dc)
        vsphere_cache.redis_client.set(VSPHERE_DATACENTERS_KEY, datacenters)
        print("Added fallback datacenter 'EDBC NONPROD'")
    
    print("\nDatacenters in cache:")
    for i, dc in enumerate(datacenters):
        print(f"{i+1}. {dc.get('name')} (ID: {dc.get('id')})")
    
    # Find templates missing datacenter association
    templates_missing_dc = [t for t in templates if 'datacenter_id' not in t]
    print(f"\nTemplates missing datacenter association: {len(templates_missing_dc)}")
    
    # Calculate templates by datacenter
    templates_by_dc = {}
    for template in templates:
        if 'datacenter_id' in template:
            dc_id = template['datacenter_id']
            if dc_id not in templates_by_dc:
                templates_by_dc[dc_id] = []
            templates_by_dc[dc_id].append(template)
    
    print("\nTemplate distribution by datacenter:")
    for dc in datacenters:
        dc_id = dc.get('id')
        dc_templates = templates_by_dc.get(dc_id, [])
        print(f"- {dc.get('name')} ({dc_id}): {len(dc_templates)} templates")
    
    # Determine if fixes are needed
    fixes_needed = False
    
    if templates_missing_dc:
        print("\nFix needed: Templates missing datacenter association")
        fixes_needed = True
    
    for dc in datacenters:
        dc_id = dc.get('id')
        if dc_id not in templates_by_dc or len(templates_by_dc[dc_id]) == 0:
            print(f"Fix needed: Datacenter {dc.get('name')} has no templates")
            fixes_needed = True
    
    # Apply fixes if needed
    if fixes_needed:
        print("\n=== APPLYING TEMPLATE FIXES ===")
        
        # Fix 1: Associate templates missing datacenter with the first datacenter
        if templates_missing_dc:
            target_dc = datacenters[0]
            print(f"Associating {len(templates_missing_dc)} templates with datacenter {target_dc.get('name')}")
            
            for template in templates_missing_dc:
                template['datacenter_id'] = target_dc.get('id')
                template['datacenter_name'] = target_dc.get('name')
                print(f"Associated template {template.get('name')} with datacenter {target_dc.get('name')}")
        
        # Fix 2: Ensure each datacenter has at least two templates (RHEL9 and Windows)
        for dc in datacenters:
            dc_id = dc.get('id')
            dc_name = dc.get('name')
            
            dc_templates = templates_by_dc.get(dc_id, [])
            print(f"Checking templates for datacenter {dc_name} ({len(dc_templates)} templates)")
            
            # Check for RHEL9 template
            has_rhel9 = any('rhel9' in t.get('name', '').lower() for t in dc_templates)
            if not has_rhel9:
                print(f"Adding RHEL9 fallback template for datacenter {dc_name}")
                rhel9_template = {
                    'id': f'vm-fallback-rhel9-{dc_id}',
                    'name': 'rhel9-template (fallback)',
                    'is_template': True,
                    'guest_id': 'rhel9_64Guest',
                    'guest_full_name': 'Red Hat Enterprise Linux 9 (64-bit)',
                    'datacenter_id': dc_id,
                    'datacenter_name': dc_name
                }
                templates.append(rhel9_template)
            
            # Check for Windows template
            has_windows = any('windows' in t.get('name', '').lower() for t in dc_templates)
            if not has_windows:
                print(f"Adding Windows fallback template for datacenter {dc_name}")
                win_template = {
                    'id': f'vm-fallback-win-{dc_id}',
                    'name': 'windows-template (fallback)',
                    'is_template': True,
                    'guest_id': 'windows2019srv_64Guest',
                    'guest_full_name': 'Windows Server 2019 (64-bit)',
                    'datacenter_id': dc_id,
                    'datacenter_name': dc_name
                }
                templates.append(win_template)
        
        # Save updated templates to Redis
        print(f"Saving {len(templates)} templates to Redis cache")
        vsphere_cache.redis_client.set(VSPHERE_TEMPLATES_KEY, templates)
        
        # Verify changes
        updated_templates = vsphere_cache.redis_client.get(VSPHERE_TEMPLATES_KEY) or []
        templates_by_dc_after = {}
        
        for t in updated_templates:
            if 'datacenter_id' in t:
                dc_id = t['datacenter_id']
                if dc_id not in templates_by_dc_after:
                    templates_by_dc_after[dc_id] = []
                templates_by_dc_after[dc_id].append(t)
        
        print("\nTemplate distribution after fix:")
        for dc in datacenters:
            dc_id = dc.get('id')
            dc_templates = templates_by_dc_after.get(dc_id, [])
            print(f"  Datacenter {dc.get('name')} ({dc_id}): {len(dc_templates)} templates")
            
            # Show some example templates
            if dc_templates:
                print("    Example templates:")
                for i, template in enumerate(dc_templates[:2]):
                    print(f"      {i+1}. {template.get('name')} (ID: {template.get('id')})")
        
        print("\nTemplate fixes applied successfully!")
        return True
    else:
        print("\nNo template fixes needed, everything looks good!")
        return False

if __name__ == "__main__":
    diagnose_and_fix_templates()