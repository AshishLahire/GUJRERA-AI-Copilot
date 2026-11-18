# Start GujRERA Saathi: the API and the web app, each in its own window, on free ports.
#
#     powershell -ExecutionPolicy Bypass -File scripts\run_gujrera.ps1
#
# Uses ports 8000 (API) and 5173 (app) when they are free. If another program already
# holds one (for example another project's dev server), it says which program and moves
# to the next free port, so the app never talks to someone else's backend.
param([int]$ApiPort = 8000, [int]$UiPort = 5173, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Get-Holder([int]$Port) {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $c) { return $null }
    $p = Get-CimInstance Win32_Process -Filter "ProcessId = $($c.OwningProcess)" -ErrorAction SilentlyContinue
    if ($p) { return "$($p.Name) (PID $($c.OwningProcess)): $($p.CommandLine)" }
    return "PID $($c.OwningProcess)"
}

function Find-FreePort([int]$Port, [string]$What) {
    $holder = Get-Holder $Port
    if (-not $holder) { return $Port }
    Write-Host "Port $Port ($What) is already used by $holder" -ForegroundColor Yellow
    $p = $Port + 1
    while (Get-Holder $p) { $p++ }
    Write-Host "  -> using port $p instead" -ForegroundColor Yellow
    return $p
}

# Python: this repo's .venv if there is one, else whichever python is on PATH.
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = (Get-Command python -ErrorAction Stop).Source }
& $Python -c "import gujrera, fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "$Python cannot import gujrera/fastapi/uvicorn. Run: pip install -e .  (from $RepoRoot)"
    exit 1
}
if (-not (Test-Path (Join-Path $RepoRoot "frontend\node_modules"))) {
    Write-Host "Installing the web app's packages (first run only) ..." -ForegroundColor Cyan
    npm --prefix frontend install
}

$ApiPort = Find-FreePort $ApiPort "API"
$UiPort = Find-FreePort $UiPort "web app"
if (-not (Get-Holder 11434)) {
    Write-Host "Ollama is not running: start it (ollama serve) for free-form questions. Everything else works without it." -ForegroundColor Yellow
}

Write-Host "Starting API on http://127.0.0.1:$ApiPort ..." -ForegroundColor Cyan
Start-Process powershell -WorkingDirectory $RepoRoot -ArgumentList @(
    "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle = 'GujRERA API :$ApiPort'; & '$Python' -m uvicorn gujrera.api.dev_app:app --host 127.0.0.1 --port $ApiPort"
)

Write-Host "Starting web app on http://localhost:$UiPort ..." -ForegroundColor Cyan
Start-Process powershell -WorkingDirectory (Join-Path $RepoRoot "frontend") -ArgumentList @(
    "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle = 'GujRERA app :$UiPort'; `$env:PRAMAAN_API = 'http://127.0.0.1:$ApiPort'; `$env:PRAMAAN_UI_PORT = '$UiPort'; npm run dev"
)

# Wait for the API (first start loads the language models) and the app, then open the browser.
$ok = $false
foreach ($i in 1..90) {
    try {
        Invoke-WebRequest "http://localhost:$UiPort/api/gujrera/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
        $ok = $true; break
    } catch { Start-Sleep -Seconds 1 }
}
if ($ok) {
    Write-Host ""
    Write-Host "GujRERA Saathi is ready: http://localhost:$UiPort" -ForegroundColor Green
    Write-Host "Close the two windows titled 'GujRERA API' and 'GujRERA app' to stop it."
    if (-not $NoBrowser) { Start-Process "http://localhost:$UiPort" }
} else {
    Write-Host "Not ready after 90 s. Check the two new windows for an error message." -ForegroundColor Red
}
