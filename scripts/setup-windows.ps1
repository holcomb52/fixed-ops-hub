$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
. (Join-Path $PSScriptRoot "windows-common.ps1")

$ProjectDir = Get-FixedOpsProjectDir
$OpenBat = Join-Path $PSScriptRoot "open-fixed-ops-hub.bat"
$DesktopShortcut = Join-Path $env:USERPROFILE "Desktop\Fixed Ops Hub.lnk"
$StartupShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\Fixed Ops Hub.lnk"

Write-Host "========================================"
Write-Host " Fixed Ops Hub - Windows Setup"
Write-Host "========================================"
Write-Host "Project folder: $ProjectDir"
Write-Host ""

$python = Get-PythonCommand
if (-not $python) {
    Show-FixedOpsError @"
Python was not found.

Install Python 3 from https://www.python.org/downloads/
Important: check Add Python to PATH during install, then run this setup again.
"@
    exit 1
}

Write-Host "Python found: $($python.File)"
Write-Host "Installing required packages..."
Set-Location $ProjectDir

$pipArgs = $python.PrefixArgs + @("-m", "pip", "install", "-r", "requirements.txt")
$pip = Start-Process `
    -FilePath $python.File `
    -ArgumentList $pipArgs `
    -WorkingDirectory $ProjectDir `
    -Wait `
    -PassThru `
    -NoNewWindow

if ($pip.ExitCode -ne 0) {
    Show-FixedOpsError "Package install failed. Make sure Python and pip are installed correctly."
    exit 1
}

function New-FixedOpsShortcut {
    param([string]$ShortcutPath)

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $OpenBat
    $shortcut.WorkingDirectory = $ProjectDir
    $shortcut.WindowStyle = 1
    $shortcut.Description = "Start Fixed Ops Hub and open Google Chrome"
    $shortcut.Save()
}

New-FixedOpsShortcut -ShortcutPath $DesktopShortcut
New-FixedOpsShortcut -ShortcutPath $StartupShortcut

Write-Host ""
Write-Host "Setup complete."
Write-Host "Desktop shortcut: $DesktopShortcut"
Write-Host "Startup shortcut: $StartupShortcut"
Write-Host "Chrome bookmark:  http://localhost:8510"
Write-Host ""
Write-Host "Opening Fixed Ops Hub now..."

& (Join-Path $PSScriptRoot "open-fixed-ops-hub.ps1")
