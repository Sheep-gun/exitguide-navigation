param(
  [Parameter(Mandatory = $true)][string]$InputPath,
  [string]$Target = "",
  [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}
$Arguments = @((Join-Path $PSScriptRoot "Import-NavigationGold.py"), "--input", $InputPath)
if ($Target) { $Arguments += @("--target", $Target) }
if ($CheckOnly) { $Arguments += "--check-only" }
& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw "Navigation gold import failed with exit code $LASTEXITCODE" }
