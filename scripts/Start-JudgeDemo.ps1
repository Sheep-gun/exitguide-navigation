$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogsDir = Join-Path $RepoRoot ".logs"
New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null

$ApiScript = Join-Path $PSScriptRoot "Start-Api.ps1"
$WebScript = Join-Path $PSScriptRoot "Start-WebDemo.ps1"
$ApiLog = Join-Path $LogsDir "judge-api.log"
$ApiErrorLog = Join-Path $LogsDir "judge-api.err.log"
$WebLog = Join-Path $LogsDir "judge-web.log"
$WebErrorLog = Join-Path $LogsDir "judge-web.err.log"

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

  throw "$Name did not become ready at $Uri. Check the judge demo logs."
}

Start-Process powershell `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ApiScript) `
  -RedirectStandardOutput $ApiLog `
  -RedirectStandardError $ApiErrorLog `
  -WindowStyle Hidden

Wait-HttpReady -Name "API quality gate" -Uri "http://127.0.0.1:8010/v1/demo-quality"

Start-Process powershell `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $WebScript) `
  -RedirectStandardOutput $WebLog `
  -RedirectStandardError $WebErrorLog `
  -WindowStyle Hidden

Wait-HttpReady -Name "Web demo" -Uri "http://127.0.0.1:8020/"

Write-Host "Started judge demo API and web demo in the background."
Write-Host "Logs:"
Write-Host "  $ApiLog"
Write-Host "  $ApiErrorLog"
Write-Host "  $WebLog"
Write-Host "  $WebErrorLog"
Write-Host ""
powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Get-DevUrls.ps1")
