param(
  [ValidateSet("Debug", "Release")]
  [string]$Variant = "Release",
  [string]$Architectures = "arm64-v8a",
  [string]$ApiBaseUrl = "",
  [switch]$DisableRuntimeConfig,
  [switch]$SkipPrebuild
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$MobileRoot = Join-Path $RepoRoot "apps/mobile"
$AndroidRoot = Join-Path $MobileRoot "android"
$NodeRoot = Join-Path $RepoRoot ".tools/node-v24.15.0-win-x64"
$ProjectNpx = Join-Path $NodeRoot "npx.cmd"
$Npx = if (Test-Path -LiteralPath $ProjectNpx) {
  $ProjectNpx
} else {
  (Get-Command npx.cmd -ErrorAction Stop).Source
}

$SdkCandidates = @(
  (Join-Path $HOME "ExitGuideAndroidSdk"),
  $env:ANDROID_HOME,
  (Join-Path $RepoRoot ".tools/android-sdk")
) | Where-Object { $_ -and (Test-Path -LiteralPath (Join-Path $_ "cmdline-tools/latest/bin/sdkmanager.bat")) }
$SdkRoot = $SdkCandidates | Select-Object -First 1
if (-not $SdkRoot) {
  throw "Android SDK was not found. Set ANDROID_HOME or install it at $HOME\ExitGuideAndroidSdk."
}

$JavaCandidates = @(
  $env:JAVA_HOME,
  "C:\Program Files\Java\jdk-17"
) | Where-Object { $_ -and (Test-Path -LiteralPath (Join-Path $_ "bin/java.exe")) }
$JavaHome = $JavaCandidates | Select-Object -First 1
if (-not $JavaHome) {
  throw "JDK 17 was not found. Set JAVA_HOME to a JDK 17 installation."
}

$env:JAVA_HOME = $JavaHome
$env:ANDROID_HOME = $SdkRoot
$env:ANDROID_SDK_ROOT = $SdkRoot
$env:NODE_ENV = if ($Variant -eq "Release") { "production" } else { "development" }
$env:Path = "$JavaHome\bin;$NodeRoot;$SdkRoot\cmdline-tools\latest\bin;$SdkRoot\platform-tools;$env:Path"

if ($ApiBaseUrl.Trim()) {
  $env:EXITGUIDE_API_BASE_URL = $ApiBaseUrl.Trim()
}
if ($DisableRuntimeConfig) {
  $env:EXITGUIDE_DISABLE_RUNTIME_CONFIG = "1"
}

Push-Location $MobileRoot
try {
  if (-not $SkipPrebuild) {
    $env:EXPO_NO_GIT_STATUS = "1"
    & $Npx expo prebuild --platform android --no-install
    if ($LASTEXITCODE -ne 0) {
      throw "Expo prebuild failed with exit code $LASTEXITCODE"
    }
  }
}
finally {
  Pop-Location
}

if (-not (Test-Path -LiteralPath (Join-Path $AndroidRoot "gradlew.bat"))) {
  throw "Android project was not generated. Run without -SkipPrebuild first."
}

Push-Location $AndroidRoot
try {
  & ".\gradlew.bat" ":app:assemble$Variant" "-PreactNativeArchitectures=$Architectures" --no-daemon
  if ($LASTEXITCODE -ne 0) {
    throw "Gradle APK build failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}

$VariantLower = $Variant.ToLowerInvariant()
$ApkSource = Join-Path $AndroidRoot "app/build/outputs/apk/$VariantLower/app-$VariantLower.apk"
if (-not (Test-Path -LiteralPath $ApkSource)) {
  throw "Expected APK was not found: $ApkSource"
}

$ArtifactDir = Join-Path $RepoRoot ".artifacts/apk"
New-Item -ItemType Directory -Path $ArtifactDir -Force | Out-Null
$ApkDestination = Join-Path $ArtifactDir "exitguide-ai-overlay-$VariantLower.apk"
Copy-Item -LiteralPath $ApkSource -Destination $ApkDestination -Force
Write-Host "APK copied to $ApkDestination"
