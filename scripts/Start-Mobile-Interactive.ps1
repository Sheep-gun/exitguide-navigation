$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$MobileRoot = Join-Path $RepoRoot "apps/mobile"
$NodeRoot = Join-Path $RepoRoot ".tools/node-v24.15.0-win-x64"
$Npx = Join-Path $NodeRoot "npx.cmd"

if (-not (Test-Path $Npx)) {
  throw "Portable Node runtime was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$env:Path = "$NodeRoot;$env:Path"

Set-Location $MobileRoot
& $Npx expo start --host lan --clear
