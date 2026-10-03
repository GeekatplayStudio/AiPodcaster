[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)

# Starts the API and the web client. If the preferred ports are taken by another
# program, the next free ports are used and every component is told about them.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$state = Join-Path $root ".run"
$web = Join-Path $root "web"
$api = Join-Path $root "backend"
$python = Join-Path $api ".venv\Scripts\python.exe"
$portsFile = Join-Path $state "ports.json"

if (-not (Test-Path $python) -or -not (Test-Path (Join-Path $web "node_modules"))) {
    throw "Dependencies are missing. Run scripts\install.ps1 first."
}
New-Item -ItemType Directory -Path $state -Force | Out-Null

function Get-RunningPid([string]$name) {
    $pidFile = Join-Path $state "$name.pid"
    if (-not (Test-Path $pidFile)) { return $null }
    $existing = (Get-Content -Raw $pidFile).Trim()
    if ($existing -and (Get-Process -Id $existing -ErrorAction SilentlyContinue)) { return $existing }
    Remove-Item -LiteralPath $pidFile -Force
    return $null
}

function Test-PortFree([int]$port) {
    # Checks IPv4 and IPv6 listeners: a server on ::1 alone still hijacks http://localhost.
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return -not $listeners
}

function Find-FreePort([int]$preferred, [int[]]$avoid = @()) {
    for ($port = $preferred; $port -lt $preferred + 200; $port++) {
        if ($avoid -contains $port) { continue }
        if (Test-PortFree $port) { return $port }
    }
    throw "No free port found between $preferred and $($preferred + 199)."
}

function Start-ServiceProcess([string]$name, [string]$file, [string[]]$arguments, [string]$workingDirectory) {
    $process = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $workingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $state "$name.log") -RedirectStandardError (Join-Path $state "$name.error.log")
    Set-Content -LiteralPath (Join-Path $state "$name.pid") -Value $process.Id -NoNewline
    Write-Host "Started $name (PID $($process.Id))."
}

$apiPid = Get-RunningPid "api"
$webPid = Get-RunningPid "web"
$previous = if (Test-Path $portsFile) { Get-Content -Raw $portsFile | ConvertFrom-Json } else { $null }

if ($apiPid -and $previous) { $chosenApi = [int]$previous.api } else {
    $chosenApi = Find-FreePort $ApiPort
    if ($chosenApi -ne $ApiPort) { Write-Host "Port $ApiPort is busy; the API will use port $chosenApi." -ForegroundColor Yellow }
}
if ($webPid -and $previous) { $chosenWeb = [int]$previous.web } else {
    $chosenWeb = Find-FreePort $WebPort @($chosenApi)
    if ($chosenWeb -ne $WebPort) { Write-Host "Port $WebPort is busy; the web client will use port $chosenWeb." -ForegroundColor Yellow }
}

$apiUrl = "http://127.0.0.1:$chosenApi"
$webUrl = "http://localhost:$chosenWeb"
# Child processes inherit these.
$env:AIPODCASTER_PUBLIC_URL = $apiUrl
$env:AIPODCASTER_API_URL = $apiUrl
$env:AIPODCASTER_ALLOWED_ORIGINS = "http://localhost:$chosenWeb,http://127.0.0.1:$chosenWeb"

if ($apiPid) { Write-Host "api is already running (PID $apiPid)." } else {
    Start-ServiceProcess "api" $python @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$chosenApi") $api
}
if ($webPid) { Write-Host "web is already running (PID $webPid)." } else {
    Start-ServiceProcess "web" "npm.cmd" @("run", "dev", "--", "--port", "$chosenWeb", "--strictPort") $web
}

@{ api = $chosenApi; web = $chosenWeb; apiUrl = $apiUrl; webUrl = $webUrl; started = (Get-Date).ToString("s") } |
    ConvertTo-Json | Set-Content -LiteralPath $portsFile -Encoding utf8

Write-Host ""
Write-Host "Web UI:   $webUrl"
Write-Host "API docs: $apiUrl/docs"
Write-Host "Logs:     $state"
Write-Host "Tip: long recordings take a while to transcribe; progress and time remaining are shown on each episode."
