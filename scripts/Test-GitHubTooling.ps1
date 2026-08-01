$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "ExitGuide.Common.psm1") -Force

$RepoRoot = Get-ExitGuideRepoRoot
$PublishScript = Join-Path $RepoRoot "scripts/Publish-GitHub.ps1"
$BootstrapScript = Join-Path $RepoRoot "scripts/Bootstrap-Windows.ps1"
$CommonModule = Join-Path $RepoRoot "scripts/ExitGuide.Common.psm1"

foreach ($Path in @($PublishScript, $BootstrapScript, $CommonModule)) {
  if (-not (Test-Path -LiteralPath $Path)) {
    throw "Missing GitHub tooling file: $Path"
  }
}

$PublishText = Get-Content -Raw -LiteralPath $PublishScript
$BootstrapText = Get-Content -Raw -LiteralPath $BootstrapScript
$CommonText = Get-Content -Raw -LiteralPath $CommonModule

foreach ($Fragment in @('"auth", "status"', "repo create", "git push", "pr create")) {
  if (-not $PublishText.Contains($Fragment)) {
    throw "Publish-GitHub.ps1 is missing $Fragment"
  }
}

foreach ($Fragment in @("GhVersion", "Install-PortableGh", "github.com/cli/cli")) {
  if (-not $BootstrapText.Contains($Fragment)) {
    throw "Bootstrap-Windows.ps1 is missing GitHub CLI bootstrap fragment $Fragment"
  }
}

if (-not $CommonText.Contains("Resolve-ExitGuideGhCommand")) {
  throw "ExitGuide.Common.psm1 is missing Resolve-ExitGuideGhCommand"
}

if (-not $CommonText.Contains("Import-ExitGuideEnvFile")) {
  throw "ExitGuide.Common.psm1 is missing Import-ExitGuideEnvFile"
}

$EnvTestName = "EXITGUIDE_ENV_IMPORT_TEST"
$OriginalEnvValue = [Environment]::GetEnvironmentVariable($EnvTestName, "Process")
$EnvTestFile = Join-Path ([System.IO.Path]::GetTempPath()) ("exitguide-env-" + [System.Guid]::NewGuid().ToString("N"))
try {
  [Environment]::SetEnvironmentVariable($EnvTestName, $null, "Process")
  Set-Content -LiteralPath $EnvTestFile -Encoding UTF8 -Value @(
    "# comment",
    "$EnvTestName=loaded",
    "INVALID LINE"
  )
  $Imported = Import-ExitGuideEnvFile -EnvFile $EnvTestFile
  if ($Imported -ne 1 -or [Environment]::GetEnvironmentVariable($EnvTestName, "Process") -ne "loaded") {
    throw "Import-ExitGuideEnvFile did not import the expected value"
  }

  [Environment]::SetEnvironmentVariable($EnvTestName, "explicit", "Process")
  Set-Content -LiteralPath $EnvTestFile -Encoding UTF8 -Value "$EnvTestName=overwritten"
  Import-ExitGuideEnvFile -EnvFile $EnvTestFile | Out-Null
  if ([Environment]::GetEnvironmentVariable($EnvTestName, "Process") -ne "explicit") {
    throw "Import-ExitGuideEnvFile overwrote an explicit process environment variable"
  }
}
finally {
  [Environment]::SetEnvironmentVariable($EnvTestName, $OriginalEnvValue, "Process")
  Remove-Item -LiteralPath $EnvTestFile -Force -ErrorAction SilentlyContinue
}

Write-Host "GitHub tooling checks passed."
