param(
  [Parameter(Mandatory = $true)]
  [string]$Text,

  [string]$Serial = "",
  [string]$PackageName = "com.exitguide.ai",
  [string]$ClassName = "android.widget.EditText",
  [ValidateRange(0, 32)]
  [int]$Instance = 0,
  [string]$Adb = "",
  [string]$AndroidSdk = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Source = Join-Path $RepoRoot "tools/uiautomator-unicode-input/UnicodeInputTest.java"
$BuildRoot = Join-Path $RepoRoot ".artifacts/uiautomator-unicode-input"
$Classes = Join-Path $BuildRoot "classes"
$Dex = Join-Path $BuildRoot "dex"
$ClassJar = Join-Path $BuildRoot "unicode-input-classes.jar"
$DexJar = Join-Path $BuildRoot "unicode-input.jar"
$RemoteJar = "/data/local/tmp/exitguide-unicode-input.jar"

if (-not $AndroidSdk) {
  $AndroidSdk = @(
    $env:EXITGUIDE_ANDROID_SDK,
    $env:ANDROID_SDK_ROOT,
    (Join-Path $env:USERPROFILE "ExitGuideAndroidSdk"),
    (Join-Path $env:LOCALAPPDATA "Android/Sdk")
  ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $AndroidSdk) {
  throw "Android SDK was not found. Pass -AndroidSdk explicitly."
}

if (-not $Adb) {
  $Adb = Join-Path $AndroidSdk "platform-tools/adb.exe"
}
if (-not (Test-Path -LiteralPath $Adb)) {
  throw "adb was not found: $Adb"
}

$Platform = Get-ChildItem -LiteralPath (Join-Path $AndroidSdk "platforms") -Directory |
  Sort-Object { [int]($_.Name -replace '^android-', '') } -Descending |
  Select-Object -First 1
$BuildTools = Get-ChildItem -LiteralPath (Join-Path $AndroidSdk "build-tools") -Directory |
  Sort-Object { [version]$_.Name } -Descending |
  Select-Object -First 1
if (-not $Platform -or -not $BuildTools) {
  throw "Android platform/build-tools are missing under $AndroidSdk"
}

$AndroidJar = Join-Path $Platform.FullName "android.jar"
$UiAutomatorJar = Join-Path $Platform.FullName "uiautomator.jar"
$AndroidTestBaseJar = Join-Path $Platform.FullName "optional/android.test.base.jar"
$D8 = Join-Path $BuildTools.FullName "d8.bat"
$Javac = (Get-Command javac -ErrorAction Stop).Source
$Jar = Get-ChildItem -Path "C:/Program Files/Java" -Recurse -Filter "jar.exe" -ErrorAction SilentlyContinue |
  Sort-Object FullName -Descending |
  Select-Object -First 1 -ExpandProperty FullName
if (-not $Jar) {
  throw "jar.exe was not found under C:/Program Files/Java"
}

$stateArgs = @()
if ($Serial) {
  $stateArgs += @("-s", $Serial)
}
$state = (& $Adb @stateArgs get-state 2>$null).Trim()
if ($state -ne "device") {
  throw "ADB device is not ready: $state"
}

if (-not $BuildRoot.StartsWith($RepoRoot, [StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to build outside the repository: $BuildRoot"
}
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
$needsBuild = -not (Test-Path -LiteralPath $DexJar)
if (-not $needsBuild) {
  $artifactTime = (Get-Item -LiteralPath $DexJar).LastWriteTimeUtc
  $needsBuild = @($Source, $AndroidJar, $UiAutomatorJar, $AndroidTestBaseJar) |
    Where-Object { (Get-Item -LiteralPath $_).LastWriteTimeUtc -gt $artifactTime } |
    Select-Object -First 1
}
if ($needsBuild) {
  if (Test-Path -LiteralPath $Classes) {
    Remove-Item -LiteralPath $Classes -Recurse -Force
  }
  if (Test-Path -LiteralPath $Dex) {
    Remove-Item -LiteralPath $Dex -Recurse -Force
  }
  New-Item -ItemType Directory -Path $Classes, $Dex -Force | Out-Null

  & $Javac `
    -encoding UTF-8 `
    -source 8 `
    -target 8 `
    -classpath "$AndroidJar;$UiAutomatorJar;$AndroidTestBaseJar" `
    -d $Classes `
    $Source
  if ($LASTEXITCODE -ne 0) {
    throw "javac failed with exit code $LASTEXITCODE"
  }

  & $Jar cf $ClassJar -C $Classes .
  if ($LASTEXITCODE -ne 0) {
    throw "jar failed with exit code $LASTEXITCODE"
  }
  & $D8 --lib $AndroidJar --lib $UiAutomatorJar --lib $AndroidTestBaseJar --output $Dex $ClassJar
  if ($LASTEXITCODE -ne 0) {
    throw "d8 failed with exit code $LASTEXITCODE"
  }
  & $Jar cf $DexJar -C $Dex classes.dex
  if ($LASTEXITCODE -ne 0) {
    throw "dex jar creation failed with exit code $LASTEXITCODE"
  }
}

$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Text))
try {
  & $Adb @stateArgs push $DexJar $RemoteJar | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "adb push failed with exit code $LASTEXITCODE"
  }
  $testOutput = & $Adb @stateArgs shell uiautomator runtest $RemoteJar `
    -c com.exitguide.tools.UnicodeInputTest `
    -e textB64 $encoded `
    -e packageName $PackageName `
    -e className $ClassName `
    -e instance $Instance `
    -e outputFormat simple 2>&1
  $testExitCode = $LASTEXITCODE
  $testOutput | Write-Output
  $testText = $testOutput -join "`n"
  if ($testExitCode -ne 0 -or $testText -match "FAILURES!!!|There (?:was|were) [1-9][0-9]* failure") {
    throw "UIAutomator Unicode input failed with exit code $LASTEXITCODE"
  }
}
finally {
  & $Adb @stateArgs shell rm -f $RemoteJar | Out-Null
}

Write-Output "unicode_text_set_ok"
