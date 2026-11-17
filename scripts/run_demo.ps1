# Launch the Pramaan FastAPI backend (port 8000) and Vite React frontend (port 5173) in separate windows.
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Error "Virtual environment not found at $PythonExe. See README.md for setup instructions."
    exit 1
}

Write-Host "Starting FastAPI backend on http://localhost:8000 ..." -ForegroundColor Cyan
Start-Process powershell -WorkingDirectory $RepoRoot -ArgumentList @(
    "-NoExit",
    "-Command",
    "& '$PythonExe' -m uvicorn factcheck.api.app:app --host 127.0.0.1 --port 8000"
)

$FrontendDir = Join-Path $RepoRoot "frontend"
Write-Host "Starting Vite React frontend on http://localhost:5173 ..." -ForegroundColor Cyan
Start-Process powershell -WorkingDirectory $FrontendDir -ArgumentList @(
    "-NoExit",
    "-Command",
    "npm run dev"
)

Write-Host ""
Write-Host "Pramaan Demo started:" -ForegroundColor Green
Write-Host "  Backend API : http://localhost:8000/api/health"
Write-Host "  Frontend UI : http://localhost:5173"
