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

$arguments = @($server)
if ($PrintConfig) { $arguments += "--print-config" }
elseif ($Http) { $arguments += @("--http", "--port", "$Port") }
& $python @arguments
