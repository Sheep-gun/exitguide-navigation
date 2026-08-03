[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AdbPath,

    [string]$ApkPath = "apps/android-executor/app/build/outputs/apk/debug/app-debug.apk",

    [int]$BindTimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"
$service = "com.exitguide.navigation.executor/com.exitguide.navigation.executor.ExitGuideAccessibilityService"
$resolvedAdb = (Resolve-Path -LiteralPath $AdbPath).Path
$resolvedApk = (Resolve-Path -LiteralPath $ApkPath).Path

function Invoke-Adb {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & $resolvedAdb @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "adb failed ($LASTEXITCODE): $($Arguments -join ' ')`n$($output -join [Environment]::NewLine)"
    }
    return $output
}

function Get-EnabledAccessibilityServices {
    $raw = ((Invoke-Adb shell settings get secure enabled_accessibility_services) -join "").Trim()
    if ([string]::IsNullOrWhiteSpace($raw) -or $raw -eq "null") {
        return @()
    }
    return @($raw.Split(":", [System.StringSplitOptions]::RemoveEmptyEntries))
}

function Test-ExecutorBound {
    $dump = (Invoke-Adb shell dumpsys accessibility) -join "`n"
    return $dump -match (
        "(?s)Bound services:\{.*?Service\[label=ExitGuide 후보 기반 탐색, " +
        "id=com\.exitguide\.navigation\.executor/(?:\.|com\.exitguide\.navigation\.executor\.)" +
        "ExitGuideAccessibilityService"
    )
}

$devices = @(Invoke-Adb devices | Select-String -Pattern "\sdevice(?:\s|$)")
if ($devices.Count -ne 1) {
    throw "exactly one authorized ADB device is required; found $($devices.Count)"
}

# `install -r` preserves app data and the user's existing grant whenever the OS
# allows it. The explicit restore below handles vendors that disable the service
# while replacing an APK signed with the same development key.
Invoke-Adb install -r $resolvedApk | Out-Host

$enabled = @(Get-EnabledAccessibilityServices)
if ($enabled -notcontains $service) {
    $enabled += $service
}
$enabled = @($enabled | Sort-Object -Unique)
$enabledValue = $enabled -join ":"
Invoke-Adb shell settings put secure enabled_accessibility_services $enabledValue | Out-Null
Invoke-Adb shell settings put secure accessibility_enabled 1 | Out-Null
Invoke-Adb shell svc power stayon true | Out-Null

$deadline = [DateTimeOffset]::UtcNow.AddSeconds($BindTimeoutSeconds)
while ([DateTimeOffset]::UtcNow -lt $deadline) {
    if (Test-ExecutorBound) {
        [pscustomobject]@{
            apk = $resolvedApk
            package = "com.exitguide.navigation.executor"
            accessibility_enabled = $true
            accessibility_bound = $true
            preserved_service_count = $enabled.Count
        } | ConvertTo-Json
        exit 0
    }
    Start-Sleep -Milliseconds 500
}

# Re-register only ExitGuide if the vendor retained the setting but did not
# rebind the replaced service. Other enabled services remain in the list.
$withoutExecutor = @($enabled | Where-Object { $_ -ne $service })
$temporaryValue = $withoutExecutor -join ":"
Invoke-Adb shell settings put secure enabled_accessibility_services $temporaryValue | Out-Null
Start-Sleep -Milliseconds 250
Invoke-Adb shell settings put secure enabled_accessibility_services $enabledValue | Out-Null

$deadline = [DateTimeOffset]::UtcNow.AddSeconds($BindTimeoutSeconds)
while ([DateTimeOffset]::UtcNow -lt $deadline) {
    if (Test-ExecutorBound) {
        [pscustomobject]@{
            apk = $resolvedApk
            package = "com.exitguide.navigation.executor"
            accessibility_enabled = $true
            accessibility_bound = $true
            preserved_service_count = $enabled.Count
            rebind_required = $true
        } | ConvertTo-Json
        exit 0
    }
    Start-Sleep -Milliseconds 500
}

throw "ExitGuide AccessibilityService did not bind within $BindTimeoutSeconds seconds"
