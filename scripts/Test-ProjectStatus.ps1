$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $RepoRoot
try {
  $Output = & powershell -ExecutionPolicy Bypass -File ".\scripts\Get-ProjectStatus.ps1" | Out-String
  if ($LASTEXITCODE -ne 0) {
    throw "Get-ProjectStatus failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}

$RequiredFragments = @(
  "Project:",
  "Git:",
  "demo-report.md:",
  "openapi.json:",
  "exitguide-source.zip:",
  "Work-block snapshots:",
  "Running services:",
  "Primary check:"
)

foreach ($Fragment in $RequiredFragments) {
  if (-not $Output.Contains($Fragment)) {
    throw "Project status output is missing '$Fragment'."
  }
}

if ($Output.Contains("Git: available")) {
  foreach ($Fragment in @("Git branch:", "Git commit:", "Git remote origin:", "Git working tree:")) {
    if (-not $Output.Contains($Fragment)) {
      throw "Git project status output is missing '$Fragment'."
    }
  }
}

Write-Host "Project status checks passed."
