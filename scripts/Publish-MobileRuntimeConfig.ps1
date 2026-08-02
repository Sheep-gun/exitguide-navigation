param(
  [string]$GistId = "5a4bd2437bfc9b4ae35071b2659a4e30",
  [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $ConfigPath) {
  $ConfigPath = Join-Path $RepoRoot "deploy/mobile-runtime.json"
}
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
  throw "Runtime configuration was not found: $ConfigPath"
}

$Config = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
if ($Config.schema_version -ne 1 -or -not $Config.active) {
  throw "Runtime configuration must use schema version 1 and be active before publishing."
}
if (-not ([string]$Config.api_base_url).StartsWith("https://")) {
  throw "Runtime API URL must use HTTPS."
}

$GhCommand = Get-Command gh.exe -ErrorAction SilentlyContinue
if ($GhCommand) {
  $Gh = $GhCommand.Source
}
else {
  $SiblingGh = Join-Path (Split-Path -Parent $RepoRoot) "exitguide/.tools/gh-2.92.0/bin/gh.exe"
  if (-not (Test-Path -LiteralPath $SiblingGh -PathType Leaf)) {
    throw "GitHub CLI was not found. Run Bootstrap-Windows.ps1 or install gh.exe."
  }
  $Gh = $SiblingGh
}

& $Gh gist edit $GistId --filename mobile-runtime.json $ConfigPath
if ($LASTEXITCODE -ne 0) {
  throw "Could not publish the mobile runtime configuration gist."
}

$RawUrl = "https://gist.githubusercontent.com/Sheep-gun/$GistId/raw/mobile-runtime.json"
$CacheBuster = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$Published = Invoke-RestMethod `
  -Uri "$RawUrl`?exitguide_ts=$CacheBuster" `
  -Headers @{ "Cache-Control" = "no-cache" } `
  -TimeoutSec 20
if ($Published.api_base_url -ne $Config.api_base_url -or -not $Published.active) {
  throw "Published runtime configuration does not match the local active API URL."
}

Write-Host "Mobile runtime configuration published: $RawUrl"
