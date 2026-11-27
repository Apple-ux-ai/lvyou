[CmdletBinding()]
param([string]$Destination)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pythonPath = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
$backupTool = Join-Path $projectRoot "backend\scripts\local_data.py"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python environment not found at $pythonPath"
}

$arguments = @($backupTool, "--project-root", $projectRoot, "backup")
if ($Destination) {
    $arguments += @("--destination", $Destination)
}

& $pythonPath @arguments
if ($LASTEXITCODE -ne 0) {
    throw "TravelMate backup failed with exit code $LASTEXITCODE"
}
