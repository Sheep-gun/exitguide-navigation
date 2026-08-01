param(
  [string]$OutputDir = "",
  [switch]$Gate
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}
if (-not $OutputDir) {
  $OutputDir = Join-Path $RepoRoot ".artifacts/navigation-catalog-quality"
}

$Arguments = @(
  (Join-Path $PSScriptRoot "Audit-NavigationCatalog.py"),
  "--output-dir", $OutputDir
)
if ($Gate) {
  $Arguments += "--gate"
}

& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
  throw "Navigation catalog audit failed with exit code $LASTEXITCODE"
}
