param(
  [string]$Label = "workblock",
  [switch]$SkipExpoDoctor,
  [switch]$SkipMobileAudit,
  [switch]$SkipTransferArchive
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "ExitGuide.Common.psm1") -Force

$RepoRoot = Get-ExitGuideRepoRoot

function Assert-LastExitCode {
  param([string]$Step)

  if ($LASTEXITCODE -ne 0) {
    throw "$Step failed with exit code $LASTEXITCODE"
  }
}

Push-Location $RepoRoot
try {
  Write-Host "== Quality gate =="
  $TestArgs = @("-ExecutionPolicy", "Bypass", "-File", ".\scripts\Test-All.ps1")
  if ($SkipExpoDoctor) {
    $TestArgs += "-SkipExpoDoctor"
  }
  if ($SkipMobileAudit) {
    $TestArgs += "-SkipMobileAudit"
  }
  & powershell @TestArgs
  Assert-LastExitCode "Test-All"

  $Git = Resolve-ExitGuideGitCommand -RepoRoot $RepoRoot
  $GitDir = Join-Path $RepoRoot ".git"
  if ($Git -and (Test-Path -LiteralPath $GitDir)) {
    Write-Host "== Git diff check =="
    & $Git diff --check
    Assert-LastExitCode "git diff --check"
  }

  if (-not $SkipTransferArchive) {
    Write-Host "== Transfer archive =="
    & powershell -ExecutionPolicy Bypass -File ".\scripts\New-TransferArchive.ps1"
    Assert-LastExitCode "New-TransferArchive"
  }

  Write-Host "== Work-block archive =="
  & powershell -ExecutionPolicy Bypass -File ".\scripts\New-WorkBlockArchive.ps1" -Label $Label
  Assert-LastExitCode "New-WorkBlockArchive"

  Write-Host "== Project status =="
  & powershell -ExecutionPolicy Bypass -File ".\scripts\Get-ProjectStatus.ps1"
  Assert-LastExitCode "Get-ProjectStatus"

  if ($Git -and (Test-Path -LiteralPath $GitDir)) {
    Write-Host "== Git status =="
    & $Git status --short --branch
    Assert-LastExitCode "git status"
  }
}
finally {
  Pop-Location
}
