#!/bin/bash
set -e

# Create /data directory if it doesn't exist
mkdir -p /data
chmod 777 /data

# Warn if running as root
if [ "$(id -u)" = "0" ]; then
    echo "WARNING: Running as root. Use a non-root user in production."
fi

# Run the server
exec uvicorn tracea.server.main:app --host 0.0.0.0 --port 8080 --workers 1
