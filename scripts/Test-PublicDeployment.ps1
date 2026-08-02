$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DeployScript = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "scripts/Deploy-PublicNavigationApi.ps1")
$PublishScript = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "scripts/Publish-MobileRuntimeConfig.ps1")
$Installer = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "deploy/server/install-public-api.sh")
$RuntimeConfig = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "deploy/mobile-runtime.json") | ConvertFrom-Json
$AppConfig = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/app.json") | ConvertFrom-Json

foreach ($Fragment in @(
  "System32\OpenSSH",
  "ssh.exe",
  "exitguide-navigation-config",
  "git archive",
  "Send-FileOverSsh",
  "RedirectStandardInput",
  "CopyTo",
  "LLM_PROVIDER=exaone",
  "NAVIGATION_AGENT_PROVIDER=exaone",
  "NAVIGATION_AGENT_TIMEOUT_SECONDS=35",
  "EXAONE_API_KEY",
  "Publish-MobileRuntimeConfig.ps1",
  "SkipRuntimeConfigPublish",
  "MobileRuntime.api_base_url = `$PublicUrl"
)) {
  if (-not $DeployScript.Contains($Fragment)) {
    throw "Public deployment script is missing required fragment: $Fragment"
  }
}

foreach ($Fragment in @(
  "/home/exitnav/workspace/",
  "127.0.0.1",
  "cloudflared",
  "trycloudflare",
  "tmux",
  "PUBLIC_API_URL="
)) {
  if (-not $Installer.Contains($Fragment)) {
    throw "Public server installer is missing required fragment: $Fragment"
  }
}

if ($RuntimeConfig.schema_version -ne 1) {
  throw "Mobile runtime configuration must use schema version 1."
}
if (-not $RuntimeConfig.api_base_url.StartsWith("https://")) {
  throw "Mobile runtime API URL must use HTTPS."
}
if (-not $AppConfig.expo.extra.runtimeConfigUrl.StartsWith("https://gist.githubusercontent.com/")) {
  throw "The release APK runtime configuration must be anonymously readable from the public gist."
}
foreach ($Fragment in @("gist edit", "mobile-runtime.json", "Invoke-RestMethod", "exitguide_ts", "Cache-Control")) {
  if (-not $PublishScript.Contains($Fragment)) {
    throw "Runtime configuration publisher is missing required fragment: $Fragment"
  }
}

Write-Host "Public deployment checks passed."
