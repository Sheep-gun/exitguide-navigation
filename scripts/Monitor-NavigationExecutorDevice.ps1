[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$AdbPath,
    [Parameter(Mandatory = $true)][string]$DeviceSerial,
    [Parameter(Mandatory = $true)][string]$RunToken,
    [Parameter(Mandatory = $true)][string]$TokenPath,
    [Parameter(Mandatory = $true)][string]$StatePath,
    [int]$PollIntervalSeconds = 5
)

$ErrorActionPreference = "Stop"
$receiver = "com.exitguide.navigation.executor/.ExecutorDiagnosticReceiver"
$heartbeatAction = "com.exitguide.navigation.executor.ADB_HEARTBEAT"
$heartbeatAcceptedResult = 73

function Write-MonitorState {
    param([string]$Status, [string]$Reason)
    $payload = [ordered]@{
        status = $Status
        reason = $Reason
        device_serial = $DeviceSerial
        updated_at = [DateTimeOffset]::Now.ToString("o")
        auto_resume = $false
    } | ConvertTo-Json
    Set-Content -LiteralPath $StatePath -Value $payload -Encoding UTF8
}

function Test-CurrentToken {
    if (-not (Test-Path -LiteralPath $TokenPath -PathType Leaf)) {
        return $false
    }
    return ((Get-Content -LiteralPath $TokenPath -Raw -Encoding UTF8).Trim() -eq $RunToken)
}

function Pause-ForDisconnect {
    param([string]$Reason)
    Write-MonitorState -Status "paused" -Reason $Reason
    if (Test-CurrentToken) {
        Remove-Item -LiteralPath $TokenPath -Force
    }
}

Write-MonitorState -Status "connected" -Reason "adb_heartbeat_active"
while (Test-CurrentToken) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $state = & $AdbPath -s $DeviceSerial get-state 2>&1
    $stateExit = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($stateExit -ne 0 -or (($state -join "").Trim() -ne "device")) {
        Pause-ForDisconnect -Reason "adb_disconnected"
        exit 0
    }

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $heartbeatOutput = & $AdbPath -s $DeviceSerial shell am broadcast --receiver-foreground `
        -a $heartbeatAction -n $receiver 2>&1
    $heartbeatExit = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    $heartbeatText = ($heartbeatOutput -join "`n")
    if ($heartbeatExit -ne 0 -or $heartbeatText -notmatch "result=$heartbeatAcceptedResult(?:,|\s|$)") {
        Pause-ForDisconnect -Reason "adb_heartbeat_failed"
        exit 0
    }
    Start-Sleep -Seconds ([Math]::Max(2, $PollIntervalSeconds))
}

Write-MonitorState -Status "stopped" -Reason "navigation_stopped"
