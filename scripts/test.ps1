[CmdletBinding()]
param(
    [switch]$E2E,
    [switch]$Mutation
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

Write-Host "== Backend: ruff lint =="
Push-Location (Join-Path $root "backend")
try {
    & $python -m ruff check app tests
    Write-Host "== Backend: pytest (unit + integration) =="
    & $python -m pytest --cov=app --cov-report=term-missing
    if ($Mutation) {
        Write-Host "== Backend: mutation tests (mutmut) =="
        & $python -m mutmut run
        & $python -m mutmut results
    }
} finally { Pop-Location }

Write-Host "== Web: lint, typecheck, unit tests =="
Push-Location (Join-Path $root "web")
try {
    npm run check
    if ($E2E) {
        Write-Host "== Web: Playwright end-to-end =="
        npx playwright install chromium
        npm run test:e2e
    }
} finally { Pop-Location }
Write-Host "All checks passed."
