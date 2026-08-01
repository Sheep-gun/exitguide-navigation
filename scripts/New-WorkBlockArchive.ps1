param(
  [Alias("BlockName")]
  [string]$Label = "workblock"
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "ExitGuide.Common.psm1") -Force

$RepoRoot = Get-ExitGuideRepoRoot
$ArtifactsDir = Join-Path $RepoRoot ".artifacts"
$WorkBlocksDir = Join-Path $ArtifactsDir "work-blocks"
$SafeLabel = ($Label -replace "[^A-Za-z0-9._-]+", "-").Trim("-")

if (-not $SafeLabel) {
  $SafeLabel = "workblock"
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ArchivePath = Join-Path $WorkBlocksDir "$Timestamp-$SafeLabel.zip"
$StagingParent = Join-Path $WorkBlocksDir ".staging-$Timestamp-$([System.Guid]::NewGuid().ToString("N"))"
$Staging = Join-Path $StagingParent "exitguide"

New-Item -ItemType Directory -Path $WorkBlocksDir -Force | Out-Null
New-Item -ItemType Directory -Path $Staging -Force | Out-Null

try {
  Copy-ExitGuideSourceToStaging -RepoRoot $RepoRoot -Staging $Staging
  Compress-Archive -LiteralPath $Staging -DestinationPath $ArchivePath -Force
  Test-ExitGuideArchiveClean -ArchivePath $ArchivePath | Out-Null
}
finally {
  if (Test-Path -LiteralPath $StagingParent) {
    Test-ExitGuideChildPath -Path $StagingParent -Parent $WorkBlocksDir | Out-Null
    Remove-Item -LiteralPath $StagingParent -Recurse -Force
  }
}

Write-Host "Created $ArchivePath"
