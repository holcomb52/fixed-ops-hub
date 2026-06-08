$ErrorActionPreference = "Stop"

$SetupScript = Join-Path $PSScriptRoot "setup-windows.ps1"
& $SetupScript
