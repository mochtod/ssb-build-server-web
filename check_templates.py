#!/usr/bin/env python
"""
Quick check for vSphere template datacenter associations in Redis
"""
from vsphere_redis_cache import VSphereRedisCache, VSPHERE_TEMPLATES_KEY, VSPHERE_DATACENTERS_KEY

# Initialize cache connection
cache = VSphereRedisCache()

# Get templates and datacenters
templates = cache.redis_client.get(VSPHERE_TEMPLATES_KEY) or []
datacenters = cache.redis_client.get(VSPHERE_DATACENTERS_KEY) or []

# Count templates with datacenter associations
templates_with_dc = [t for t in templates if "datacenter_id" in t]

# Print summary
print(f"Redis connection: {cache.redis_client.ping()}")
print(f"Total templates: {len(templates)}")
print(f"Templates with datacenter association: {len(templates_with_dc)}/{len(templates)}")
print(f"Total datacenters: {len(datacenters)}")

# Print template distribution by datacenter
templates_by_dc = {}
for t in templates_with_dc:
    dc_id = t.get("datacenter_id")
    if dc_id not in templates_by_dc:
        templates_by_dc[dc_id] = []
    templates_by_dc[dc_id].append(t)

print("\nTemplate distribution by datacenter:")
for dc in datacenters:
    dc_id = dc.get("id")
    dc_name = dc.get("name")
    templates_count = len(templates_by_dc.get(dc_id, []))
    print(f"- {dc_name} ({dc_id}): {templates_count} templates")