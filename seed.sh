#!/usr/bin/env bash
# XP-Arc seed.sh – seed a URL into the running daemon.
#
# Usage:   ./seed.sh <url>
#
# The script POSTs JSON { "url": "<url>" } to the daemon’s /api/seed endpoint on $XP_ARC_PORT (default 8089).
#
# Successful response (HTTP 200) returns JSON with the created entity ID, status, and payload_hash.
# Failure (e.g., daemon not running, invalid URL) yields a non‑200 status and the response body.
#
# Example:
#   ./seed.sh https://example.com
#   # => {"entity_id":42,"status":"raw","payload_hash":"..."}
#
# For background execution you can pipe the output to jq for pretty printing.
#
# Environment overrides:
#   XP_ARC_PORT – HTTP port of the running daemon (default 8089).
#
# Note: The daemon must be started (via ./start.sh or ./run_persistent.py) before using this script.

PORT="${XP_ARC_PORT:-8089}"
if [ -z "$1" ]; then
    echo "Usage: $0 <url>"
    echo "  Seeds a URL into the running XP‑Arc pipeline"
    exit 1
fi
URL="$1"
# Send POST request and pretty‑print JSON response
curl -s -X POST "http://localhost:${PORT}/api/seed" \
    -H "Content-Type: application/json" \
    -d "{\"url\": \"${URL}\"}" | python3 -m json.tool
