#!/bin/bash
# Script to fix Redis connection issues in Docker containers

echo "==== Redis Connection Fix Script ===="
echo "This script will:
1. Update environment variables in both web and vsphere-sync containers 
2. Restart the containers to apply changes"

# Fix the web container
echo "Fixing web container Redis connection..."

# Set proper Redis connection environment variables
docker exec ssb-build-server-web-1-web-1 bash -c 'echo "export REDIS_HOST=redis" >> /etc/environment'
docker exec ssb-build-server-web-1-web-1 bash -c 'echo "export REDIS_PORT=6379" >> /etc/environment'

# Fix the vsphere-sync container
echo "Fixing vsphere-sync container Redis connection..."

# Set proper Redis connection environment variables
docker exec ssb-build-server-web-1-vsphere-sync-1 bash -c 'echo "export REDIS_HOST=redis" >> /etc/environment'
docker exec ssb-build-server-web-1-vsphere-sync-1 bash -c 'echo "export REDIS_PORT=6379" >> /etc/environment'

# Restart containers to apply changes
echo "Restarting containers to apply changes..."
docker restart ssb-build-server-web-1-web-1
docker restart ssb-build-server-web-1-vsphere-sync-1

echo "Done! Redis connections should now work correctly."