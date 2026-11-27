[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runRoot = Join-Path $projectRoot ".local\run"

function Stop-RecordedProcess {
    param([string]$StatePath)

    if (-not (Test-Path -LiteralPath $StatePath)) {
        return
    }

    $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    $processId = [int]$state.processId
    $record = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue

    if ($null -eq $record) {
        Remove-Item -LiteralPath $StatePath -Force
        return
    }

    $commandLine = [string]$record.CommandLine
    $isTravelMate = $commandLine.Contains([string]$state.signature) -and $commandLine.Contains($projectRoot)
    if (-not $isTravelMate) {
        Write-Warning "Refusing to stop PID $processId because its CommandLine is not a recorded TravelMate service."
        return
    }

    Stop-Process -Id $processId -Force
    Remove-Item -LiteralPath $StatePath -Force
    Write-Host "Stopped $($state.name) (PID $processId)."
}

if (-not (Test-Path -LiteralPath $runRoot)) {
    Write-Host "No recorded TravelMate services are running."
    return
}

# State signatures are "uvicorn app.main:app" and "http.server <port>".
Stop-RecordedProcess -StatePath (Join-Path $runRoot "frontend.json")
Stop-RecordedProcess -StatePath (Join-Path $runRoot "backend.json")
Write-Host "TravelMate local services are stopped."
