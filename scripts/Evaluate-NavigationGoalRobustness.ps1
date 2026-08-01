param(
  [ValidateSet("fast", "full")][string]$Mode = "fast",
  [double]$MinimumAccuracy = 0.995,
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
  $OutputDir = Join-Path $RepoRoot ".artifacts/navigation-goal-robustness"
}

$Arguments = @(
  (Join-Path $PSScriptRoot "Evaluate-NavigationGoalRobustness.py"),
  "--mode", $Mode,
  "--minimum-accuracy", $MinimumAccuracy,
  "--output-dir", $OutputDir
)
if ($Gate) {
  $Arguments += "--gate"
}

& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
  throw "Navigation goal robustness failed with exit code $LASTEXITCODE"
}
