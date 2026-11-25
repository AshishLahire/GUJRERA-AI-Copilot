# Start GujRERA Saathi on a throw-away COPY of a database, for testing features without changing the real one.
#
#   powershell -ExecutionPolicy Bypass -File scripts\run_gujrera_test_copy.ps1              # real public data -> http://localhost:5192
#   powershell -ExecutionPolicy Bypass -File scripts\run_gujrera_test_copy.ps1 -Source demo # demo data        -> http://localhost:5193
#   add -Fresh to throw away earlier test changes and copy again
#
# Copies go to data\gujrera\test_copies\ (not committed). Uploads made while testing stay beside the copy.

param([ValidateSet("real", "demo")][string]$Source = "real", [switch]$Fresh, [switch]$NoBrowser)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$src = if ($Source -eq "real") { "data\gujrera\gujrera_public.sqlite" } else { "data\gujrera\gujrera.sqlite" }
$ports = if ($Source -eq "real") { @(8102, 5192) } else { @(8103, 5193) }
$dir = Join-Path $root "data\gujrera\test_copies\$Source"
$copy = Join-Path $dir "test.sqlite"

if (-not (Test-Path $src)) { throw "Database not found: $src" }
if ($Fresh -and (Test-Path $dir)) { Remove-Item -Recurse -Force $dir -Confirm:$false }
New-Item -ItemType Directory -Force $dir | Out-Null
if (-not (Test-Path $copy)) {
    # SQLite's backup API copies a consistent snapshot, including changes still in the WAL file.
    python -c "import sqlite3,sys; s=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" $src $copy
    Write-Host "Copied $src -> $copy" -ForegroundColor Cyan
} else {
    Write-Host "Using the existing test copy (add -Fresh to start again from the real database)" -ForegroundColor Yellow
}

# Stop an earlier test app on these ports
foreach ($port in $ports) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -Confirm:$false -ErrorAction SilentlyContinue }
}
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "GujRERA (API|app) :($($ports[0])|$($ports[1]))" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false -ErrorAction SilentlyContinue }

& (Join-Path $PSScriptRoot "run_gujrera.ps1") -ApiPort $ports[0] -UiPort $ports[1] -Db $copy -NoBrowser:$NoBrowser
Write-Host ""
Write-Host "TEST COPY ($Source data): http://localhost:$($ports[1])   (your real app on :5191 is not touched)" -ForegroundColor Green
