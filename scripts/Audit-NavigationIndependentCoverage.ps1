param(
  [string]$Output = "",
  [switch]$Gate
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}
if (-not $Output) {
  $Output = Join-Path $RepoRoot ".artifacts/navigation-independent-coverage/report.json"
}
$Arguments = @(
  (Join-Path $PSScriptRoot "Audit-NavigationIndependentCoverage.py"),
  "--output", $Output
)
if ($Gate) {
  $Arguments += "--gate"
}

& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
  throw "Independent coverage audit failed with exit code $LASTEXITCODE"
}
