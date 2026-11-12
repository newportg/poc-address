param(
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8001,

    [ValidateRange(1, 65535)]
    [int]$ClientPort = 5174,

    [string]$CaCertificatePath
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$apiDirectory = Join-Path $repoRoot "api"
$clientSource = Join-Path $repoRoot "docs"
$containerfile = Join-Path $apiDirectory "Containerfile"
$staticServer = Join-Path $PSScriptRoot "serve-client.js"
$imageName = "poc-address-loqate-api:local"
$containerName = "poc-address-local-api-$PID"
$temporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "poc-address-local-$([guid]::NewGuid().ToString('N'))"
$hostCaPath = $null
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
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw "Node.js was not found. Install Node.js to serve the local browser client."
    }

    Write-Host "Rebuilding the local documentation site..."
    & (Join-Path $PSScriptRoot "publish.ps1")
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "Documentation publishing failed with exit code $LASTEXITCODE."
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

    if ($CaCertificatePath) {
        $resolvedCaPath = (Resolve-Path -LiteralPath $CaCertificatePath).Path
        $hostCaPath = Join-Path $temporaryDirectory "host-ca.crt"
        & certutil.exe -encode $resolvedCaPath $hostCaPath *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not convert the supplied CA certificate to PEM format."
        }
    } else {
        $trustedCorporateRoot = Get-ChildItem Cert:\CurrentUser\Root,Cert:\LocalMachine\Root `
            -ErrorAction SilentlyContinue |
            Where-Object { $_.Subject -match "CN=Zscaler Root CA" } |
            Select-Object -First 1
        if ($trustedCorporateRoot) {
            $exportedCaPath = Join-Path $temporaryDirectory "host-ca.cer"
            $hostCaPath = Join-Path $temporaryDirectory "host-ca.crt"
            Export-Certificate -Cert $trustedCorporateRoot -FilePath $exportedCaPath -Type CERT | Out-Null
            & certutil.exe -encode $exportedCaPath $hostCaPath *> $null
            if ($LASTEXITCODE -ne 0) {
                throw "Could not convert the trusted Windows CA certificate to PEM format."
            }
            Write-Host "Using the trusted Windows Zscaler root CA for the container."
        }
    }

    Write-Host "Building the local API image..."
    Invoke-Podman @(
        "build", "--network", "host", "--tag", $imageName,
        "--file", $containerfile, $apiDirectory
    )
    $localApiUrl = "http://127.0.0.1:$ApiPort"
    Write-Host "Starting the API container on $localApiUrl..."
    $runArguments = @("run", "--detach", "--name", $containerName, "--network", "host")
    if ($hostCaPath) {
        $runArguments += @("--volume", "$hostCaPath`:/run/host-ca/ca.crt:ro")
    }
    $runArguments += @("--env", "PORT=$ApiPort", $imageName)
    Invoke-Podman $runArguments
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
    $stdoutLog = Join-Path $temporaryDirectory "client-server.out.log"
    $stderrLog = Join-Path $temporaryDirectory "client-server.err.log"
    $staticProcess = Start-Process -FilePath "node" `
        -ArgumentList @("`"$staticServer`"", "`"$clientDirectory`"", "$ClientPort") `
        -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog `
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
        if (Test-Path $stderrLog) {
            Get-Content -LiteralPath $stderrLog
        }
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
        & podman rm $containerName *> $null
    }
    if (Test-Path $temporaryDirectory) {
        Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force
    }
}
