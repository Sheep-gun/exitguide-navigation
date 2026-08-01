param(
  [switch]$ForceDevServers
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogsDir = Join-Path $RepoRoot ".logs/test-environment"
$PidFile = Join-Path $LogsDir "test-environment.pids.json"

function Test-SafeTrackedProcess {
  param(
    [object]$Entry,
    [object]$ProcessInfo
  )

  $CommandLine = [string]$ProcessInfo.CommandLine
  if ([string]::IsNullOrWhiteSpace($CommandLine)) {
    return $false
  }

  return (
    $CommandLine -like "*$RepoRoot*" -or
    $CommandLine -like "*uvicorn app.main:app*" -or
    $CommandLine -like "*http.server 8020*" -or
    $CommandLine -like "*expo start*"
  )
}

function Stop-ProcessTree {
  param([int]$ProcessId)

  $Children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
  foreach ($Child in $Children) {
    Stop-ProcessTree -ProcessId ([int]$Child.ProcessId)
  }

  $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if ($Process) {
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped PID $ProcessId ($($Process.ProcessName))"
  }
}

if (Test-Path -LiteralPath $PidFile) {
  $RawEntries = Get-Content -Raw -LiteralPath $PidFile | ConvertFrom-Json
  $Entries = @()
  foreach ($Entry in @($RawEntries)) {
    if ($Entry -is [array]) {
      foreach ($NestedEntry in $Entry) {
        $Entries += $NestedEntry
      }
    } else {
      $Entries += $Entry
    }
  }

  foreach ($Entry in $Entries) {
    if (-not $Entry.pid) {
      continue
    }

    $TrackedProcessId = [int]$Entry.pid
    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $TrackedProcessId" -ErrorAction SilentlyContinue
    if (-not $ProcessInfo) {
      Write-Host "PID $TrackedProcessId is no longer running."
      continue
    }

    if (-not (Test-SafeTrackedProcess -Entry $Entry -ProcessInfo $ProcessInfo)) {
      Write-Host "Skipping PID $TrackedProcessId because it no longer matches the test environment command line."
      continue
    }

    Stop-ProcessTree -ProcessId $TrackedProcessId
  }

  Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
} else {
  Write-Host "No test environment PID file found."
}

if ($ForceDevServers) {
  powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Stop-DevServers.ps1")
  if ($LASTEXITCODE -ne 0) {
    throw "Stop-DevServers failed with exit code $LASTEXITCODE"
  }
}

Write-Host "Test environment stopped."
