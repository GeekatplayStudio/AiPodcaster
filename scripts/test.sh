#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python="$root/backend/.venv/bin/python"
[[ -x "$python" ]] || python=python3
e2e=false; mutation=false
for arg in "$@"; do
  [[ "$arg" == "--e2e" ]] && e2e=true
  [[ "$arg" == "--mutation" ]] && mutation=true
done

echo "== Backend: ruff lint =="
(cd "$root/backend" && "$python" -m ruff check app tests)
echo "== Backend: pytest (unit + integration) =="
(cd "$root/backend" && "$python" -m pytest --cov=app --cov-report=term-missing)
if $mutation; then
  echo "== Backend: mutation tests =="
  (cd "$root/backend" && "$python" -m mutmut run && "$python" -m mutmut results)
fi

echo "== Web: lint, typecheck, unit tests =="
(cd "$root/web" && npm run check)
if $e2e; then
  echo "== Web: Playwright end-to-end =="
  (cd "$root/web" && npx playwright install chromium && npm run test:e2e)
fi
echo "All checks passed."
