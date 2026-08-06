[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("click", "scroll", "back", "wait_and_observe", "stop_for_user")]
    [string]$Action,

    [string]$CandidateId = "",

    [ValidateSet("", "up", "down")]
    [string]$Direction = "",

    [Parameter(Mandatory = $true)]
    [string]$ReasonCodes,

    [Parameter(Mandatory = $true)]
    [string]$ReasonText,

    [ValidateSet("unreviewed", "provisional", "verified")]
    [string]$ReviewStatus = "provisional",

    [string]$AdbPath = "",

    [int]$ObserveTimeoutSeconds = 12
)

$ErrorActionPreference = "Stop"
$executorPackage = "com.exitguide.navigation.executor"
$receiver = "$executorPackage/.ExecutorDiagnosticReceiver"
$operatorAction = "$executorPackage.ADB_OPERATOR_ACTION"
if ([string]::IsNullOrWhiteSpace($AdbPath)) {
    $AdbPath = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
}
$adb = (Resolve-Path -LiteralPath $AdbPath).Path

function Read-LatestScreen {
    $text = (& $adb exec-out run-as $executorPackage `
        cat files/collector/latest-screen.json 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0) {
        throw "could not read the Executor latest screen: $text"
    }
    return ($text | ConvertFrom-Json)
}

function ConvertTo-AdbShellLiteral {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value.Contains("`0") -or $Value.Contains("`r") -or $Value.Contains("`n")) {
        throw "ADB shell string extras cannot contain NUL or newline characters."
    }
    $singleQuote = [string][char]39
    $doubleQuote = [string][char]34
    $escapedSingleQuote = $singleQuote + $doubleQuote + $singleQuote + $doubleQuote + $singleQuote
    return $singleQuote + $Value.Replace($singleQuote, $escapedSingleQuote) + $singleQuote
}

$before = Read-LatestScreen
if ($Action -eq "click") {
    if ([string]::IsNullOrWhiteSpace($CandidateId)) {
        throw "click requires CandidateId"
    }
    $known = @($before.screen.candidates | ForEach-Object { [string]$_.candidate_id })
    if ($known -notcontains $CandidateId) {
        throw "candidate is not present on the current screen: $CandidateId"
    }
} elseif (-not [string]::IsNullOrWhiteSpace($CandidateId)) {
    throw "$Action must not include CandidateId"
}
if ($Action -eq "scroll" -and $Direction -notin @("up", "down")) {
    throw "scroll requires Direction up or down"
}
if ($Action -ne "scroll" -and -not [string]::IsNullOrWhiteSpace($Direction)) {
    throw "$Action must not include Direction"
}

$commandId = [Guid]::NewGuid().ToString("N")
$parts = @(
    "am", "broadcast", "--receiver-foreground",
    "-a", $operatorAction,
    "-n", $receiver,
    "--es", "action_name", (ConvertTo-AdbShellLiteral $Action),
    "--es", "command_id", (ConvertTo-AdbShellLiteral $commandId),
    "--es", "expected_screen_fingerprint", (ConvertTo-AdbShellLiteral ([string]$before.screen_fingerprint)),
    "--es", "reason_codes", (ConvertTo-AdbShellLiteral $ReasonCodes),
    "--es", "reason_text", (ConvertTo-AdbShellLiteral $ReasonText),
    "--es", "review_status", (ConvertTo-AdbShellLiteral $ReviewStatus)
)
if ($Action -eq "click") {
    $parts += @("--es", "candidate_id", (ConvertTo-AdbShellLiteral $CandidateId))
}
if ($Action -eq "scroll") {
    $parts += @("--es", "direction", (ConvertTo-AdbShellLiteral $Direction))
}
$shellCommand = $parts -join " "
$broadcast = (& $adb shell $shellCommand 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0) {
    throw "operator action broadcast failed: $broadcast"
}

$deadline = [DateTimeOffset]::UtcNow.AddSeconds($ObserveTimeoutSeconds)
$after = $before
do {
    Start-Sleep -Milliseconds 350
    $after = Read-LatestScreen
    $captureAdvanced = [string]$after.captured_at -ne [string]$before.captured_at
    $sessionBound = -not [string]::IsNullOrWhiteSpace([string]$after.session_id)
    $stepAdvanced = [int]$after.step_ordinal -gt [int]$before.step_ordinal
    if ($captureAdvanced -and $sessionBound -and $stepAdvanced) {
        break
    }
} while ([DateTimeOffset]::UtcNow -lt $deadline)

[ordered]@{
    command_id = $commandId
    action = $Action
    candidate_id = if ($Action -eq "click") { $CandidateId } else { $null }
    direction = if ($Action -eq "scroll") { $Direction } else { $null }
    before_fingerprint = $before.screen_fingerprint
    after_fingerprint = $after.screen_fingerprint
    screen_changed = [string]$before.screen_fingerprint -ne [string]$after.screen_fingerprint
    session_id = $after.session_id
    step_ordinal = $after.step_ordinal
    app_package = $after.app_package
    captured_at = $after.captured_at
    candidates = @(
        $after.screen.candidates | ForEach-Object {
            [ordered]@{
                candidate_id = $_.candidate_id
                label = $_.label
                risk_level = $_.risk_level
                position_bucket = $_.position_bucket
            }
        }
    )
} | ConvertTo-Json -Depth 8
