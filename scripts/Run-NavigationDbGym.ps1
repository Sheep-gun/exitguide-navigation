param(
  [ValidateSet("fast", "full", "deep")][string]$Mode = "fast",
  [string]$OutputDir = "",
  [string]$Baseline = "",
  [switch]$Gate,
  [ValidateRange(1, 16)][int]$GeneratedVariants = 3,
  [ValidateRange(0, 512)][int]$SyntheticCases = 0
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}
if (-not $OutputDir) {
  $OutputDir = Join-Path $RepoRoot ".artifacts/navigation-db-gym"
}

$Arguments = @(
  (Join-Path $PSScriptRoot "Run-NavigationDbGym.py"),
  "--mode", $Mode,
  "--output-dir", $OutputDir,
  "--generated-variants", $GeneratedVariants,
  "--synthetic-cases", $SyntheticCases
)
if ($Baseline) {
  $Arguments += @("--baseline", $Baseline)
}
if ($Gate) {
  $Arguments += "--gate"
}

& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
  throw "Navigation DB Gym failed with exit code $LASTEXITCODE"
}
