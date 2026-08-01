param(
  [Parameter(Mandatory = $true)]
  [string]$InputPath,
  [string]$DatabasePath = "",
  [string]$SummaryOutput = "",
  [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$Arguments = @(
  (Join-Path $PSScriptRoot "Import-NavigationPerformance.py"),
  "--input",
  $InputPath
)
if ($DatabasePath) {
  $Arguments += @("--database", $DatabasePath)
}
if ($SummaryOutput) {
  $Arguments += @("--summary-output", $SummaryOutput)
}
if ($CheckOnly) {
  $Arguments += "--check-only"
}

& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
  throw "Navigation performance import failed with exit code $LASTEXITCODE"
}
