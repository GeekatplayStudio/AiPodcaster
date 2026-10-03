[CmdletBinding()]
param(
    [switch]$Http,
    [int]$Port = 8765,
    [switch]$PrintConfig
)

# Runs the AiPodcaster MCP server. Requires the API to be running (scripts\start.ps1).
# Set AIPODCASTER_API_KEY to a key generated in Settings -> API & MCP access.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
$server = Join-Path $root "backend\mcp_server.py"
$portsFile = Join-Path $root ".run\ports.json"
if (-not $env:AIPODCASTER_URL -and (Test-Path $portsFile)) {
    # Follow the API port chosen by start.ps1 (it may not be 8000 if that port was busy).
    $env:AIPODCASTER_URL = (Get-Content -Raw $portsFile | ConvertFrom-Json).apiUrl
}

$arguments = @($server)
if ($PrintConfig) { $arguments += "--print-config" }
elseif ($Http) { $arguments += @("--http", "--port", "$Port") }
& $python @arguments
