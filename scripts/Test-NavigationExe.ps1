param(
  [string]$ExePath
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if (-not $ExePath) {
  $ExePath = Join-Path $RepoRoot "dist/EGL-Navigation-MVP.exe"
}
if (-not (Test-Path -LiteralPath $ExePath)) {
  throw "Navigation executable was not found: $ExePath"
}

$Listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), 0)
$Listener.Start()
$Port = $Listener.LocalEndpoint.Port
$Listener.Stop()

$Process = Start-Process `
  -FilePath $ExePath `
  -ArgumentList @("--headless", "--no-browser", "--port", "$Port") `
  -WindowStyle Hidden `
  -PassThru

function Stop-ProcessTree {
  param([int]$ProcessId)

  $Children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
  foreach ($Child in @($Children)) {
    Stop-ProcessTree -ProcessId ([int]$Child.ProcessId)
  }
  Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

try {
  $Ready = $false
  for ($Attempt = 0; $Attempt -lt 100; $Attempt++) {
    $Process.Refresh()
    if ($Process.HasExited) {
      throw "Bundled Navigation executable exited during startup with code $($Process.ExitCode)."
    }
    try {
      $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
      if ($Health.status -eq "ok") {
        $Ready = $true
        break
      }
    }
    catch {
      Start-Sleep -Milliseconds 250
    }
  }
  if (-not $Ready) {
    throw "Bundled Navigation API did not become ready."
  }

  $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/navigation.html" -TimeoutSec 5
  if ($Page.StatusCode -ne 200 -or -not $Page.Content.Contains("EGL Navigation MVP")) {
    throw "Bundled Navigation page returned unexpected content."
  }

  $DarkPage = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/dark-pattern.html" -TimeoutSec 5
  if ($DarkPage.StatusCode -ne 200 -or -not $DarkPage.Content.Contains("EGL Dark Pattern MVP")) {
    throw "Bundled Dark Pattern page returned unexpected content."
  }

  $Body = @'
{
  "request_id": "req_exe_test",
  "app_package": "lab.exitguide.stream.demo",
  "app_version": "1.0.0",
  "platform": "android",
  "locale": "ko-KR",
  "goal_id": "cancel_subscription",
  "session": {
    "last_confirmed_state_id": null,
    "failed_element_ids": [],
    "failed_candidate_meanings": [],
    "retry_count": 0
  },
  "screen_elements": [
    {"id":"title","text":"\uacc4\uc815","role":"heading","clickable":false},
    {"id":"profile","text":"\ud504\ub85c\ud544","role":"text","clickable":false},
    {"id":"settings","text":"\uc124\uc815","role":"text","clickable":false},
    {"id":"target","text":"\uad6c\ub9e4 \ud56d\ubaa9 \ubc0f \uba64\ubc84\uc2ed","role":"button","clickable":true}
  ]
}
'@
  $Guide = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:$Port/v1/navigation/guide" `
    -ContentType "application/json; charset=utf-8" `
    -Body $Body `
    -TimeoutSec 10

  if ($Guide.target_element_id -ne "target") {
    throw "Bundled Navigation API returned an unexpected target."
  }
  if (-not $Guide.dark_pattern -or $Guide.dark_pattern.overall_risk -ne "low") {
    throw "Bundled Navigation API did not include the integrated dark-pattern result."
  }

  $DarkBody = @'
{
  "request_id": "req_dark_exe_test",
  "goal_id": "buy_without_addons",
  "screen_title": "Checkout",
  "elements": [
    {"id":"addon","text":"\uc548\uc2ec \ubcf4\uc99d +2,900\uc6d0","role":"checkbox","clickable":true,"prominence":2,"default_selected":true,"optional":true,"monetary_impact":true},
    {"id":"pay","text":"39,900\uc6d0 \uacb0\uc81c","role":"button","clickable":true,"prominence":3}
  ]
}
'@
  $DarkResult = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:$Port/v1/dark-pattern/inspect" `
    -ContentType "application/json; charset=utf-8" `
    -Body $DarkBody `
    -TimeoutSec 10
  if ($DarkResult.overall_risk -ne "high") {
    throw "Bundled Dark Pattern API did not detect the preselected paid add-on."
  }

  Write-Host "Navigation executable checks passed on port $Port."
}
finally {
  Stop-ProcessTree -ProcessId $Process.Id
}
