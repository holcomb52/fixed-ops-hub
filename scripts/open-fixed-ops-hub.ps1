$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
. (Join-Path $PSScriptRoot "windows-common.ps1")

$ProjectDir = Get-FixedOpsProjectDir
$Port = Get-FixedOpsPort
$Url = Get-FixedOpsUrl
$StartScript = Join-Path $PSScriptRoot "start-fixed-ops-hub.ps1"

Write-Host "Fixed Ops Hub"
Write-Host "Project: $ProjectDir"
Write-Host "URL: $Url"
Write-Host ""

if (-not (Test-Path (Join-Path $ProjectDir "app.py"))) {
    Show-FixedOpsError @"
The fixed-ops-hub project folder was not found.

Make sure this entire project folder is copied to your Windows PC
(OneDrive, USB, or Git), then run SETUP-WINDOWS.bat from inside it.
"@
    exit 1
}

if (-not (Test-StreamlitHealthy -HealthUrl "$Url/_stcore/health")) {
    Write-Host "Starting Fixed Ops Hub..."
    & $StartScript
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    $started = $false
    for ($i = 0; $i -lt 40; $i++) {
        if (Test-StreamlitHealthy -HealthUrl "$Url/_stcore/health") {
            $started = $true
            break
        }
        Start-Sleep -Milliseconds 250
    }

    if (-not $started) {
        Show-FixedOpsError @"
Fixed Ops Hub did not open in time.

Run SETUP-WINDOWS.bat once on this Windows PC, then try again.
"@
        exit 1
    }
}

Write-Host "Opening Google Chrome..."
Open-FixedOpsBrowser -Url $Url
Write-Host "Done."
