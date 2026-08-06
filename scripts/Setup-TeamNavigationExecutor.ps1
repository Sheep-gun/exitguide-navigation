[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SshKeyPath,
    [string]$N100Host = "100.77.172.25",
    [string]$N100User = "exitguide",
    [int]$LocalForwardPort = 18104,
    [int]$N100ApiPort = 8100,
    [int]$DeviceApiPort = 8100,
    [string]$SshPath = "",
    [string]$AdbPath = "",
    [string]$ApkPath = "",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$expectedSplitSha256 = "ae3b7e0a0ea9f5fd392f173c33d005e43263aabba3c70ad37d40619662a620b0"
$bundleRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$artifactDirectory = Join-Path $bundleRoot ".artifacts"
$tunnelStatePath = Join-Path $artifactDirectory "team-navigation-tunnel-$LocalForwardPort.json"
$installScript = Join-Path $PSScriptRoot "Install-NavigationExecutor.ps1"

function Resolve-SshExecutable {
    if (-not [string]::IsNullOrWhiteSpace($SshPath)) {
        return (Resolve-Path -LiteralPath $SshPath).Path
    }
    $systemSsh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    if (Test-Path -LiteralPath $systemSsh -PathType Leaf) {
        return (Resolve-Path -LiteralPath $systemSsh).Path
    }
    $command = Get-Command ssh.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }
    throw "OpenSSH ssh.exe was not found. Install the Windows OpenSSH Client."
}

function Resolve-AdbExecutable {
    if (-not [string]::IsNullOrWhiteSpace($AdbPath)) {
        return (Resolve-Path -LiteralPath $AdbPath).Path
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
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "adb.exe was not found. Install Android platform-tools or pass -AdbPath."
}

function Resolve-ExecutorApk {
    if (-not [string]::IsNullOrWhiteSpace($ApkPath)) {
        return (Resolve-Path -LiteralPath $ApkPath).Path
    }
    $bundleApk = Join-Path $bundleRoot "navigation-executor-debug.apk"
    if (Test-Path -LiteralPath $bundleApk -PathType Leaf) {
        return (Resolve-Path -LiteralPath $bundleApk).Path
    }
    $repoApk = Join-Path $bundleRoot "apps\android-executor\app\build\outputs\apk\debug\app-debug.apk"
    if (Test-Path -LiteralPath $repoApk -PathType Leaf) {
        return (Resolve-Path -LiteralPath $repoApk).Path
    }
    throw "Navigation Executor APK was not found. Pass -ApkPath."
}

function Get-LocalNavigationStatus {
    try {
        return Invoke-RestMethod `
            -Uri "http://127.0.0.1:$LocalForwardPort/v1/navigation/status" `
            -TimeoutSec 3
    } catch {
        return $null
    }
}

function Assert-NavigationStatus {
    param([object]$Status)
    if ($null -eq $Status -or $Status.ready -ne $true) {
        throw "The N100 Navigation API did not report ready=true through the local tunnel."
    }
    if ($Status.public_prior.enabled -ne $true) {
        throw "The fixed B runtime is not active: public_prior.enabled is not true."
    }
    if ($Status.dataset_split.sha256 -ne $expectedSplitSha256) {
        throw "The N100 split manifest does not match the current 11-app collection split."
    }
    if ($Status.dataset_split.counts.collection -ne 11 `
            -or $Status.dataset_split.counts.validation -ne 0 `
            -or $Status.dataset_split.counts.locked_holdout -ne 0) {
        throw "The N100 split counts are not collection=11, validation=0, locked_holdout=0."
    }
}

if (-not (Test-Path -LiteralPath $installScript -PathType Leaf)) {
    throw "Install-NavigationExecutor.ps1 must remain next to this setup script."
}
$resolvedKey = (Resolve-Path -LiteralPath $SshKeyPath).Path
$resolvedSsh = Resolve-SshExecutable
$resolvedAdb = Resolve-AdbExecutable
$resolvedApk = Resolve-ExecutorApk
New-Item -ItemType Directory -Path $artifactDirectory -Force | Out-Null

$deviceLines = @(& $resolvedAdb devices | Select-String -Pattern "\sdevice(?:\s|$)")
if ($LASTEXITCODE -ne 0 -or $deviceLines.Count -ne 1) {
    throw "Exactly one authorized ADB device is required; found $($deviceLines.Count)."
}
$deviceSerial = (($deviceLines[0].Line -split "\s+")[0]).Trim()

$status = Get-LocalNavigationStatus
$tunnelProcess = $null
if ($null -eq $status) {
    $forward = "127.0.0.1:${LocalForwardPort}:${N100Host}:${N100ApiPort}"
    $target = "$N100User@$N100Host"
    $sshArguments = @(
        "-N",
        "-L", $forward,
        "-i", ('"' + $resolvedKey + '"'),
        "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=20",
        "-o", "ServerAliveCountMax=3",
        $target
    ) -join " "
    $tunnelProcess = Start-Process `
        -FilePath $resolvedSsh `
        -ArgumentList $sshArguments `
        -WindowStyle Hidden `
        -PassThru

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(20)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if ($tunnelProcess.HasExited) {
            throw "The SSH tunnel exited before the Navigation API became reachable. Verify Tailscale and the team member's own SSH key."
        }
        $status = Get-LocalNavigationStatus
        if ($null -ne $status) {
            break
        }
        Start-Sleep -Milliseconds 500
    }
}
Assert-NavigationStatus $status

& $resolvedAdb -s $deviceSerial reverse "tcp:$DeviceApiPort" "tcp:$LocalForwardPort" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "adb reverse failed."
}
$reverseList = (& $resolvedAdb -s $deviceSerial reverse --list) -join "`n"
if ($reverseList -notmatch "tcp:$DeviceApiPort\s+tcp:$LocalForwardPort") {
    throw "adb reverse was not installed for the Navigation API."
}

$installArguments = @{
    AdbPath = $resolvedAdb
    ApkPath = $resolvedApk
    NavigationApiBaseUrl = "http://127.0.0.1:$DeviceApiPort"
}
if ($SkipInstall) {
    $installArguments.SkipInstall = $true
}
$installJson = & $installScript @installArguments
$installResult = ($installJson -join "`n") | ConvertFrom-Json

$tunnelPid = $null
if ($null -ne $tunnelProcess) {
    $tunnelPid = $tunnelProcess.Id
}
[ordered]@{
    status = "ready"
    architecture = "B_fixed"
    n100_api_ready = $true
    public_prior_enabled = $true
    split_manifest_sha256 = $status.dataset_split.sha256
    ssh_tunnel_reused = $null -eq $tunnelProcess
    ssh_tunnel_pid = $tunnelPid
    adb_device_serial = $deviceSerial
    adb_reverse = "tcp:$DeviceApiPort -> host tcp:$LocalForwardPort"
    apk_path = $resolvedApk
    apk_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedApk).Hash
    accessibility_enabled = $installResult.accessibility_enabled
    accessibility_bound = $installResult.accessibility_bound
    nodes = $installResult.nodes
    candidates = $installResult.candidates
    navigation_api_ready = $installResult.navigation_api_ready
    adb_disconnect_auto_resume = $false
} | ConvertTo-Json -Depth 5 | Tee-Object -FilePath $tunnelStatePath
