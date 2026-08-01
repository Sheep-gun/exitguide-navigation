param(
  [Parameter(Mandatory = $true)][string]$VersionId,
  [Parameter(Mandatory = $true)]
  [ValidateSet("approved_for_search", "rejected_license", "rejected_privacy", "rejected_quality", "deprecated")]
  [string]$Decision,
  [Parameter(Mandatory = $true)][string]$Reviewer,
  [Parameter(Mandatory = $true)][string]$Reason,
  [string]$Database
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"
if (-not $Database) {
  $Database = Join-Path $RepoRoot ".artifacts/terms-corpus.sqlite"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

Push-Location $ApiRoot
try {
  $env:PYTHONDONTWRITEBYTECODE = "1"
  $env:PYTHONPATH = $ApiRoot
  $env:PYTHONIOENCODING = "utf-8"
  & $Python -m app.services.terms_review `
    --db $Database `
    --version-id $VersionId `
    --decision $Decision `
    --reviewer $Reviewer `
    --reason $Reason
  if ($LASTEXITCODE -ne 0) {
    throw "Terms document review failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}
