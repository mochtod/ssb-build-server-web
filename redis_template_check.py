#!/usr/bin/env python
"""
Redis cache diagnostic for vSphere templates
"""
from vsphere_redis_cache import VSphereRedisCache, VSPHERE_DATACENTERS_KEY, VSPHERE_TEMPLATES_KEY, VSPHERE_CLUSTERS_KEY

def check_redis_templates():
    """Check and fix vSphere templates in Redis cache"""
    # Create the cache instance
    cache = VSphereRedisCache()
    
    # Get datacenters and templates
    datacenters = cache.redis_client.get(VSPHERE_DATACENTERS_KEY) or []
    templates = cache.redis_client.get(VSPHERE_TEMPLATES_KEY) or []
    clusters = cache.redis_client.get(VSPHERE_CLUSTERS_KEY) or []
    
    print("=== VSPHERE REDIS CACHE DIAGNOSTICS ===")
    print(f"Datacenters in cache: {len(datacenters)}")
    print(f"Templates in cache: {len(templates)}")
    print(f"Clusters in cache: {len(clusters)}")
    
    # Check template-datacenter associations
    templates_with_dc = [t for t in templates if 'datacenter_id' in t]
    missing_dc = [t for t in templates if 'datacenter_id' not in t]
    
    print(f"\nTemplates with datacenter association: {len(templates_with_dc)}")
    print(f"Templates missing datacenter association: {len(missing_dc)}")
    
    # Show first few datacenters
    if datacenters:
        print("\nAvailable datacenters:")
        for i, dc in enumerate(datacenters[:3]):
            print(f"  {i+1}. {dc.get('name', 'Unnamed')} (ID: {dc.get('id', 'Unknown')})")
        if len(datacenters) > 3:
            print(f"  ... and {len(datacenters) - 3} more")
    else:
        print("\nNo datacenters found in cache!")
    
    # Show template distribution
    template_by_dc = {}
    for t in templates_with_dc:
        dc_id = t.get('datacenter_id')
        if dc_id not in template_by_dc:
            template_by_dc[dc_id] = []
        template_by_dc[dc_id].append(t)
    
    if template_by_dc:
        print("\nTemplate distribution by datacenter:")
        for dc_id, dc_templates in template_by_dc.items():
            # Find datacenter name
            dc_name = "Unknown Datacenter"
            for dc in datacenters:
                if dc.get('id') == dc_id:
                    dc_name = dc.get('name', 'Unnamed')
                    break
            
            print(f"  - {dc_name} ({dc_id}): {len(dc_templates)} templates")
    
    # Add fallback templates if needed
    fix_needed = False
    if not templates:
        print("\nNo templates found in cache at all, adding fallbacks")
        fix_needed = True
    elif len(templates_with_dc) == 0:
        print("\nNo templates with datacenter association, fix required")
        fix_needed = True
    elif any(len(template_by_dc.get(dc.get('id'), [])) == 0 for dc in datacenters):
        print("\nSome datacenters have no templates, fix required")
        fix_needed = True
    
    # Fix templates if needed
    if fix_needed and datacenters:
        print("\n=== FIXING TEMPLATE ASSOCIATIONS ===")
        target_dc = datacenters[0]  # Use first datacenter as target
        print(f"Using datacenter {target_dc.get('name')} as target")
        
        # Fix missing associations
        for template in missing_dc:
            template['datacenter_id'] = target_dc.get('id')
            template['datacenter_name'] = target_dc.get('name')
            print(f"Associated template {template.get('name')} with datacenter {target_dc.get('name')}")
        
        # Make sure each datacenter has at least default templates
        for dc in datacenters:
            dc_id = dc.get('id')
            dc_name = dc.get('name')
            
            # Check if this datacenter has any templates
            dc_templates = [t for t in templates if t.get('datacenter_id') == dc_id]
            
            if not dc_templates:
                print(f"No templates for datacenter {dc_name}, adding fallbacks")
                
                # Add RHEL9 template
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
                print(f"Added fallback RHEL9 template for datacenter {dc_name}")
                
                # Add Windows template
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
                print(f"Added fallback Windows template for datacenter {dc_name}")
        
        # Save updated templates to Redis
        cache.redis_client.set(VSPHERE_TEMPLATES_KEY, templates)
        print("Updated templates saved to Redis cache")
        
        # Verify changes
        updated_templates = cache.redis_client.get(VSPHERE_TEMPLATES_KEY) or []
        updated_with_dc = [t for t in updated_templates if 'datacenter_id' in t]
        print(f"\nAfter fix: {len(updated_templates)} total templates, {len(updated_with_dc)} with datacenter association")
    
    return templates, datacenters, clusters

if __name__ == "__main__":
    check_redis_templates()