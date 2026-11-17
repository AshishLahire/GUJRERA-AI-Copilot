$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$outDir = "c:\Users\ashis\Downloads\fujitsu final(1)\fujitsu\docs\screenshots\redesign"
$tempProfile = "$env:TEMP\edge_profile_shots"

if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Force -Path $outDir
}

$targets = @(
    @{ name = "start_state_light.png"; url = "http://localhost:5173/"; budget = 3000 },
    @{ name = "start_state_dark.png"; url = "http://localhost:5173/?theme=dark"; budget = 3000 },
    @{ name = "red_result_FN-TG-01595_light.png"; url = "http://localhost:5173/?sample=FN-TG-01595"; budget = 6000 },
    @{ name = "red_result_FN-TG-01595_dark.png"; url = "http://localhost:5173/?sample=FN-TG-01595&theme=dark"; budget = 6000 },
    @{ name = "amber_result_FN-TG-01746_light.png"; url = "http://localhost:5173/?sample=FN-TG-01746"; budget = 6000 },
    @{ name = "amber_result_FN-TG-01746_dark.png"; url = "http://localhost:5173/?sample=FN-TG-01746&theme=dark"; budget = 6000 },
    @{ name = "green_result_CBSE_55_light.png"; url = "http://localhost:5173/?sample=OFF-4A2E01CE80__screenshot"; budget = 6000 },
    @{ name = "green_result_CBSE_55_dark.png"; url = "http://localhost:5173/?sample=OFF-4A2E01CE80__screenshot&theme=dark"; budget = 6000 },
    @{ name = "narratives_light.png"; url = "http://localhost:5173/?tab=narratives"; budget = 4000 },
    @{ name = "narratives_dark.png"; url = "http://localhost:5173/?tab=narratives&theme=dark"; budget = 4000 }
)

foreach ($t in $targets) {
    $tempShot = "$env:TEMP\" + $t.name
    if (Test-Path $tempShot) { Remove-Item -Force $tempShot }
    $dest = Join-Path $outDir $t.name
    Write-Host "Capturing $($t.name)..."
    Start-Process -FilePath $edgePath -ArgumentList "--headless=new", "--user-data-dir=$tempProfile", "--window-size=1440,1050", "--virtual-time-budget=$($t.budget)", "--screenshot=$tempShot", $t.url -Wait -NoNewWindow
    if (Test-Path $tempShot) {
        Copy-Item -Force -Path $tempShot -Destination $dest
        $size = (Get-Item $dest).Length
        Write-Host "  Saved $dest ($size bytes)"
    } else {
        Write-Warning "  Failed to capture $($t.name)"
    }
}
Write-Host "All screenshots captured."
