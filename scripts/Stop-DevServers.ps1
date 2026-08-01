$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

$processes = Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -and
    $_.CommandLine -like "*$RepoRoot*" -and
    (
      $_.CommandLine -like "*Start-Api.ps1*" -or
      $_.CommandLine -like "*Start-Mobile.ps1*" -or
      $_.CommandLine -like "*Start-DevServers.ps1*" -or
      $_.CommandLine -like "*Start-WebDemo.ps1*" -or
      $_.CommandLine -like "*Start-Mobile-Interactive.ps1*" -or
      $_.CommandLine -like "*expo start*" -or
      $_.CommandLine -like "*expo\bin\cli*start*" -or
      $_.CommandLine -like "*http.server 8020*" -or
      $_.CommandLine -like "*uvicorn app.main:app*"
    )
  }

foreach ($process in $processes) {
  Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
  Write-Host "Stopped $($process.ProcessId) $($process.Name)"
}
