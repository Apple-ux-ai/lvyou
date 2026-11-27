[CmdletBinding()]
param(
    [int]$FrontendPort = 5501,
    [int]$BackendPort = 8000,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$backendRoot = Join-Path $projectRoot "backend"
$pythonPath = Join-Path $backendRoot ".venv\Scripts\python.exe"
$runtimeRoot = Join-Path $projectRoot ".local"
$runRoot = Join-Path $runtimeRoot "run"
$logRoot = Join-Path $runtimeRoot "logs"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python environment not found at $pythonPath. Create backend/.venv and install backend/requirements.txt."
}

New-Item -ItemType Directory -Force -Path $runRoot, $logRoot | Out-Null

function Test-ServiceUrl {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    }
    catch {
        return $false
    }
}

function Wait-ServiceUrl {
    param(
        [string]$Url,
        [int]$Attempts = 60
    )

    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        if (Test-ServiceUrl -Url $Url) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Save-ProcessState {
    param(
        [string]$Name,
        [System.Diagnostics.Process]$Process,
        [string]$Signature
    )

    [pscustomobject]@{
        name = $Name
        processId = $Process.Id
        signature = $Signature
        startedAt = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot "$Name.json") -Encoding UTF8
}

function Start-LocalService {
    param(
        [string]$Name,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$Signature,
        [string]$HealthUrl
    )

    if (Test-ServiceUrl -Url $HealthUrl) {
        Write-Host "$Name is already available at $HealthUrl"
        return
    }

    $stdoutLog = Join-Path $logRoot "$Name.out.log"
    $stderrLog = Join-Path $logRoot "$Name.err.log"
    $process = Start-Process -FilePath $pythonPath -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    Save-ProcessState -Name $Name -Process $process -Signature $Signature

    if (-not (Wait-ServiceUrl -Url $HealthUrl)) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
        Remove-Item -LiteralPath (Join-Path $runRoot "$Name.json") -Force -ErrorAction SilentlyContinue
        throw "$Name failed to start. Check $stderrLog"
    }

    Write-Host "$Name started at $HealthUrl"
}

$backendHealth = "http://127.0.0.1:$BackendPort/api/health"
$frontendHealth = "http://127.0.0.1:$FrontendPort/pages/home.html"
$backendArguments = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort")
$frontendArguments = @("-m", "http.server", "$FrontendPort", "--bind", "127.0.0.1")

$previousHfHubOffline = $env:HF_HUB_OFFLINE
$previousTransformersOffline = $env:TRANSFORMERS_OFFLINE
try {
    # The semantic model is downloaded and quality-gated before activation.
    # Runtime startup should use that cache instead of waiting on Hugging Face.
    $env:HF_HUB_OFFLINE = "1"
    $env:TRANSFORMERS_OFFLINE = "1"
    Start-LocalService -Name "backend" -Arguments $backendArguments -WorkingDirectory $backendRoot `
        -Signature "uvicorn app.main:app" -HealthUrl $backendHealth
}
finally {
    if ($null -eq $previousHfHubOffline) { Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue } else { $env:HF_HUB_OFFLINE = $previousHfHubOffline }
    if ($null -eq $previousTransformersOffline) { Remove-Item Env:TRANSFORMERS_OFFLINE -ErrorAction SilentlyContinue } else { $env:TRANSFORMERS_OFFLINE = $previousTransformersOffline }
}
Start-LocalService -Name "frontend" -Arguments $frontendArguments -WorkingDirectory $projectRoot `
    -Signature "http.server $FrontendPort" -HealthUrl $frontendHealth

$homeUrl = "http://127.0.0.1:$FrontendPort/pages/home.html"
Write-Host "TravelMate is ready: $homeUrl"
if (-not $NoBrowser) {
    Start-Process $homeUrl
}
