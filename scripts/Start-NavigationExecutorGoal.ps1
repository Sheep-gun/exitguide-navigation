[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AppPackage,

    [Parameter(Mandatory = $true)]
    [string]$Goal,

    [string]$NavigationApiBaseUrl = "http://127.0.0.1:8100",

    [string]$AdbPath = ""
)

$ErrorActionPreference = "Stop"
$executorPackage = "com.exitguide.navigation.executor"
$receiver = "$executorPackage/.ExecutorDiagnosticReceiver"
$startAction = "$executorPackage.ADB_START_NAVIGATION"
$serviceId = "id=$executorPackage/.ExitGuideAccessibilityService"

function Resolve-AdbExecutable {
    if (-not [string]::IsNullOrWhiteSpace($AdbPath)) {
        return (Resolve-Path -LiteralPath $AdbPath).Path
    }
    $command = Get-Command adb.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }
    $candidate = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        return (Resolve-Path -LiteralPath $candidate).Path
    }
    throw "adb.exe was not found. Pass -AdbPath."
}

$adb = Resolve-AdbExecutable
function Invoke-Adb {
    param([string[]]$Arguments)
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & $adb @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    if ($exitCode -ne 0) {
        throw "adb failed ($exitCode): $($Arguments -join ' ')`n$($output -join [Environment]::NewLine)"
    }
    return $output
}

$devices = @(Invoke-Adb @("devices") | Select-String -Pattern "\sdevice(?:\s|$)")
if ($devices.Count -ne 1) {
    throw "exactly one authorized ADB device is required; found $($devices.Count)"
}

$compactAccessibility = ((Invoke-Adb @("shell", "dumpsys", "accessibility")) -join "`n") -replace "\s", ""
if (-not $compactAccessibility.Contains($serviceId)) {
    throw "ExitGuide AccessibilityService is not bound. Run scripts/Install-NavigationExecutor.ps1 first."
}

$installed = (Invoke-Adb @("shell", "pm", "path", $AppPackage)) -join ""
if (-not $installed.Contains("package:")) {
    throw "target app is not installed: $AppPackage"
}

# Launch through Android's package-aware launcher event. No coordinate is used.
Invoke-Adb @(
    "shell", "monkey", "-p", $AppPackage,
    "-c", "android.intent.category.LAUNCHER", "1"
) | Out-Null
Start-Sleep -Milliseconds 1200

Invoke-Adb @(
    "shell", "am", "broadcast", "--receiver-foreground",
    "-a", $startAction,
    "-n", $receiver,
    "--es", "goal", $Goal,
    "--es", "api_base_url", $NavigationApiBaseUrl
) | Out-Null

[pscustomobject]@{
    app_package = $AppPackage
    navigation_api = $NavigationApiBaseUrl
    accessibility_bound = $true
    launch_method = "package_launcher_event_without_coordinates"
    navigation_started = $true
} | ConvertTo-Json
