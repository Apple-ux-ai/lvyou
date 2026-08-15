[CmdletBinding()]
param(
    [string]$IndexRoot = "",
    [string]$Version = "bge-small-zh-v1.5",
    [double]$RecallAt3 = 0.80,
    [double]$RecallAt5 = 0.90,
    [string]$Report = ""
)

$ErrorActionPreference = "Stop"
$backendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $backendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python environment not found at $pythonPath"
}

if (-not $IndexRoot) {
    $IndexRoot = Join-Path $backendRoot "index_versions"
} elseif (-not [IO.Path]::IsPathRooted($IndexRoot)) {
    $IndexRoot = Join-Path $backendRoot $IndexRoot
}

$probe = & $pythonPath -c "import importlib.util, sys; missing = [name for name in ('sentence_transformers', 'torch', 'transformers') if importlib.util.find_spec(name) is None]; print('Missing semantic dependencies: ' + ', '.join(missing) if missing else 'Semantic dependencies available'); sys.exit(2 if missing else 0)"
if ($LASTEXITCODE -ne 0) {
    throw "Install backend/requirements.lock (including sentence-transformers and torch) before building a BGE index."
}

$IndexRoot = (Resolve-Path -LiteralPath (New-Item -ItemType Directory -Force -Path $IndexRoot)).Path
if (-not $Report) {
    $Report = Join-Path $backendRoot "..\docs\retrieval-evaluation-$Version.json"
}

# Keep the semantic rebuild isolated from the current local Hash index. The
# active pointer is changed only after the new version passes evaluation.
$previousEmbeddingProvider = $env:TRAVELMATE_EMBEDDING_PROVIDER
$previousEmbeddingModel = $env:TRAVELMATE_EMBEDDING_MODEL
$previousEmbeddingVersion = $env:TRAVELMATE_EMBEDDING_VERSION
$previousEmbeddingDimension = $env:TRAVELMATE_EMBEDDING_DIMENSION
$previousEmbeddingFallback = $env:TRAVELMATE_EMBEDDING_ALLOW_FALLBACK
$previousIndexRoot = $env:TRAVELMATE_INDEX_ROOT
$previousIndexVersion = $env:TRAVELMATE_INDEX_VERSION

try {
    $env:TRAVELMATE_EMBEDDING_PROVIDER = "sentence_transformers"
    $env:TRAVELMATE_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
    $env:TRAVELMATE_EMBEDDING_VERSION = $Version
    $env:TRAVELMATE_EMBEDDING_DIMENSION = "512"
    $env:TRAVELMATE_EMBEDDING_ALLOW_FALLBACK = "false"
    $env:TRAVELMATE_INDEX_ROOT = $IndexRoot
    $env:TRAVELMATE_INDEX_VERSION = $Version

    & $pythonPath (Join-Path $PSScriptRoot "ingest.py") `
        --index-root $IndexRoot `
        --version $Version `
        --reset
    if ($LASTEXITCODE -ne 0) {
        throw "BGE index build failed; the active index was not changed."
    }

    & (Join-Path $PSScriptRoot "verify_retrieval.ps1") `
        -RecallAt3 $RecallAt3 `
        -RecallAt5 $RecallAt5 `
        -Report $Report
    if ($LASTEXITCODE -ne 0) {
        throw "BGE retrieval quality gate failed; the previous active index remains selected."
    }

    & $pythonPath (Join-Path $PSScriptRoot "activate_index.py") `
        --index-root $IndexRoot `
        --version $Version
    if ($LASTEXITCODE -ne 0) {
        throw "BGE index passed evaluation but could not be activated."
    }
}
finally {
    if ($null -eq $previousEmbeddingProvider) { Remove-Item Env:TRAVELMATE_EMBEDDING_PROVIDER -ErrorAction SilentlyContinue } else { $env:TRAVELMATE_EMBEDDING_PROVIDER = $previousEmbeddingProvider }
    if ($null -eq $previousEmbeddingModel) { Remove-Item Env:TRAVELMATE_EMBEDDING_MODEL -ErrorAction SilentlyContinue } else { $env:TRAVELMATE_EMBEDDING_MODEL = $previousEmbeddingModel }
    if ($null -eq $previousEmbeddingVersion) { Remove-Item Env:TRAVELMATE_EMBEDDING_VERSION -ErrorAction SilentlyContinue } else { $env:TRAVELMATE_EMBEDDING_VERSION = $previousEmbeddingVersion }
    if ($null -eq $previousEmbeddingDimension) { Remove-Item Env:TRAVELMATE_EMBEDDING_DIMENSION -ErrorAction SilentlyContinue } else { $env:TRAVELMATE_EMBEDDING_DIMENSION = $previousEmbeddingDimension }
    if ($null -eq $previousEmbeddingFallback) { Remove-Item Env:TRAVELMATE_EMBEDDING_ALLOW_FALLBACK -ErrorAction SilentlyContinue } else { $env:TRAVELMATE_EMBEDDING_ALLOW_FALLBACK = $previousEmbeddingFallback }
    if ($null -eq $previousIndexRoot) { Remove-Item Env:TRAVELMATE_INDEX_ROOT -ErrorAction SilentlyContinue } else { $env:TRAVELMATE_INDEX_ROOT = $previousIndexRoot }
    if ($null -eq $previousIndexVersion) { Remove-Item Env:TRAVELMATE_INDEX_VERSION -ErrorAction SilentlyContinue } else { $env:TRAVELMATE_INDEX_VERSION = $previousIndexVersion }
}

$relativeIndexRoot = $IndexRoot
$backendPrefix = $backendRoot.TrimEnd([char[]]"\/") + [IO.Path]::DirectorySeparatorChar
if ($IndexRoot.StartsWith($backendPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    $relativeIndexRoot = $IndexRoot.Substring($backendPrefix.Length)
}
$relativeIndexRoot = $relativeIndexRoot.Replace("\", "/")
Write-Host "BGE index passed the retrieval gate and is active: $Version"
Write-Host "Index root: $IndexRoot"
Write-Host "Report: $Report"
Write-Host "Runtime config: TRAVELMATE_INDEX_ROOT=$relativeIndexRoot; leave TRAVELMATE_INDEX_VERSION empty to use active.json."
