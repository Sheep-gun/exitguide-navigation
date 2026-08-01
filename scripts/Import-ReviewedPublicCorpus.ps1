param(
  [string]$PacketRoot,
  [string]$ResultsRoot,
  [string]$ProcessedRoot,
  [string]$Database,
  [switch]$Apply
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"
if (-not $PacketRoot) { $PacketRoot = Join-Path $RepoRoot ".artifacts/review-packets/public-corpus-v1" }
if (-not $ResultsRoot) { $ResultsRoot = Join-Path $RepoRoot ".artifacts/review-results/public-corpus-v1" }
if (-not $ProcessedRoot) { $ProcessedRoot = Join-Path $RepoRoot ".artifacts/processed-corpus" }
if (-not $Database) { $Database = Join-Path $RepoRoot ".artifacts/terms-corpus.sqlite" }
$ValidatedResults = Join-Path $ResultsRoot "validated-results.jsonl"
$ReviewItems = Join-Path $PacketRoot "review-items.jsonl"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}
foreach ($InputPath in @($ValidatedResults, $ReviewItems, $ProcessedRoot)) {
  if (-not (Test-Path -LiteralPath $InputPath)) {
    throw "Reviewed public corpus input was not found: $InputPath"
  }
}

Push-Location $ApiRoot
try {
  $env:PYTHONDONTWRITEBYTECODE = "1"
  $env:PYTHONPATH = $ApiRoot
  $env:PYTHONIOENCODING = "utf-8"
  $Arguments = @(
    "-m", "app.services.dataset_adapters.review_import",
    "--validated-results", $ValidatedResults,
    "--review-items", $ReviewItems,
    "--processed-root", $ProcessedRoot,
    "--db", $Database
  )
  if ($Apply) { $Arguments += "--apply" }
  & $Python @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Reviewed public corpus import failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}
