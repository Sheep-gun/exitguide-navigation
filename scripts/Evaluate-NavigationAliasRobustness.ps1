param(
  [string]$Output = "",
  [int]$MaximumGroups = 0,
  [double]$MinimumPositiveAccuracy = 0.90,
  [double]$MinimumNegativeAccuracy = 0.75,
  [int]$MaximumUnresolved = 0,
  [switch]$Gate
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}
if (-not $Output) {
  $Output = Join-Path $RepoRoot ".artifacts/navigation-alias-robustness/report.json"
}
$Arguments = @(
  (Join-Path $PSScriptRoot "Evaluate-NavigationAliasRobustness.py"),
  "--output", $Output,
  "--maximum-groups", $MaximumGroups,
  "--minimum-positive-accuracy", $MinimumPositiveAccuracy,
  "--minimum-negative-accuracy", $MinimumNegativeAccuracy,
  "--maximum-unresolved", $MaximumUnresolved
)
if ($Gate) {
  $Arguments += "--gate"
}

& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
  throw "Alias robustness evaluation failed with exit code $LASTEXITCODE"
}
