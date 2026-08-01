param(
  [double]$MinimumAccuracy = 0.95,
  [double]$MinimumSplitAccuracy = 0.90,
  [string]$Output = "",
  [string[]]$Fixture = @(),
  [switch]$Gate
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}
if (-not $Output) {
  $Output = Join-Path $RepoRoot ".artifacts/navigation-goal-generalization/report.json"
}
$Arguments = @(
  (Join-Path $PSScriptRoot "Evaluate-NavigationIndependentGoals.py"),
  "--minimum-accuracy", $MinimumAccuracy,
  "--minimum-split-accuracy", $MinimumSplitAccuracy,
  "--output", $Output
)
if ($Gate) {
  $Arguments += "--gate"
}
if ($Fixture.Count -gt 0) {
  $Arguments += @($Fixture)
}

& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
  throw "Independent goal evaluation failed with exit code $LASTEXITCODE"
}
