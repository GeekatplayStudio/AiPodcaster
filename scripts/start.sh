#!/usr/bin/env bash
# Starts the API and the web client. If the preferred ports are taken by another
# program, the next free ports are used and every component is told about them.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
web="$root/web"
api="$root/backend"
state="$root/.run"
python="$api/.venv/bin/python"
ports_file="$state/ports.json"
api_port="${1:-8000}"
web_port="${2:-5173}"
mkdir -p "$state"

[[ -x "$python" && -d "$web/node_modules" ]] || { echo "Dependencies are missing. Run ./scripts/install.sh first." >&2; exit 1; }

running_pid() {
  local pid_file="$state/$1.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then cat "$pid_file"; else rm -f "$pid_file"; fi
}

port_free() {
  # Try binding on IPv4 and IPv6 loopback: a server on ::1 alone still hijacks http://localhost.
  "$python" - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
    try:
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.bind((host, port))
    except OSError as error:
        if family == socket.AF_INET6 and error.errno in (99, 97, 49):  # IPv6 unavailable
            continue
        sys.exit(1)
sys.exit(0)
PY
}

find_free_port() {
  local port="$1" avoid="${2:-}"
  for ((i = 0; i < 200; i++)); do
    if [[ "$port" != "$avoid" ]] && port_free "$port"; then echo "$port"; return; fi
    port=$((port + 1))
  done
  echo "No free port found near $1" >&2; exit 1
}

json_value() { "$python" -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$ports_file" "$1" 2>/dev/null || true; }

api_pid="$(running_pid api)"
web_pid="$(running_pid web)"
if [[ -n "$api_pid" && -f "$ports_file" ]]; then chosen_api="$(json_value api)"; else
  chosen_api="$(find_free_port "$api_port")"
  [[ "$chosen_api" == "$api_port" ]] || echo "Port $api_port is busy; the API will use port $chosen_api."
fi
if [[ -n "$web_pid" && -f "$ports_file" ]]; then chosen_web="$(json_value web)"; else
  chosen_web="$(find_free_port "$web_port" "$chosen_api")"
  [[ "$chosen_web" == "$web_port" ]] || echo "Port $web_port is busy; the web client will use port $chosen_web."
fi

api_url="http://127.0.0.1:$chosen_api"
web_url="http://localhost:$chosen_web"
export AIPODCASTER_PUBLIC_URL="$api_url" AIPODCASTER_API_URL="$api_url"
export AIPODCASTER_ALLOWED_ORIGINS="http://localhost:$chosen_web,http://127.0.0.1:$chosen_web"

start_service() {
  local name="$1" directory="$2"; shift 2
  (cd "$directory" && nohup "$@" >"$state/$name.log" 2>"$state/$name.error.log" & echo $! >"$state/$name.pid")
  echo "Started $name (PID $(cat "$state/$name.pid"))."
}

if [[ -n "$api_pid" ]]; then echo "api is already running (PID $api_pid)."; else
  start_service api "$api" "$python" -m uvicorn app.main:app --host 127.0.0.1 --port "$chosen_api"
fi
if [[ -n "$web_pid" ]]; then echo "web is already running (PID $web_pid)."; else
  start_service web "$web" npm run dev -- --port "$chosen_web" --strictPort
fi

printf '{"api": %s, "web": %s, "apiUrl": "%s", "webUrl": "%s"}\n' "$chosen_api" "$chosen_web" "$api_url" "$web_url" >"$ports_file"
echo
echo "Web UI:   $web_url"
echo "API docs: $api_url/docs"
echo "Logs:     $state"
echo "Tip: long recordings take a while to transcribe; progress and time remaining are shown on each episode."
