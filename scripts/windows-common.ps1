function Get-FixedOpsProjectDir {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-FixedOpsPort {
    if ($env:FIXED_OPS_HUB_PORT) {
        return [int]$env:FIXED_OPS_HUB_PORT
    }
    return 8510
}

function Get-FixedOpsUrl {
    return "http://localhost:$(Get-FixedOpsPort)"
}

function Get-FixedOpsLogDir {
    $dir = Join-Path $env:LOCALAPPDATA "fixed-ops-hub"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Test-PortListening {
    param([int]$ListenPort)

    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect("127.0.0.1", $ListenPort, $null, $null)
        $success = $async.AsyncWaitHandle.WaitOne(300)
        if ($success -and $client.Connected) {
            $client.EndConnect($async)
            $client.Close()
            return $true
        }
        $client.Close()
        return $false
    } catch {
        return $false
    }
}

function Test-StreamlitHealthy {
    param([string]$HealthUrl)

    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ File = $py.Source; PrefixArgs = @("-3") }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ File = $python.Source; PrefixArgs = @() }
    }

    $python3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3) {
        return @{ File = $python3.Source; PrefixArgs = @() }
    }

    return $null
}

function Test-StreamlitInstalled {
    param($PythonCommand)

    $args = $PythonCommand.PrefixArgs + @("-m", "streamlit", "--version")
    $process = Start-Process `
        -FilePath $PythonCommand.File `
        -ArgumentList $args `
        -WorkingDirectory (Get-FixedOpsProjectDir) `
        -WindowStyle Hidden `
        -PassThru `
        -Wait

    return $process.ExitCode -eq 0
}

function Show-FixedOpsError {
    param([string]$Message)

    Write-Host ""
    Write-Host $Message -ForegroundColor Red
    Write-Host ""
    [System.Windows.Forms.MessageBox]::Show(
        $Message,
        "Fixed Ops Hub",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}

function Open-FixedOpsBrowser {
    param([string]$Url)

    $chromePaths = @(
        ${env:ProgramFiles} + "\Google\Chrome\Application\chrome.exe",
        ${env:ProgramFiles(x86)} + "\Google\Chrome\Application\chrome.exe",
        ${env:LOCALAPPDATA} + "\Google\Chrome\Application\chrome.exe"
    )

    $chrome = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($chrome) {
        Start-Process -FilePath $chrome -ArgumentList $Url
    } else {
        Start-Process $Url
    }
}
