#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
state="$root/.run"
for name in web api; do
  pid_file="$state/$name.pid"
  [[ -f "$pid_file" ]] || continue
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
    echo "Stopped $name (PID $pid)."
  fi
  rm -f "$pid_file"
done
