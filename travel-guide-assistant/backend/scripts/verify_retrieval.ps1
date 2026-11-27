[CmdletBinding()]
param(
    [double]$RecallAt3 = 0.80,
    [double]$RecallAt5 = 0.90,
    [string]$Report = ""
)

$ErrorActionPreference = "Stop"
$backendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $backendRoot ".venv\Scripts\python.exe"
if (-not $Report) {
    $Report = Join-Path $backendRoot "..\docs\retrieval-evaluation-latest.json"
}

& $pythonPath (Join-Path $PSScriptRoot "evaluate_retrieval.py") `
    --require-recall-at-3 $RecallAt3 `
    --require-recall-at-5 $RecallAt5 `
    --report $Report
exit $LASTEXITCODE
