param(
  [switch]$IncludeMobile,
  [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"

function Assert-LastExitCode {
  param([string]$Step)

  if ($LASTEXITCODE -ne 0) {
    throw "$Step failed with exit code $LASTEXITCODE"
  }
}

function Test-TcpOpen {
  param(
    [string]$HostName,
    [int]$Port
  )

  $Client = [System.Net.Sockets.TcpClient]::new()
  try {
    $Connect = $Client.BeginConnect($HostName, $Port, $null, $null)
    if ($Connect.AsyncWaitHandle.WaitOne(1000) -and $Client.Connected) {
      $Client.EndConnect($Connect)
      return $true
    }
    return $false
  }
  catch {
    return $false
  }
  finally {
    $Client.Dispose()
  }
}

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$StartScriptText = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot "Start-TestEnvironment.ps1")
if (-not $StartScriptText.Contains('"--host", "0.0.0.0"')) {
  throw "Start-TestEnvironment.ps1 must bind the API to 0.0.0.0 so physical phones can reach the LAN URL."
}

Push-Location $RepoRoot
try {
  $StartArgs = @("-ExecutionPolicy", "Bypass", "-File", ".\scripts\Start-TestEnvironment.ps1")
  if ($IncludeMobile) {
    $StartArgs += "-IncludeMobile"
  }

  try {
    & powershell @StartArgs
    Assert-LastExitCode "Start-TestEnvironment"

    $OldApiBaseUrl = $env:EXITGUIDE_TEST_API_BASE_URL
    try {
      $env:EXITGUIDE_TEST_API_BASE_URL = "http://127.0.0.1:8010"
      & $Python ".\apps\api\tests\live_environment.py"
      Assert-LastExitCode "live API environment checks"
    }
    finally {
      $env:EXITGUIDE_TEST_API_BASE_URL = $OldApiBaseUrl
    }

    $WebResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8020/" -TimeoutSec 5
    if ($WebResponse.StatusCode -ne 200) {
      throw "Web demo returned HTTP $($WebResponse.StatusCode)."
    }
    if (-not $WebResponse.Content.Contains("Goal-first dark-pattern guidance.")) {
      throw "Web demo did not return the expected page content."
    }

    if ($IncludeMobile -and -not (Test-TcpOpen -HostName "127.0.0.1" -Port 8081)) {
      throw "Expo Metro port 8081 is not open."
    }

    Write-Host "Test environment checks passed."
  }
  finally {
    if (-not $KeepRunning) {
      & powershell -ExecutionPolicy Bypass -File ".\scripts\Stop-TestEnvironment.ps1"
      Assert-LastExitCode "Stop-TestEnvironment"
    }
  }
}
finally {
  Pop-Location
}
