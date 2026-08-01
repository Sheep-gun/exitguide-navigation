param(
  [string]$Report = "",
  [string]$Output = "",
  [ValidateRange(1, 100)][int]$MaxFailures = 40
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}
$Arguments = @((Join-Path $PSScriptRoot "Propose-NavigationDbChanges.py"), "--max-failures", $MaxFailures)
if ($Report) { $Arguments += @("--report", $Report) }
if ($Output) { $Arguments += @("--output", $Output) }
& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw "K-EXAONE proposal generation failed with exit code $LASTEXITCODE" }
