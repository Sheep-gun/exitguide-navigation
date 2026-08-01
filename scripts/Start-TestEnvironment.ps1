param(
  [switch]$IncludeMobile
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$WebRoot = Join-Path $RepoRoot "apps/web-demo"
$MobileRoot = Join-Path $RepoRoot "apps/mobile"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"
$NodeRoot = Join-Path $RepoRoot ".tools/node-v24.15.0-win-x64"
$Npx = Join-Path $NodeRoot "npx.cmd"
$LogsDir = Join-Path $RepoRoot ".logs/test-environment"
$PidFile = Join-Path $LogsDir "test-environment.pids.json"

Import-Module (Join-Path $PSScriptRoot "ExitGuide.Common.psm1") -Force
Import-ExitGuideEnvFile -EnvFile (Join-Path $RepoRoot ".env") | Out-Null

New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null

function Test-HttpOk {
  param([string]$Uri)

  try {
    $Response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
    return $Response.StatusCode -eq 200
  }
  catch {
    return $false
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

function Wait-HttpReady {
  param(
    [string]$Name,
    [string]$Uri,
    [int]$Attempts = 50
  )

  for ($Attempt = 1; $Attempt -le $Attempts; $Attempt++) {
    if (Test-HttpOk -Uri $Uri) {
      Write-Host "$Name ready: $Uri"
      return
    }
    Start-Sleep -Milliseconds 500
  }

  throw "$Name did not become ready at $Uri. Check logs under $LogsDir."
}

function Wait-TcpReady {
  param(
    [string]$Name,
    [string]$HostName,
    [int]$Port,
    [int]$Attempts = 80
  )

  for ($Attempt = 1; $Attempt -le $Attempts; $Attempt++) {
    if (Test-TcpOpen -HostName $HostName -Port $Port) {
      Write-Host "$Name ready: $HostName`:$Port"
      return
    }
    Start-Sleep -Milliseconds 500
  }

  throw "$Name did not open $HostName`:$Port. Check logs under $LogsDir."
}

function Start-TrackedProcess {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    [Parameter(Mandatory = $true)]
    [string]$FilePath,

    [Parameter(Mandatory = $true)]
    [string[]]$ArgumentList,

    [Parameter(Mandatory = $true)]
    [string]$WorkingDirectory,

    [Parameter(Mandatory = $true)]
    [string]$OutputLog,

    [Parameter(Mandatory = $true)]
    [string]$ErrorLog
  )

  Remove-Item -LiteralPath $OutputLog, $ErrorLog -Force -ErrorAction SilentlyContinue
  $Process = Start-Process `
    -FilePath $FilePath `
    -ArgumentList $ArgumentList `
    -WorkingDirectory $WorkingDirectory `
    -RedirectStandardOutput $OutputLog `
    -RedirectStandardError $ErrorLog `
    -WindowStyle Hidden `
    -PassThru

  Write-Host "Started $Name as PID $($Process.Id)"
  return [pscustomobject]@{
    name = $Name
    pid = $Process.Id
    command = $FilePath
    arguments = ($ArgumentList -join " ")
    working_directory = $WorkingDirectory
    stdout_log = $OutputLog
    stderr_log = $ErrorLog
    started_at = (Get-Date).ToString("o")
  }
}

function Get-RecordedProcesses {
  if (-not (Test-Path -LiteralPath $PidFile)) {
    return @()
  }

  try {
    $RawEntries = Get-Content -Raw -LiteralPath $PidFile | ConvertFrom-Json
    foreach ($Entry in @($RawEntries)) {
      if ($Entry -is [array]) {
        foreach ($NestedEntry in $Entry) {
          $NestedEntry
        }
      } else {
        $Entry
      }
    }
  }
  catch {
    Write-Host "Ignoring unreadable PID file: $PidFile"
    return @()
  }
}

function Save-RecordedProcesses {
  param([object[]]$NewProcesses)

  $ByPid = @{}
  foreach ($Entry in (@(Get-RecordedProcesses) + @($NewProcesses))) {
    if (-not $Entry.pid) {
      continue
    }

    $Process = Get-Process -Id ([int]$Entry.pid) -ErrorAction SilentlyContinue
    if ($Process) {
      $ByPid[[string]$Entry.pid] = $Entry
    }
  }

  if ($ByPid.Count -eq 0) {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    return
  }

  @($ByPid.Values) |
    Sort-Object pid |
    ConvertTo-Json -Depth 6 |
    Set-Content -Encoding UTF8 -LiteralPath $PidFile
}

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$StartedProcesses = @()
$env:PYTHONDONTWRITEBYTECODE = "1"

if (Test-HttpOk -Uri "http://127.0.0.1:8010/v1/demo-quality") {
  Write-Host "API already ready: http://127.0.0.1:8010/v1/demo-quality"
} else {
  $StartedProcesses += Start-TrackedProcess `
    -Name "api" `
    -FilePath $Python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010") `
    -WorkingDirectory $ApiRoot `
    -OutputLog (Join-Path $LogsDir "api.log") `
    -ErrorLog (Join-Path $LogsDir "api.err.log")
  Save-RecordedProcesses -NewProcesses $StartedProcesses
  Wait-HttpReady -Name "API quality gate" -Uri "http://127.0.0.1:8010/v1/demo-quality"
}

if (Test-HttpOk -Uri "http://127.0.0.1:8020/") {
  Write-Host "Web demo already ready: http://127.0.0.1:8020/"
} else {
  $StartedProcesses += Start-TrackedProcess `
    -Name "web-demo" `
    -FilePath $Python `
    -ArgumentList @("-m", "http.server", "8020", "--bind", "127.0.0.1") `
    -WorkingDirectory $WebRoot `
    -OutputLog (Join-Path $LogsDir "web-demo.log") `
    -ErrorLog (Join-Path $LogsDir "web-demo.err.log")
  Save-RecordedProcesses -NewProcesses $StartedProcesses
  Wait-HttpReady -Name "Web demo" -Uri "http://127.0.0.1:8020/"
}

if ($IncludeMobile) {
  if (-not (Test-Path -LiteralPath $Npx)) {
    throw "Portable Node runtime was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
  }

  if (Test-TcpOpen -HostName "127.0.0.1" -Port 8081) {
    Write-Host "Expo Metro already ready: 127.0.0.1:8081"
  } else {
    $OriginalPath = $env:Path
    $OriginalCi = $env:CI
    try {
      $env:Path = "$NodeRoot;$env:Path"
      $env:CI = "1"
      $StartedProcesses += Start-TrackedProcess `
        -Name "expo-metro" `
        -FilePath $Npx `
        -ArgumentList @("expo", "start", "--host", "lan", "--clear") `
        -WorkingDirectory $MobileRoot `
        -OutputLog (Join-Path $LogsDir "mobile.log") `
        -ErrorLog (Join-Path $LogsDir "mobile.err.log")
      Save-RecordedProcesses -NewProcesses $StartedProcesses
    }
    finally {
      $env:Path = $OriginalPath
      $env:CI = $OriginalCi
    }
    Wait-TcpReady -Name "Expo Metro" -HostName "127.0.0.1" -Port 8081
  }
}

Save-RecordedProcesses -NewProcesses $StartedProcesses

Write-Host "Test environment is ready."
Write-Host "Logs: $LogsDir"
Write-Host "PID file: $PidFile"
Write-Host ""
powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Get-DevUrls.ps1")
