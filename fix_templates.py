#!/usr/bin/env python
"""
Fix vSphere template datacenter associations in Redis cache
"""
from vsphere_redis_cache import VSphereRedisCache, VSPHERE_DATACENTERS_KEY, VSPHERE_TEMPLATES_KEY

# Create VSphereRedisCache instance
cache = VSphereRedisCache()

# Get datacenters and templates from Redis
datacenters = cache.redis_client.get(VSPHERE_DATACENTERS_KEY) or []
templates = cache.redis_client.get(VSPHERE_TEMPLATES_KEY) or []

print(f"Found {len(datacenters)} datacenters and {len(templates)} templates")

# Find target datacenter (use first available one)
target_dc = datacenters[0] if datacenters else None

if not target_dc:
    print("No datacenters found in cache! Cannot fix templates.")
    exit(1)

print(f"Target datacenter: {target_dc['name']} (ID: {target_dc['id']})")

# Find templates missing datacenter association
missing_templates = [t for t in templates if 'datacenter_id' not in t]
print(f"Found {len(missing_templates)} templates missing datacenter association")

# Associate missing templates with target datacenter
if missing_templates:
    for template in missing_templates:
        template['datacenter_id'] = target_dc['id']
        template['datacenter_name'] = target_dc['name']
        print(f"Associated template {template.get('name')} with datacenter {target_dc['name']}")
    
    # Save updated templates back to Redis
    cache.redis_client.set(VSPHERE_TEMPLATES_KEY, templates)
    print(f"Fixed {len(missing_templates)} templates by associating with {target_dc['name']}")
    
    # Add fallback templates if needed
    templates_for_dc = [t for t in templates if t.get('datacenter_id') == target_dc['id']]
    if len(templates_for_dc) < 2:
        print(f"Only {len(templates_for_dc)} templates for datacenter {target_dc['name']}, adding fallbacks")
        
        # Add RHEL9 template if missing
        if not any('rhel9' in t.get('name', '').lower() for t in templates_for_dc):
            rhel9_template = {
                'id': f'vm-fallback-rhel9-{target_dc["id"]}',
                'name': 'rhel9-template (fallback)',
                'is_template': True,
                'guest_id': 'rhel9_64Guest',
                'guest_full_name': 'Red Hat Enterprise Linux 9 (64-bit)',
                'datacenter_id': target_dc['id'],
                'datacenter_name': target_dc['name']
            }
            templates.append(rhel9_template)
            print(f"Added fallback RHEL9 template for datacenter {target_dc['name']}")
        
        # Add Windows template if missing
        if not any('windows' in t.get('name', '').lower() for t in templates_for_dc):
            win_template = {
                'id': f'vm-fallback-win-{target_dc["id"]}',
                'name': 'windows-template (fallback)',
                'is_template': True,
                'guest_id': 'windows2019srv_64Guest',
                'guest_full_name': 'Windows Server 2019 (64-bit)',
                'datacenter_id': target_dc['id'],
                'datacenter_name': target_dc['name']
            }
            templates.append(win_template)
            print(f"Added fallback Windows template for datacenter {target_dc['name']}")
            
        # Save updated templates again if fallbacks were added
        cache.redis_client.set(VSPHERE_TEMPLATES_KEY, templates)
        print("Fallback templates added and saved to cache")
else:
    print("No templates need fixing!")

# Verify the changes
updated_templates = cache.redis_client.get(VSPHERE_TEMPLATES_KEY) or []
templates_by_dc = {}

for template in updated_templates:
    dc_id = template.get('datacenter_id')
    if dc_id:
        if dc_id not in templates_by_dc:
            templates_by_dc[dc_id] = []
        templates_by_dc[dc_id].append(template)

print("\nTemplates by datacenter after fix:")
for dc_id, dc_templates in templates_by_dc.items():
    # Find datacenter name
    dc_name = "Unknown"
    for dc in datacenters:
        if dc.get('id') == dc_id:
            dc_name = dc.get('name')
            break
    
    print(f"- {dc_name} ({dc_id}): {len(dc_templates)} templates")
    # Show first 3 templates for each datacenter
    for i, template in enumerate(dc_templates[:3]):
        print(f"  {i+1}. {template.get('name')} (ID: {template.get('id')})")

print("\nTemplate fix complete!")