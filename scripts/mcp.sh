#!/usr/bin/env bash
# Runs the AiPodcaster MCP server. Requires the API to be running (./scripts/start.sh).
# Set AIPODCASTER_API_KEY to a key generated in Settings -> API & MCP access.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python="$root/backend/.venv/bin/python"
[[ -x "$python" ]] || python=python3
ports_file="$root/.run/ports.json"
if [[ -z "${AIPODCASTER_URL:-}" && -f "$ports_file" ]]; then
  # Follow the API port chosen by start.sh (it may not be 8000 if that port was busy).
  AIPODCASTER_URL="$("$python" -c "import json,sys; print(json.load(open(sys.argv[1]))['apiUrl'])" "$ports_file")"
  export AIPODCASTER_URL
fi
exec "$python" "$root/backend/mcp_server.py" "$@"
