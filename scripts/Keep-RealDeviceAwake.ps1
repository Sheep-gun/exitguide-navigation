[CmdletBinding()]
param(
    [string]$Serial = "R3CY204GDVE",
    [string]$Adb = "C:\Users\YangGeon\ExitGuideAndroidSdk\platform-tools\adb.exe",
    [ValidateRange(60, 300)]
    [int]$IntervalSeconds = 60,
    [ValidateRange(0, 1439)]
    [int]$SafeTouchX = 720,
    [ValidateRange(0, 31)]
    [int]$SafeTouchY = 8,
    [string]$AuditLogPath = "",
    [ValidateRange(0, 2147483647)]
    [int]$MaxCycles = 0
)

$ErrorActionPreference = "Stop"
$ExpectedSerial = "R3CY204GDVE"
$AuditTargetClass = "system_top_safe"

if ($Serial.StartsWith("emulator-", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Emulator serials are forbidden for the physical-device keep-alive."
}
if ($Serial -ne $ExpectedSerial) {
    throw "The physical-device serial must be $ExpectedSerial."
}
if (-not (Test-Path -LiteralPath $Adb)) {
    throw "adb was not found at: $Adb"
}

if ([string]::IsNullOrWhiteSpace($AuditLogPath)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
    $AuditLogPath = Join-Path $RepoRoot ".artifacts\runtime\real-device-keepalive.jsonl"
}
$AuditDirectory = Split-Path -Parent $AuditLogPath
if (-not [string]::IsNullOrWhiteSpace($AuditDirectory)) {
    New-Item -ItemType Directory -Path $AuditDirectory -Force | Out-Null
}

function Get-ExpectedDeviceState {
    # `adb devices` is a host-side query.  Parse only the exact expected serial;
    # another attached phone or emulator must never become the keep-alive target.
    try {
        $DeviceLines = @(& $Adb devices 2>$null)
        $AdbExitCode = $LASTEXITCODE
    }
    catch {
        return "disconnected"
    }

    if ($AdbExitCode -ne 0 -or $null -eq $DeviceLines) {
        return "disconnected"
    }

    foreach ($DeviceLineValue in $DeviceLines) {
        if ($null -eq $DeviceLineValue) {
            continue
        }
        $DeviceLine = ([string]$DeviceLineValue).Trim()
        if ([string]::IsNullOrWhiteSpace($DeviceLine)) {
            continue
        }
        $Parts = @($DeviceLine -split "\s+")
        if ($Parts.Count -lt 2 -or $Parts[0] -cne $ExpectedSerial) {
            continue
        }

        switch ($Parts[1].ToLowerInvariant()) {
            "device" { return "device" }
            "offline" { return "offline" }
            "unauthorized" { return "unauthorized" }
            default { return "disconnected" }
        }
    }

    return "disconnected"
}

function Invoke-AdbKeepAliveStep {
    param([string[]]$CommandArguments)

    try {
        & $Adb @CommandArguments *> $null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Write-KeepAliveAuditRecord {
    param(
        [string]$DeviceState,
        [bool]$InputAttempted,
        [bool]$StayAwakeSucceeded,
        [bool]$WakeSucceeded,
        [bool]$SafeTapSucceeded
    )

    # Deliberately omit the device serial, coordinates, command output, screen
    # contents, package names, and UI data.  This log is operational metadata only.
    $Record = [ordered]@{
        schema_version = "egl-real-device-keepalive-audit.v1"
        timestamp_utc = [DateTimeOffset]::UtcNow.ToString("o")
        device_state = $DeviceState
        input_attempted = $InputAttempted
        stay_awake_succeeded = $StayAwakeSucceeded
        wake_succeeded = $WakeSucceeded
        safe_tap_succeeded = $SafeTapSucceeded
        target_class = $AuditTargetClass
    }
    Add-Content -LiteralPath $AuditLogPath -Value ($Record | ConvertTo-Json -Compress) -Encoding UTF8
}

$CycleCount = 0
while ($true) {
    $CycleStartedAt = [DateTimeOffset]::UtcNow
    $State = Get-ExpectedDeviceState
    $InputAttempted = $false
    $StayAwakeSucceeded = $false
    $WakeSucceeded = $false
    $SafeTapSucceeded = $false

    if ($State -eq "device") {
        # Keep the display awake while USB is connected, wake it if needed,
        # then touch the verified system-status-bar strip.  The fixed target
        # is outside this device's app content area and never represents an
        # app menu, confirmation, purchase, deletion, or navigation action.
        $InputAttempted = $true
        $StayAwakeSucceeded = Invoke-AdbKeepAliveStep @("-s", $Serial, "shell", "svc", "power", "stayon", "usb")
        $WakeSucceeded = Invoke-AdbKeepAliveStep @("-s", $Serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
        $SafeTapSucceeded = Invoke-AdbKeepAliveStep @("-s", $Serial, "shell", "input", "tap", [string]$SafeTouchX, [string]$SafeTouchY)
    }

    Write-KeepAliveAuditRecord `
        -DeviceState $State `
        -InputAttempted $InputAttempted `
        -StayAwakeSucceeded $StayAwakeSucceeded `
        -WakeSucceeded $WakeSucceeded `
        -SafeTapSucceeded $SafeTapSucceeded

    $CycleCount += 1
    if ($MaxCycles -gt 0 -and $CycleCount -ge $MaxCycles) {
        break
    }

    # Keep the interval measured between touch attempts, not "ADB work plus
    # IntervalSeconds".  The previous fixed sleep produced roughly 61-second
    # gaps on the physical device because the three ADB calls take about one
    # second.  Subtracting that work time keeps the requested 60-second cadence.
    $ElapsedMilliseconds = ([DateTimeOffset]::UtcNow - $CycleStartedAt).TotalMilliseconds
    $RemainingMilliseconds = [Math]::Max(
        0,
        [int][Math]::Round(($IntervalSeconds * 1000) - $ElapsedMilliseconds)
    )
    if ($RemainingMilliseconds -gt 0) {
        Start-Sleep -Milliseconds $RemainingMilliseconds
    }
}
