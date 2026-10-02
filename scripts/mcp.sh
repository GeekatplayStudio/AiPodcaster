#!/usr/bin/env bash
# Runs the AiPodcaster MCP server. Requires the API to be running (./scripts/start.sh).
# Set AIPODCASTER_API_KEY to a key generated in Settings -> API & MCP access.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python="$root/backend/.venv/bin/python"
[[ -x "$python" ]] || python=python3
exec "$python" "$root/backend/mcp_server.py" "$@"
