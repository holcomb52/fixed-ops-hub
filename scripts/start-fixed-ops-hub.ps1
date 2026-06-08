$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
. (Join-Path $PSScriptRoot "windows-common.ps1")

$ProjectDir = Get-FixedOpsProjectDir
$Port = Get-FixedOpsPort
$LogFile = Join-Path (Get-FixedOpsLogDir) "streamlit.log"

Set-Location $ProjectDir

if (Test-PortListening -ListenPort $Port) {
    exit 0
}

$python = Get-PythonCommand
if (-not $python) {
    Show-FixedOpsError @"
Python was not found on this Windows PC.

1. Install Python 3 from https://www.python.org/downloads/
2. Check the box: Add Python to PATH
3. Double-click SETUP-WINDOWS.bat in the fixed-ops-hub folder
"@
    exit 1
}

if (-not (Test-StreamlitInstalled -PythonCommand $python)) {
    Show-FixedOpsError @"
Streamlit is not installed on this Windows PC.

Double-click SETUP-WINDOWS.bat in the fixed-ops-hub folder.
That will install everything this app needs.
"@
    exit 1
}

$arguments = $python.PrefixArgs + @(
    "-m", "streamlit", "run", "app.py",
    "--server.port", "$Port",
    "--server.address", "localhost",
    "--server.headless", "true"
)

Start-Process `
    -FilePath $python.File `
    -ArgumentList $arguments `
    -WorkingDirectory $ProjectDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError $LogFile | Out-Null

Start-Sleep -Seconds 1

if (-not (Test-PortListening -ListenPort $Port)) {
    $logTail = ""
    if (Test-Path $LogFile) {
        $logTail = (Get-Content $LogFile -Tail 12) -join "`n"
    }
    Show-FixedOpsError @"
Fixed Ops Hub could not start on port $Port.

Try running SETUP-WINDOWS.bat first.

Recent log:
$logTail
"@
    exit 1
}
