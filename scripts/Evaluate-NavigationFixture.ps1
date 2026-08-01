param(
  [Parameter(Mandatory = $true)][string[]]$Fixture,
  [string]$Name = "fixture",
  [string]$OutputDir = "",
  [double]$MinimumSuccess = 0.90,
  [double]$MinimumGoalAccuracy = 0.95,
  [switch]$Gate
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}
if (-not $OutputDir) {
  $OutputDir = Join-Path $RepoRoot ".artifacts/navigation-fixture-evaluation"
}
$Arguments = @(
  (Join-Path $PSScriptRoot "Evaluate-NavigationFixture.py"),
  "--name", $Name,
  "--output-dir", $OutputDir,
  "--minimum-success", $MinimumSuccess,
  "--minimum-goal-accuracy", $MinimumGoalAccuracy
)
if ($Gate) {
  $Arguments += "--gate"
}
$Arguments += $Fixture

& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
  throw "Navigation fixture evaluation failed with exit code $LASTEXITCODE"
}
