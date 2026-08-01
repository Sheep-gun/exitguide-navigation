$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogsDir = Join-Path $RepoRoot ".logs"
New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null

$ApiScript = Join-Path $PSScriptRoot "Start-Api.ps1"
$MobileScript = Join-Path $PSScriptRoot "Start-Mobile.ps1"
$ApiLog = Join-Path $LogsDir "api.log"
$ApiErrorLog = Join-Path $LogsDir "api.err.log"
$MobileLog = Join-Path $LogsDir "mobile.log"
$MobileErrorLog = Join-Path $LogsDir "mobile.err.log"

function Wait-HttpReady {
  param(
    [string]$Name,
    [string]$Uri,
    [int]$Attempts = 40
  )

  for ($Attempt = 1; $Attempt -le $Attempts; $Attempt++) {
    try {
      $Response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
      if ($Response.StatusCode -eq 200) {
        Write-Host "$Name ready: $Uri"
        return
      }
    }
    catch {
      Start-Sleep -Milliseconds 500
    }
  }

  throw "$Name did not become ready at $Uri. Check the dev server logs."
}

function Wait-TcpReady {
  param(
    [string]$Name,
    [string]$HostName,
    [int]$Port,
    [int]$Attempts = 80
  )

  for ($Attempt = 1; $Attempt -le $Attempts; $Attempt++) {
    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
      $Connect = $Client.BeginConnect($HostName, $Port, $null, $null)
      if ($Connect.AsyncWaitHandle.WaitOne(1000) -and $Client.Connected) {
        $Client.EndConnect($Connect)
        Write-Host "$Name ready: $HostName`:$Port"
        return
      }
    }
    catch {
      Start-Sleep -Milliseconds 500
    }
    finally {
      $Client.Dispose()
    }
  }

  throw "$Name did not open $HostName`:$Port. Check the dev server logs."
}

Start-Process powershell `
  -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$ApiScript`"" `
  -RedirectStandardOutput $ApiLog `
  -RedirectStandardError $ApiErrorLog `
  -WindowStyle Hidden

Wait-HttpReady -Name "API quality gate" -Uri "http://127.0.0.1:8010/v1/demo-quality"

Start-Process powershell `
  -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$MobileScript`"" `
  -RedirectStandardOutput $MobileLog `
  -RedirectStandardError $MobileErrorLog `
  -WindowStyle Hidden

Wait-TcpReady -Name "Expo Metro" -HostName "127.0.0.1" -Port 8081

Write-Host "Started API and Expo Metro in the background."
Write-Host "Logs:"
Write-Host "  $ApiLog"
Write-Host "  $ApiErrorLog"
Write-Host "  $MobileLog"
Write-Host "  $MobileErrorLog"
Write-Host ""
powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Get-DevUrls.ps1")
