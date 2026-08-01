param(
  [string]$PacketRoot,
  [string]$OutputRoot
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"
if (-not $PacketRoot) {
  $PacketRoot = Join-Path $RepoRoot ".artifacts/review-packets/public-corpus-v1"
}
if (-not $OutputRoot) {
  $OutputRoot = Join-Path $RepoRoot ".artifacts/review-results/public-corpus-v1"
}
$Checklist = Join-Path $PacketRoot "review-checklist.csv"
$ReviewItems = Join-Path $PacketRoot "review-items.jsonl"
$SourceReview = Join-Path $PacketRoot "source-review.json"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}
foreach ($InputPath in @($Checklist, $ReviewItems, $SourceReview)) {
  if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
    throw "Public corpus review input was not found: $InputPath"
  }
}

Push-Location $ApiRoot
try {
  $env:PYTHONDONTWRITEBYTECODE = "1"
  $env:PYTHONPATH = $ApiRoot
  $env:PYTHONIOENCODING = "utf-8"
  & $Python -m app.services.dataset_adapters.review_results `
    --checklist $Checklist `
    --review-items $ReviewItems `
    --source-review $SourceReview `
    --output-root $OutputRoot
  if ($LASTEXITCODE -ne 0) {
    throw "Public corpus review validation failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}
