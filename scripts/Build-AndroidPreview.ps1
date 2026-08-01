param(
  [ValidateSet("development", "preview", "production")]
  [string]$Profile = "preview"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$MobileRoot = Join-Path $RepoRoot "apps/mobile"
$NodeRoot = Join-Path $RepoRoot ".tools/node-v24.15.0-win-x64"
$Npx = Join-Path $NodeRoot "npx.cmd"

if (-not (Test-Path $Npx)) {
  throw "Portable Node runtime was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$env:Path = "$NodeRoot;$env:Path"
Push-Location $MobileRoot
try {
  & $Npx eas-cli build --platform android --profile $Profile
  exit $LASTEXITCODE
}
finally {
  Pop-Location
}
