#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
web="$root/web"
api="$root/backend"
state="$root/.run"
python="$api/.venv/bin/python"
mkdir -p "$state"

[[ -x "$python" && -d "$web/node_modules" ]] || { echo "Dependencies are missing. Run ./scripts/install.sh first." >&2; exit 1; }

start_service() {
  local name="$1" directory="$2"; shift 2
  local pid_file="$state/$name.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then echo "$name is already running."; return; fi
  rm -f "$pid_file"
  (cd "$directory" && nohup "$@" >"$state/$name.log" 2>"$state/$name.error.log" & echo $! >"$pid_file")
  echo "Started $name (PID $(cat "$pid_file"))."
}

assert_port_free() {
  local port="$1" name="$2" pid_file="$state/$2.pid" own=""
  [[ -f "$pid_file" ]] && own="$(cat "$pid_file")"
  local pids
  pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || ss -ltnp 2>/dev/null | awk -v p=":$port" '$4 ~ p"$" {print $NF}' | grep -o 'pid=[0-9]*' | cut -d= -f2)"
  for pid in $pids; do
    local current="$pid" ours=0 depth=0
    while [[ -n "$current" && "$current" != "0" && $depth -lt 4 ]]; do
      if [[ "$current" == "$own" ]] || ps -o args= -p "$current" 2>/dev/null | grep -q "$root"; then ours=1; break; fi
      current="$(ps -o ppid= -p "$current" 2>/dev/null | tr -d ' ')"
      depth=$((depth + 1))
    done
    if [[ $ours -eq 0 ]]; then
      echo "Port $port is already used by PID $pid: $(ps -o args= -p "$pid" 2>/dev/null). Stop it or the browser will reach the wrong server." >&2
      exit 1
    fi
  done
}

assert_port_free 8000 api
assert_port_free 5173 web
start_service api "$api" "$python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
start_service web "$web" npm run dev
echo
echo "Web UI:   http://localhost:5173"
echo "API docs: http://127.0.0.1:8000/docs"
echo "Logs:     $state"
