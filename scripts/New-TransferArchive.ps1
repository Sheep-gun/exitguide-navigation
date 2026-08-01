$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "ExitGuide.Common.psm1") -Force

$RepoRoot = Get-ExitGuideRepoRoot
$ArtifactsDir = Join-Path $RepoRoot ".artifacts"
$ArchivePath = Join-Path $ArtifactsDir "exitguide-source.zip"
$TrashDir = Join-Path $ArtifactsDir ("trash-" + (Get-Date -Format "yyyyMMdd-HHmmss"))

New-Item -ItemType Directory -Path $ArtifactsDir -Force | Out-Null
Test-ExitGuideChildPath -Path $TrashDir -Parent $ArtifactsDir | Out-Null

if (Test-Path -LiteralPath $ArchivePath) {
  New-Item -ItemType Directory -Path $TrashDir -Force | Out-Null
  Test-ExitGuideChildPath -Path $ArchivePath -Parent $ArtifactsDir | Out-Null
  Move-Item -LiteralPath $ArchivePath -Destination (Join-Path $TrashDir "exitguide-source.zip")
}

$staging = Join-Path $ArtifactsDir "exitguide"
if (Test-Path -LiteralPath $staging) {
  New-Item -ItemType Directory -Path $TrashDir -Force | Out-Null
  Test-ExitGuideChildPath -Path $staging -Parent $ArtifactsDir | Out-Null
  Move-Item -LiteralPath $staging -Destination (Join-Path $TrashDir "exitguide-staging")
}

Copy-ExitGuideSourceToStaging -RepoRoot $RepoRoot -Staging $staging

Compress-Archive -LiteralPath $staging -DestinationPath $ArchivePath -Force
Test-ExitGuideArchiveClean -ArchivePath $ArchivePath | Out-Null
New-Item -ItemType Directory -Path $TrashDir -Force | Out-Null
Test-ExitGuideChildPath -Path $staging -Parent $ArtifactsDir | Out-Null
Move-Item -LiteralPath $staging -Destination (Join-Path $TrashDir "exitguide-staging")

Write-Host "Created $ArchivePath"
