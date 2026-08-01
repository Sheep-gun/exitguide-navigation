param(
  [string]$NormalizedRoot,
  [string]$OutputRoot
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"
if (-not $NormalizedRoot) {
  $NormalizedRoot = Join-Path $RepoRoot ".artifacts/normalized-datasets"
}
if (-not $OutputRoot) {
  $OutputRoot = Join-Path $RepoRoot ".artifacts/processed-corpus"
}
$Roles = Join-Path $RepoRoot "fixtures/public-datasets/processing-roles.json"
$Inventory = Join-Path $RepoRoot "fixtures/public-datasets/sources.json"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

Push-Location $ApiRoot
try {
  $env:PYTHONDONTWRITEBYTECODE = "1"
  $env:PYTHONPATH = $ApiRoot
  $env:PYTHONIOENCODING = "utf-8"
  & $Python -m app.services.dataset_adapters.public_corpus `
    --normalized-root $NormalizedRoot `
    --output-root $OutputRoot `
    --roles $Roles `
    --inventory $Inventory
  if ($LASTEXITCODE -ne 0) {
    throw "Public corpus processing failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}
