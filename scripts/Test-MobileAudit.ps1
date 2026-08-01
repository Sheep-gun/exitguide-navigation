$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$MobileRoot = Join-Path $RepoRoot "apps/mobile"
$NodeRoot = Join-Path $RepoRoot ".tools/node-v24.15.0-win-x64"
$Npm = Join-Path $NodeRoot "npm.cmd"

if (-not (Test-Path -LiteralPath $Npm)) {
  throw "Portable Node runtime was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$env:Path = "$NodeRoot;$env:Path"
Push-Location $MobileRoot
try {
  # Keep the full advisory report visible, but block CI only for critical findings.
  & $Npm audit --audit-level=critical
  if ($LASTEXITCODE -ne 0) {
    throw "npm audit found critical vulnerabilities (exit code $LASTEXITCODE)"
  }
}
finally {
  Pop-Location
}
