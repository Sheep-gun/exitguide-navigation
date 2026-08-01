param(
  [ValidateSet("fast", "full")][string]$Mode = "fast"
)

$ErrorActionPreference = "Stop"
$Runner = Join-Path $PSScriptRoot "Run-NavigationDbGym.ps1"
& $Runner -Mode $Mode -Gate
if ($LASTEXITCODE -ne 0) {
  throw "Navigation DB Gym $Mode gate failed with exit code $LASTEXITCODE"
}
