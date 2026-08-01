param(
  [string]$AvdName = "EGL_Universal_Play_API36",
  [string]$ApiBaseUrl = "http://10.0.2.2:8010",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$SdkRoot = @(
  $env:ANDROID_HOME,
  (Join-Path $HOME "ExitGuideAndroidSdk"),
  (Join-Path $RepoRoot ".tools/android-sdk")
) | Where-Object { $_ -and (Test-Path -LiteralPath (Join-Path $_ "platform-tools/adb.exe")) } | Select-Object -First 1

if (-not $SdkRoot) {
  throw "Android SDK was not found. Set ANDROID_HOME or install it at $HOME\ExitGuideAndroidSdk."
}

$Adb = Join-Path $SdkRoot "platform-tools/adb.exe"
$Emulator = Join-Path $SdkRoot "emulator/emulator.exe"
$Artifact = Join-Path $RepoRoot ".artifacts/apk/exitguide-ai-overlay-release.apk"
$ApiHealthUrl = "http://127.0.0.1:8010/v1/demo-quality"
$PackageName = "com.exitguide.ai"
$AccessibilityService = "${PackageName}/${PackageName}.overlay.ExitGuideAccessibilityService"

function Test-HttpOk([string]$Uri) {
  try {
    return (Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2).StatusCode -eq 200
  }
  catch {
    return $false
  }
}

function Get-EmulatorSerial {
  $line = & $Adb devices | Select-String '^emulator-\d+\s+device$' | Select-Object -First 1
  if (-not $line) {
    return $null
  }
  return ($line.Line -split '\s+')[0]
}

if (-not (Test-HttpOk -Uri $ApiHealthUrl)) {
  $LogDir = Join-Path $RepoRoot ".logs"
  New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
  Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-File", ".\scripts\Start-Api.ps1") `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogDir "emulator-api.log") `
    -RedirectStandardError (Join-Path $LogDir "emulator-api-error.log") | Out-Null

  $ApiDeadline = (Get-Date).AddSeconds(45)
  while (-not (Test-HttpOk -Uri $ApiHealthUrl)) {
    if ((Get-Date) -ge $ApiDeadline) {
      throw "ExitGuide API did not become ready at $ApiHealthUrl."
    }
    Start-Sleep -Seconds 1
  }
}

$Serial = Get-EmulatorSerial
if (-not $Serial) {
  $Avds = & $Emulator -list-avds
  if ($Avds -notcontains $AvdName) {
    throw "Android Virtual Device '$AvdName' does not exist."
  }

  Start-Process -FilePath $Emulator -ArgumentList @("-avd", $AvdName, "-gpu", "auto") | Out-Null
  & $Adb wait-for-device | Out-Null

  $BootDeadline = (Get-Date).AddMinutes(3)
  do {
    Start-Sleep -Seconds 2
    $Serial = Get-EmulatorSerial
    $BootCompleted = if ($Serial) { (& $Adb -s $Serial shell getprop sys.boot_completed 2>$null).Trim() } else { "" }
  } while ($BootCompleted -ne "1" -and (Get-Date) -lt $BootDeadline)

  if (-not $Serial -or $BootCompleted -ne "1") {
    throw "Android emulator '$AvdName' did not finish booting."
  }
}

if (-not $SkipBuild) {
  & (Join-Path $PSScriptRoot "Build-AndroidLocal.ps1") `
    -Variant Release `
    -Architectures "x86_64" `
    -ApiBaseUrl $ApiBaseUrl `
    -DisableRuntimeConfig
}

if (-not (Test-Path -LiteralPath $Artifact)) {
  throw "APK was not found at $Artifact. Run without -SkipBuild first."
}

& $Adb -s $Serial install -r $Artifact | Out-Host
if ($LASTEXITCODE -ne 0) {
  throw "APK installation failed with exit code $LASTEXITCODE."
}

& $Adb -s $Serial shell appops set $PackageName SYSTEM_ALERT_WINDOW allow | Out-Null
& $Adb -s $Serial shell pm grant $PackageName android.permission.POST_NOTIFICATIONS 2>$null
& $Adb -s $Serial shell am force-stop $PackageName | Out-Null
& $Adb -s $Serial shell monkey -p $PackageName -c android.intent.category.LAUNCHER 1 | Out-Null
& $Adb -s $Serial shell settings put secure enabled_accessibility_services $AccessibilityService | Out-Null
& $Adb -s $Serial shell settings put secure accessibility_enabled 1 | Out-Null
Start-Sleep -Seconds 1

& $Adb -s $Serial shell "nc -z -w 3 10.0.2.2 8010" | Out-Null
$EmulatorPortOk = $LASTEXITCODE -eq 0
$EnabledServices = (& $Adb -s $Serial shell settings get secure enabled_accessibility_services).Trim()

Write-Host ""
Write-Host "ExitGuide Android emulator is ready."
Write-Host "  Device:        $Serial ($AvdName)"
Write-Host "  API:           $ApiBaseUrl"
Write-Host "  API reachable: $EmulatorPortOk"
Write-Host "  Accessibility: $($EnabledServices -eq $AccessibilityService)"
Write-Host "  APK:           $Artifact"
