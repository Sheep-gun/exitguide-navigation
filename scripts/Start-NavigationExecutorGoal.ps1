[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AppPackage,

    [Parameter(Mandatory = $true)]
    [string]$Goal,

    [string]$NavigationApiBaseUrl = "http://127.0.0.1:8100",

    [string]$CollectorAlias = "codex-yanggeon",

    [ValidateSet("logged_in", "logged_out", "unknown")]
    [string]$AccountState = "unknown",

    [ValidateSet("none", "trial", "active", "paused", "cancelled", "unknown")]
    [string]$ServiceState = "unknown",

    [string]$StartSurface = "app_home",

    [ValidateSet("ready", "not_ready", "unknown")]
    [string]$PreconditionStatus = "ready",

    [string]$ResetMethod = "app_relaunch",

    [bool]$ResetVerified = $true,

    [ValidateSet("human", "codex", "system", "unknown")]
    [string]$PreconditionSource = "human",

    [ValidateRange(0.0, 1.0)]
    [float]$PreconditionConfidence = 0.95,

    [string]$AdbPath = ""
)

$ErrorActionPreference = "Stop"
$executorPackage = "com.exitguide.navigation.executor"
$receiver = "$executorPackage/.ExecutorDiagnosticReceiver"
$startAction = "$executorPackage.ADB_START_NAVIGATION"
$serviceId = "id=$executorPackage/.ExitGuideAccessibilityService"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$monitorScript = Join-Path $PSScriptRoot "Monitor-NavigationExecutorDevice.ps1"
$monitorDirectory = Join-Path $repoRoot ".artifacts"
$monitorTokenPath = Join-Path $monitorDirectory "navigation-executor-device-monitor.token"
$monitorStatePath = Join-Path $monitorDirectory "navigation-executor-device-state.json"

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

function ConvertTo-AdbShellLiteral {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value.Contains("`0") -or $Value.Contains("`r") -or $Value.Contains("`n")) {
        throw "ADB shell string extras cannot contain NUL or newline characters."
    }
    # `adb shell` joins its host arguments before the Android shell parses them.
    # Preserve whitespace and prevent shell expansion with a POSIX single-quoted literal.
    $singleQuote = [string][char]39
    $doubleQuote = [string][char]34
    $escapedSingleQuote = $singleQuote + $doubleQuote + $singleQuote + $doubleQuote + $singleQuote
    return $singleQuote + $Value.Replace($singleQuote, $escapedSingleQuote) + $singleQuote
}

$devices = @(Invoke-Adb @("devices") | Select-String -Pattern "\sdevice(?:\s|$)")
if ($devices.Count -ne 1) {
    throw "exactly one authorized ADB device is required; found $($devices.Count)"
}
$deviceSerial = (($devices[0].Line -split "\s+")[0]).Trim()

$compactAccessibility = ((Invoke-Adb @("shell", "dumpsys", "accessibility")) -join "`n") -replace "\s", ""
if (-not $compactAccessibility.Contains($serviceId)) {
    throw "ExitGuide AccessibilityService is not bound. Run scripts/Install-NavigationExecutor.ps1 first."
}

$installed = (Invoke-Adb @("shell", "pm", "path", $AppPackage)) -join ""
if (-not $installed.Contains("package:")) {
    throw "target app is not installed: $AppPackage"
}

# An external settings/browser activity can remain on top of the target app's
# task. Force-stopping only the target package preserves its data and login.
# Resolve the package's launcher activity at runtime and clear the stale task;
# no coordinate or app-specific activity name is used.
Invoke-Adb @("shell", "am", "force-stop", $AppPackage) | Out-Null
Start-Sleep -Milliseconds 300
$launcherComponent = (
    (Invoke-Adb @(
        "shell", "cmd", "package", "resolve-activity", "--brief",
        "-a", "android.intent.action.MAIN",
        "-c", "android.intent.category.LAUNCHER",
        $AppPackage
    )) | Select-Object -Last 1
).Trim()
$componentPattern = "^" + [Regex]::Escape($AppPackage) + "/[A-Za-z0-9._`$]+$"
if ($launcherComponent -notmatch $componentPattern) {
    throw "could not resolve a safe launcher activity for: $AppPackage"
}
$launchCommand = @(
    "am", "start", "-W", "--activity-clear-task",
    "-a", "android.intent.action.MAIN",
    "-c", "android.intent.category.LAUNCHER",
    "-n", (ConvertTo-AdbShellLiteral $launcherComponent)
) -join " "
Invoke-Adb @("shell", $launchCommand) | Out-Null
$foregroundDeadline = [DateTimeOffset]::UtcNow.AddSeconds(8)
$foregroundConfirmed = $false
while ([DateTimeOffset]::UtcNow -lt $foregroundDeadline) {
    $activityDump = (Invoke-Adb @("shell", "dumpsys", "activity", "activities")) -join "`n"
    $topResumed = @(
        $activityDump -split "`n" | Where-Object { $_ -match "topResumedActivity" }
    )
    if ($topResumed -match [Regex]::Escape("$AppPackage/")) {
        $foregroundConfirmed = $true
        break
    }
    Start-Sleep -Milliseconds 300
}
if (-not $foregroundConfirmed) {
    throw "target app did not become the foreground package: $AppPackage"
}

$broadcastCommand = @(
    "am", "broadcast", "--receiver-foreground",
    "-a", $startAction,
    "-n", $receiver,
    "--es", "goal", (ConvertTo-AdbShellLiteral $Goal),
    "--es", "api_base_url", (ConvertTo-AdbShellLiteral $NavigationApiBaseUrl),
    "--es", "collector_alias", (ConvertTo-AdbShellLiteral $CollectorAlias),
    "--es", "account_state", (ConvertTo-AdbShellLiteral $AccountState),
    "--es", "service_state", (ConvertTo-AdbShellLiteral $ServiceState),
    "--es", "start_surface", (ConvertTo-AdbShellLiteral $StartSurface),
    "--es", "precondition_status", (ConvertTo-AdbShellLiteral $PreconditionStatus),
    "--es", "reset_method", (ConvertTo-AdbShellLiteral $ResetMethod),
    "--ez", "reset_verified", $ResetVerified.ToString().ToLowerInvariant(),
    "--es", "precondition_source", (ConvertTo-AdbShellLiteral $PreconditionSource),
    "--ef", "precondition_confidence", $PreconditionConfidence.ToString([Globalization.CultureInfo]::InvariantCulture)
) -join " "
Invoke-Adb @("shell", $broadcastCommand) | Out-Null

# Maintain a short ADB lease while this collection episode is active. If the
# exact device disappears, the hidden monitor stops heartbeats and records a
# paused marker. The Executor checks the lease again before every decision and
# before executing a delayed model response, so it cannot silently resume.
New-Item -ItemType Directory -Path $monitorDirectory -Force | Out-Null
$runToken = [Guid]::NewGuid().ToString("N")
Set-Content -LiteralPath $monitorTokenPath -Value $runToken -Encoding UTF8
[ordered]@{
    status = "starting"
    reason = "awaiting_adb_heartbeat"
    device_serial = $deviceSerial
    updated_at = [DateTimeOffset]::Now.ToString("o")
    auto_resume = $false
} | ConvertTo-Json | Set-Content -LiteralPath $monitorStatePath -Encoding UTF8
$monitorArguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", ('"' + $monitorScript + '"'),
    "-AdbPath", ('"' + $adb + '"'),
    "-DeviceSerial", $deviceSerial,
    "-RunToken", $runToken,
    "-TokenPath", ('"' + $monitorTokenPath + '"'),
    "-StatePath", ('"' + $monitorStatePath + '"')
) -join " "
Start-Process -FilePath "powershell.exe" -ArgumentList $monitorArguments -WindowStyle Hidden | Out-Null

[pscustomobject]@{
    app_package = $AppPackage
    navigation_api = $NavigationApiBaseUrl
    accessibility_bound = $true
    launch_method = "resolved_package_launcher_clear_task_without_coordinates"
    foreground_package_confirmed = $true
    navigation_started = $true
    adb_device_monitor = $true
    adb_auto_resume = $false
    monitor_state = $monitorStatePath
    collector_alias = $CollectorAlias
    account_state = $AccountState
    service_state = $ServiceState
    start_surface = $StartSurface
    precondition_status = $PreconditionStatus
    reset_method = $ResetMethod
    reset_verified = $ResetVerified
    precondition_source = $PreconditionSource
    precondition_confidence = $PreconditionConfidence
} | ConvertTo-Json
