[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$state = Join-Path $root ".run"

foreach ($name in @("web", "api")) {
    $pidFile = Join-Path $state "$name.pid"
    if (-not (Test-Path $pidFile)) { continue }
    $processId = (Get-Content -Raw $pidFile).Trim()
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        # Stop the whole tree so the Vite child of npm.cmd does not linger.
        & taskkill.exe /PID $processId /T /F | Out-Null
        Write-Host "Stopped $name (PID $processId)."
    }
    Remove-Item -LiteralPath $pidFile -Force
}
