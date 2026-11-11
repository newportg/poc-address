param(
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8001,

    [ValidateRange(1, 65535)]
    [int]$ClientPort = 5173
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$apiDirectory = Join-Path $repoRoot "api"
$clientSource = Join-Path $repoRoot "docs"
$containerfile = Join-Path $apiDirectory "Containerfile"
$imageName = "poc-address-loqate-api:local"
$containerName = "poc-address-local-api-$PID"
$temporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "poc-address-local-$([guid]::NewGuid().ToString('N'))"
$staticProcess = $null
$containerStarted = $false

function Invoke-Podman {
    param([string[]]$Arguments)

    & podman @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Podman command failed: podman $($Arguments -join ' ')"
    }
}

try {
    if (-not (Get-Command podman -ErrorAction SilentlyContinue)) {
        throw "Podman was not found. Install Podman Desktop or add podman to PATH."
    }
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python was not found. Install Python to serve the local browser client."
    }

    & podman info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Starting the Podman machine..."
        Invoke-Podman @("machine", "start")
    }

    New-Item -ItemType Directory -Path $temporaryDirectory | Out-Null
    Copy-Item -Path $clientSource -Destination (Join-Path $temporaryDirectory "client") -Recurse
    $clientDirectory = Join-Path $temporaryDirectory "client"
    Set-Content -LiteralPath (Join-Path $clientDirectory "config.js") `
        -Value "window.ADDRESS_API_BASE_URL = `"http://127.0.0.1:$ApiPort`";" -Encoding ASCII

    Write-Host "Building the local API image..."
    Invoke-Podman @(
        "build", "--network", "host", "--tag", $imageName,
        "--file", $containerfile, $apiDirectory
    )
    $localApiUrl = "http://127.0.0.1:$ApiPort"
    Write-Host "Starting the API container on $localApiUrl..."
    Invoke-Podman @(
        "run", "--detach", "--name", $containerName, "--network", "host",
        $imageName, "python", "-m", "uvicorn", "main:app",
        "--host", "0.0.0.0", "--port", "$ApiPort"
    )
    $containerStarted = $true

    $apiReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "$localApiUrl/health" -TimeoutSec 2
            if ($health.status -eq "ok") {
                $apiReady = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $apiReady) {
        & podman logs $containerName
        throw "The API container did not become healthy at $localApiUrl/health."
    }

    $clientUrl = "http://127.0.0.1:$ClientPort/"
    $staticProcess = Start-Process -FilePath "python" `
        -ArgumentList @("-m", "http.server", "$ClientPort", "--bind", "127.0.0.1", "--directory", $clientDirectory) `
        -PassThru -WindowStyle Hidden

    $clientReady = $false
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        try {
            $null = Invoke-WebRequest -Uri $clientUrl -TimeoutSec 2 -UseBasicParsing
            $clientReady = $true
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $clientReady) {
        throw "The local client server did not start at $clientUrl."
    }

    Write-Host "API docs: $localApiUrl/docs"
    Write-Host "Client:   $clientUrl"
    Start-Process $clientUrl
    Read-Host "Press Enter to stop the local client and API"
} catch {
    Write-Error $_
    exit 1
} finally {
    if ($staticProcess -and -not $staticProcess.HasExited) {
        Stop-Process -Id $staticProcess.Id -Force
    }
    if ($containerStarted) {
        & podman stop --time 5 $containerName *> $null
    }
    if (Test-Path $temporaryDirectory) {
        Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force
    }
}
