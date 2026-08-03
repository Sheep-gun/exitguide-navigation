[CmdletBinding()]
param(
    [string]$AdbPath = "",

    [string]$ApkPath = "apps/android-executor/app/build/outputs/apk/debug/app-debug.apk",

    [int]$BindTimeoutSeconds = 60,

    [int]$DiagnosticTimeoutSeconds = 30,

    [string]$NavigationApiBaseUrl = "",

    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$package = "com.exitguide.navigation.executor"
$service = "$package/$package.ExitGuideAccessibilityService"
$activity = "$package/.MainActivity"
$diagnosticReceiver = "$package/.ExecutorDiagnosticReceiver"
$diagnosticAction = "$package.DIAGNOSTIC_SNAPSHOT"

function Resolve-AdbExecutable {
    param([string]$RequestedPath)

    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        return (Resolve-Path -LiteralPath $RequestedPath).Path
    }

    $candidates = @()
    $command = Get-Command adb.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        $candidates += $command.Source
    }
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $candidates += Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
    }
    if (-not [string]::IsNullOrWhiteSpace($env:ANDROID_SDK_ROOT)) {
        $candidates += Join-Path $env:ANDROID_SDK_ROOT "platform-tools\adb.exe"
    }
    if (-not [string]::IsNullOrWhiteSpace($env:ANDROID_HOME)) {
        $candidates += Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "adb.exe was not found. Install Android platform-tools or pass -AdbPath."
}

$resolvedAdb = Resolve-AdbExecutable $AdbPath
$resolvedApk = $null
if (-not $SkipInstall) {
    $resolvedApk = (Resolve-Path -LiteralPath $ApkPath).Path
} elseif (Test-Path -LiteralPath $ApkPath -PathType Leaf) {
    $resolvedApk = (Resolve-Path -LiteralPath $ApkPath).Path
}

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
    # Samsung may wrap long lines inside the service record.
    $compact = $dump -replace "\s", ""
    return $compact.Contains(
        "id=com.exitguide.navigation.executor/.ExitGuideAccessibilityService"
    )
}

function Wait-ExecutorBound {
    param([int]$TimeoutSeconds)
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if (Test-ExecutorBound) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Enable-ExecutorAccessibility {
    $enabled = @(Get-EnabledAccessibilityServices)
    if ($enabled -notcontains $service) {
        $enabled += $service
    }
    $enabled = @($enabled | Sort-Object -Unique)
    $enabledValue = $enabled -join ":"
    Invoke-Adb shell settings put secure enabled_accessibility_services $enabledValue | Out-Null
    Invoke-Adb shell settings put secure accessibility_enabled 1 | Out-Null

    if (Wait-ExecutorBound $BindTimeoutSeconds) {
        return $enabled
    }

    # Re-register only ExitGuide; preserve every other enabled service.
    $withoutExecutor = @($enabled | Where-Object { $_ -ne $service })
    Invoke-Adb shell settings put secure enabled_accessibility_services ($withoutExecutor -join ":") | Out-Null
    Start-Sleep -Milliseconds 300
    Invoke-Adb shell settings put secure enabled_accessibility_services $enabledValue | Out-Null
    Invoke-Adb shell settings put secure accessibility_enabled 1 | Out-Null

    if (-not (Wait-ExecutorBound $BindTimeoutSeconds)) {
        throw "ExitGuide AccessibilityService did not bind within $BindTimeoutSeconds seconds after an automatic rebind retry."
    }
    return $enabled
}

function Invoke-ExecutorDiagnostic {
    $requestId = [Guid]::NewGuid().ToString("N")
    Invoke-Adb -Arguments @("shell", "am", "start", "-W", "-n", $activity) | Out-Null
    Start-Sleep -Milliseconds 800

    $arguments = @(
        "shell", "am", "broadcast", "--receiver-foreground",
        "-a", $diagnosticAction,
        "-n", $diagnosticReceiver,
        "--es", "request_id", $requestId
    )
    if (-not [string]::IsNullOrWhiteSpace($NavigationApiBaseUrl)) {
        $arguments += @("--es", "api_base_url", $NavigationApiBaseUrl)
    }
    Invoke-Adb @arguments | Out-Null

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($DiagnosticTimeoutSeconds)
    $snapshotMatch = $null
    $apiReady = $false
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        $logs = (
            Invoke-Adb -Arguments @(
                "logcat", "-d", "-v", "brief", "-s",
                "ExitGuideNavigationExecutor:I", "*:S"
            )
        ) -join "`n"
        $escaped = [Regex]::Escape($requestId)
        $snapshotMatch = [Regex]::Match(
            $logs,
            "diagnostic_snapshot request_id=$escaped package=(\S*) nodes=(\d+) candidates=(\d+)"
        )
        $apiReady = $logs -match "diagnostic_api request_id=$escaped ready=true"
        if ($snapshotMatch.Success -and $apiReady) {
            break
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $snapshotMatch.Success) {
        throw "Executor diagnostic did not return an Accessibility snapshot."
    }
    $nodeCount = [int]$snapshotMatch.Groups[2].Value
    $candidateCount = [int]$snapshotMatch.Groups[3].Value
    if ($nodeCount -lt 1 -or $candidateCount -lt 1) {
        throw "Executor diagnostic returned nodes=$nodeCount candidates=$candidateCount; candidate extraction is not ready."
    }
    if (-not $apiReady) {
        throw "Executor diagnostic could not reach a ready Navigation API. Verify the existing adb reverse/tunnel or pass -NavigationApiBaseUrl."
    }

    return [pscustomobject]@{
        request_id = $requestId
        observed_package = $snapshotMatch.Groups[1].Value
        node_count = $nodeCount
        candidate_count = $candidateCount
        navigation_api_ready = $true
    }
}

$devices = @(Invoke-Adb devices | Select-String -Pattern "\sdevice(?:\s|$)")
if ($devices.Count -ne 1) {
    throw "exactly one authorized ADB device is required; found $($devices.Count)"
}

# `install -r` preserves app data and the enabled-service grant whenever the OS
# permits it. The explicit restoration below handles vendors that disable the
# service while replacing an APK signed with the same development key.
if (-not $SkipInstall) {
    Invoke-Adb install -r $resolvedApk | Out-Host
}

$enabled = @(Enable-ExecutorAccessibility)
Invoke-Adb shell svc power stayon true | Out-Null
$diagnostic = Invoke-ExecutorDiagnostic

[pscustomobject]@{
    adb = $resolvedAdb
    apk = $resolvedApk
    package = $package
    accessibility_enabled = $true
    accessibility_bound = $true
    preserved_service_count = $enabled.Count
    node_collection_ready = $diagnostic.node_count -gt 0
    candidate_id_generation_ready = $diagnostic.candidate_count -gt 0
    navigation_api_ready = $diagnostic.navigation_api_ready
    diagnostic_request_id = $diagnostic.request_id
    observed_package = $diagnostic.observed_package
    nodes = $diagnostic.node_count
    candidates = $diagnostic.candidate_count
} | ConvertTo-Json
