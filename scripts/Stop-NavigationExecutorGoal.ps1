[CmdletBinding()]
param([string]$AdbPath = "")

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($AdbPath)) {
    $command = Get-Command adb.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        $AdbPath = $command.Source
    } else {
        $AdbPath = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
    }
}
$adb = (Resolve-Path -LiteralPath $AdbPath).Path
& $adb shell am broadcast --receiver-foreground `
    -a com.exitguide.navigation.executor.ADB_STOP_NAVIGATION `
    -n com.exitguide.navigation.executor/.ExecutorDiagnosticReceiver | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "failed to stop Navigation Executor"
}
Write-Output '{"navigation_stopped":true}'
