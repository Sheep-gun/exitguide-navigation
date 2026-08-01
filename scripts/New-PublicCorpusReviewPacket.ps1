param(
  [string]$ProcessedRoot,
  [string]$NormalizedRoot,
  [string]$OutputRoot,
  [ValidateRange(1, 100)][int]$SampleLimit = 8
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"
if (-not $ProcessedRoot) {
  $ProcessedRoot = Join-Path $RepoRoot ".artifacts/processed-corpus"
}
if (-not $NormalizedRoot) {
  $NormalizedRoot = Join-Path $RepoRoot ".artifacts/normalized-datasets"
}
if (-not $OutputRoot) {
  $OutputRoot = Join-Path $RepoRoot ".artifacts/review-packets/public-corpus-v1"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

Push-Location $ApiRoot
try {
  $env:PYTHONDONTWRITEBYTECODE = "1"
  $env:PYTHONPATH = $ApiRoot
  $env:PYTHONIOENCODING = "utf-8"
  & $Python -m app.services.dataset_adapters.review_packet `
    --processed-root $ProcessedRoot `
    --normalized-root $NormalizedRoot `
    --output-root $OutputRoot `
    --sample-limit $SampleLimit
  if ($LASTEXITCODE -ne 0) {
    throw "Public corpus review packet generation failed with exit code $LASTEXITCODE"
  }
  $SourceTemplate = Join-Path $OutputRoot "source-review.template.json"
  $SourceReview = Join-Path $OutputRoot "source-review.json"
  if (-not (Test-Path -LiteralPath $SourceReview)) {
    Copy-Item -LiteralPath $SourceTemplate -Destination $SourceReview
  }
}
finally {
  Pop-Location
}
