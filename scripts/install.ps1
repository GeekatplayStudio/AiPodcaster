[CmdletBinding()]
param(
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$web = Join-Path $root "web"
$api = Join-Path $root "backend"
$venv = Join-Path $api ".venv"

foreach ($command in @("node", "npm", "python", "ffmpeg", "ffprobe")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "'$command' is required but was not found on PATH. See docs/user-manual.md for installation links."
    }
}

$nodeVersion = (node --version).TrimStart("v")
if ([version]$nodeVersion -lt [version]"22.12.0") { throw "Node.js 22.12 or newer is required (found $nodeVersion)." }

Push-Location $web
try { npm install --no-audit --no-fund } finally { Pop-Location }

if (-not (Test-Path $venv)) { python -m venv $venv }
$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --upgrade pip
$requirements = if ($Dev) { "requirements-dev.txt" } else { "requirements.txt" }
& $python -m pip install -r (Join-Path $api $requirements)

Write-Host ""
Write-Host "Installed. Start the application with scripts\start.ps1 and open http://localhost:5173"
Write-Host "Optional: pip install torch with CUDA for GPU transcription; the first local transcription downloads the Whisper model."
