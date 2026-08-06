[CmdletBinding()]
param(
    [string]$AdbPath = "",
    [switch]$Raw
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($AdbPath)) {
    $AdbPath = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
}
$adb = (Resolve-Path -LiteralPath $AdbPath).Path
$json = (& $adb exec-out run-as com.exitguide.navigation.executor `
    cat files/collector/latest-screen.json 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0) {
    throw "could not read the Executor latest screen: $json"
}
if ($Raw) {
    $json
    exit 0
}

$payload = $json | ConvertFrom-Json
[ordered]@{
    captured_at = $payload.captured_at
    app_package = $payload.app_package
    app_version = $payload.app_version
    goal_text = $payload.goal_text
    session_id = $payload.session_id
    step_ordinal = $payload.step_ordinal
    screen_fingerprint = $payload.screen_fingerprint
    window_title = $payload.screen.window_title
    surface_type = $payload.screen.surface_type
    nodes = $payload.screen.nodes_captured
    candidates = @(
        $payload.screen.candidates | ForEach-Object {
            [ordered]@{
                candidate_id = $_.candidate_id
                label = $_.label
                role = $_.role
                risk_level = $_.risk_level
                position_bucket = $_.position_bucket
                nearby_text = $_.nearby_text
            }
        }
    )
} | ConvertTo-Json -Depth 8
