[CmdletBinding()]
param(
    [string]$BackupPath,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pythonPath = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
$backupTool = Join-Path $projectRoot "backend\scripts\local_data.py"
$verifyTool = Join-Path $projectRoot "backend\scripts\verify_backup.py"

if (-not $BackupPath) {
    $backupRoot = Join-Path $projectRoot "backups"
    if (-not (Test-Path -LiteralPath $backupRoot)) {
        throw "No TravelMate backups were found at $backupRoot"
    }
    $latest = Get-ChildItem -LiteralPath $backupRoot -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "manifest.json") } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($null -eq $latest) {
        throw "No valid TravelMate backup with manifest.json was found at $backupRoot"
    }
    $BackupPath = $latest.FullName
}

$resolvedBackup = (Resolve-Path -LiteralPath $BackupPath).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedBackup "manifest.json"))) {
    throw "The selected directory is not a TravelMate backup: $resolvedBackup"
}

& $pythonPath $verifyTool --backup-path $resolvedBackup | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The selected backup failed read-only verification: $resolvedBackup"
}
Write-Host "Backup verification passed: $resolvedBackup"

if (-not $Force) {
    $answer = Read-Host "Restore $resolvedBackup and replace current local data? Type RESTORE to continue"
    if ($answer -ne "RESTORE") {
        Write-Host "Restore cancelled."
        return
    }
}

& (Join-Path $PSScriptRoot "Stop-TravelMate.ps1")
& $pythonPath $backupTool --project-root $projectRoot restore --backup-path $resolvedBackup
if ($LASTEXITCODE -ne 0) {
    throw "TravelMate restore failed with exit code $LASTEXITCODE"
}
