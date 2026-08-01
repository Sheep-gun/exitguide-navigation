$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Source = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/src/components/CatalogStatus.tsx")

foreach ($Fragment in @("failedChecks", "check.detail", "issueList", "issueText", "failedChecks.slice(0, 3)")) {
  if (-not $Source.Contains($Fragment)) {
    throw "CatalogStatus.tsx is missing readiness detail fragment: $Fragment"
  }
}

Write-Host "Mobile readiness detail checks passed."
