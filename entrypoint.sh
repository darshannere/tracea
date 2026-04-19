#!/bin/bash
set -e

# Create /data directory if it doesn't exist
mkdir -p /data
chmod 777 /data

# Generate API key if not exists
API_KEY_FILE="/data/api_key.txt"
if [ ! -f "$API_KEY_FILE" ]; then
    API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(16))")
    echo "$API_KEY" > "$API_KEY_FILE"
    chmod 600 "$API_KEY_FILE"
    echo "TRACEA_API_KEY=$API_KEY"
else
    API_KEY=$(cat "$API_KEY_FILE")
    echo "TRACEA_API_KEY=$API_KEY"
fi

# Warn if running as root
if [ "$(id -u)" = "0" ]; then
    echo "WARNING: Running as root. Use a non-root user in production."
fi

# Run the server
exec uvicorn tracea.server.main:app --host 0.0.0.0 --port 8080 --workers 1
