param(
  [switch]$SkipExpoDoctor,
  [switch]$SkipMobileAudit,
  [switch]$SkipTestEnvironment
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$NodeRoot = Join-Path $RepoRoot ".tools/node-v24.15.0-win-x64"
$Npx = Join-Path $NodeRoot "npx.cmd"

Push-Location $RepoRoot

try {
  Write-Host "== API smoke =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-Api.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "API smoke failed with exit code $LASTEXITCODE"
  }

  Write-Host "== API unit =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-ApiUnit.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "API unit checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Navigation catalog quality gate =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Audit-NavigationCatalog.ps1" -Gate
  if ($LASTEXITCODE -ne 0) {
    throw "Navigation catalog quality gate failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Navigation goal robustness gate =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Evaluate-NavigationGoalRobustness.ps1" -Mode full -Gate
  if ($LASTEXITCODE -ne 0) {
    throw "Navigation goal robustness gate failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Navigation independent coverage gate =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Audit-NavigationIndependentCoverage.ps1" -Gate
  if ($LASTEXITCODE -ne 0) {
    throw "Navigation independent coverage gate failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Navigation independent goal generalization gate =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Evaluate-NavigationIndependentGoals.ps1" `
    -MinimumAccuracy 0.99 -MinimumSplitAccuracy 0.95 -Gate
  if ($LASTEXITCODE -ne 0) {
    throw "Navigation independent goal generalization gate failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Navigation DB Gym fast gate =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-NavigationDbGym.ps1" -Mode fast
  if ($LASTEXITCODE -ne 0) {
    throw "Navigation DB Gym fast gate failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Mobile typecheck =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Typecheck-Mobile.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Mobile typecheck failed with exit code $LASTEXITCODE"
  }

  if (-not $SkipMobileAudit) {
    Write-Host "== Mobile audit =="
    powershell -ExecutionPolicy Bypass -File ".\scripts\Test-MobileAudit.ps1"
    if ($LASTEXITCODE -ne 0) {
      throw "Mobile audit failed with exit code $LASTEXITCODE"
    }
  }

  Write-Host "== Android config =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-AndroidConfig.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Android config checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Public deployment =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-PublicDeployment.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Public deployment checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Demo report =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\New-DemoReport.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Demo report failed with exit code $LASTEXITCODE"
  }

  Write-Host "== OpenAPI export =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Export-OpenApi.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "OpenAPI export failed with exit code $LASTEXITCODE"
  }

  Write-Host "== OpenAPI contract =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-OpenApi.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "OpenAPI contract checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Documentation sync =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-DocsSync.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Documentation sync checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Provider config =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-ProviderConfig.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Provider config checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Mobile fallback catalog =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-MobileFallbackCatalog.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Mobile fallback catalog checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Mobile trace display =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-MobileTraceDisplay.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Mobile trace display checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Mobile API URL =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-MobileApiUrl.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Mobile API URL checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Mobile history dedupe =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-MobileHistoryDedupe.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Mobile history dedupe checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Mobile readiness details =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-MobileReadinessDetails.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Mobile readiness detail checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Mobile selection clear =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-MobileSelectionClear.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Mobile selection clear checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Web demo =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-WebDemo.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Web demo failed with exit code $LASTEXITCODE"
  }

  if (-not $SkipTestEnvironment) {
    Write-Host "== Live test environment =="
    powershell -ExecutionPolicy Bypass -File ".\scripts\Test-TestEnvironment.ps1"
    if ($LASTEXITCODE -ne 0) {
      throw "Live test environment failed with exit code $LASTEXITCODE"
    }
  }

  Write-Host "== PowerShell scripts =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-Scripts.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "PowerShell script checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Archive safety =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-ArchiveSafety.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Archive safety checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Text hygiene =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-TextHygiene.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Text hygiene checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== CI workflow =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-CiWorkflow.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "CI workflow checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== GitHub tooling =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-GitHubTooling.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "GitHub tooling checks failed with exit code $LASTEXITCODE"
  }

  Write-Host "== Project status =="
  powershell -ExecutionPolicy Bypass -File ".\scripts\Test-ProjectStatus.ps1"
  if ($LASTEXITCODE -ne 0) {
    throw "Project status checks failed with exit code $LASTEXITCODE"
  }

  if (-not $SkipExpoDoctor) {
    Write-Host "== Expo doctor =="
    $env:Path = "$NodeRoot;$env:Path"
    Push-Location (Join-Path $RepoRoot "apps/mobile")
    try {
      & $Npx expo-doctor
      if ($LASTEXITCODE -ne 0) {
        throw "Expo doctor failed with exit code $LASTEXITCODE"
      }
    }
    finally {
      Pop-Location
    }
  }

  Write-Host "All checks passed."
}
finally {
  Pop-Location
}
