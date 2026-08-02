$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiSource = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/src/api/exitguideApi.ts")
$SettingsSource = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/src/components/ApiSettings.tsx")
$ProviderSettingsSource = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/src/components/ProviderSettings.tsx")
$OverlayNativeSource = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/src/native/ExitGuideOverlay.ts")
$StoredSource = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/src/hooks/useStoredApiBaseUrl.ts")

foreach ($Fragment in @('export function normalizeApiBaseUrl', 'http://${trimmed}', 'replace(/\/+$/, "")', 'ExitGuideApiError', 'fetchRuntimeApiBaseUrl', 'application/vnd.github.raw+json', 'runtimeConfigUrl', 'exitguide_ts=${Date.now()}', 'Cache-Control')) {
  if (-not $ApiSource.Contains($Fragment)) {
    throw "exitguideApi.ts is missing URL normalization fragment: $Fragment"
  }
}

foreach ($Fragment in @("normalizeApiBaseUrl", "onEndEditing", "commitApiBaseUrl")) {
  if (-not $SettingsSource.Contains($Fragment)) {
    throw "ApiSettings.tsx is missing URL commit fragment: $Fragment"
  }
}

if (-not $StoredSource.Contains("saveApiBaseUrl(normalizeApiBaseUrl(apiBaseUrl))")) {
  throw "useStoredApiBaseUrl.ts should persist normalized API URLs."
}

if (-not $StoredSource.Contains("fetchRuntimeApiBaseUrl")) {
  throw "useStoredApiBaseUrl.ts should refresh the public API URL from runtime configuration."
}

$AppConfig = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/app.json") | ConvertFrom-Json
if (-not $AppConfig.expo.extra.runtimeConfigUrl.StartsWith("https://")) {
  throw "app.json should provide an HTTPS runtime configuration URL."
}

foreach ($Fragment in @("provider_id", "provider_api_key", "provider_model", "provider_base_url", "buildProviderPayload")) {
  if (-not $ApiSource.Contains($Fragment)) {
    throw "exitguideApi.ts is missing provider request fragment: $Fragment"
  }
}

foreach ($Fragment in @("google", "gpt", "exaone", "secureTextEntry")) {
  if (-not $ProviderSettingsSource.Contains($Fragment)) {
    throw "ProviderSettings.tsx is missing provider UI fragment: $Fragment"
  }
}

foreach ($Fragment in @("providerSettings.providerId", "providerSettings.apiKey", "providerSettings.model", "providerSettings.baseUrl")) {
  if (-not $OverlayNativeSource.Contains($Fragment)) {
    throw "ExitGuideOverlay.ts is missing overlay provider fragment: $Fragment"
  }
}

Write-Host "Mobile API URL checks passed."
