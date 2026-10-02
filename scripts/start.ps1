[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$state = Join-Path $root ".run"
$web = Join-Path $root "web"
$api = Join-Path $root "backend"
$python = Join-Path $api ".venv\Scripts\python.exe"

if (-not (Test-Path $python) -or -not (Test-Path (Join-Path $web "node_modules"))) {
    throw "Dependencies are missing. Run scripts\install.ps1 first."
}
New-Item -ItemType Directory -Path $state -Force | Out-Null

function Start-ServiceProcess([string]$name, [string]$file, [string[]]$arguments, [string]$workingDirectory) {
    $pidFile = Join-Path $state "$name.pid"
    if (Test-Path $pidFile) {
        $existing = (Get-Content -Raw $pidFile).Trim()
        if (Get-Process -Id $existing -ErrorAction SilentlyContinue) {
            Write-Host "$name is already running (PID $existing)."
            return
        }
        Remove-Item -LiteralPath $pidFile -Force
    }
    $process = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $workingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $state "$name.log") -RedirectStandardError (Join-Path $state "$name.error.log")
    Set-Content -LiteralPath $pidFile -Value $process.Id -NoNewline
    Write-Host "Started $name (PID $($process.Id))."
}

function Assert-PortFree([int]$port, [string]$name) {
    $pidFile = Join-Path $state "$name.pid"
    $ownPid = if (Test-Path $pidFile) { (Get-Content -Raw $pidFile).Trim() } else { "" }
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        # Walk up the parent chain: the venv python launcher spawns the real interpreter as a child.
        $current = $listener.OwningProcess
        $ours = $false
        for ($depth = 0; $depth -lt 4 -and $current; $depth++) {
            if ("$current" -eq $ownPid) { $ours = $true; break }
            $info = Get-CimInstance Win32_Process -Filter "ProcessId=$current" -ErrorAction SilentlyContinue
            if (-not $info) { break }
            if ($info.CommandLine -like "*$root*") { $ours = $true; break }
            $current = $info.ParentProcessId
        }
        if ($ours) { continue }
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        throw "Port $port ($($listener.LocalAddress)) is already used by PID $($listener.OwningProcess): $($proc.CommandLine). Stop it or the browser will reach the wrong server."
    }
}

Assert-PortFree 8000 "api"
Assert-PortFree 5173 "web"
Start-ServiceProcess "api" $python @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") $api
Start-ServiceProcess "web" "npm.cmd" @("run", "dev") $web
Write-Host ""
Write-Host "Web UI:  http://localhost:5173"
Write-Host "API docs: http://127.0.0.1:8000/docs"
Write-Host "Logs:    $state"
