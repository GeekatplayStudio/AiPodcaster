#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
web="$root/web"
api="$root/backend"
venv="$api/.venv"
requirements="requirements.txt"
[[ "${1:-}" == "--dev" ]] && requirements="requirements-dev.txt"

for command in node npm python3 ffmpeg ffprobe; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command (see docs/user-manual.md)" >&2; exit 1; }
done

(cd "$web" && npm install --no-audit --no-fund)
[[ -d "$venv" ]] || python3 -m venv "$venv"
"$venv/bin/python" -m pip install --upgrade pip
"$venv/bin/python" -m pip install -r "$api/$requirements"
echo
echo "Installed. Start the application with ./scripts/start.sh and open http://localhost:5173"
