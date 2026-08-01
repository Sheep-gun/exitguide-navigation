param(
  [string]$AiHubRoot,
  [string]$OpenTermsArchiveZip = (Join-Path $HOME "Downloads\contrib-collection-dataset-2026-07-13.zip"),
  [string]$PublicRawRoot,
  [string]$PrincetonXz = (Join-Path $HOME "Downloads\release_db.sqlite.xz"),
  [string]$OutputRoot,
  [switch]$SkipPrinceton
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"
if (-not $AiHubRoot) {
  $AiHubCandidates = @(Get-ChildItem -LiteralPath (Join-Path $HOME "Downloads") -Directory -Filter "019.*")
  if ($AiHubCandidates.Count -ne 1) {
    throw "Expected one AI Hub 019 directory below Downloads, found $($AiHubCandidates.Count). Pass -AiHubRoot explicitly."
  }
  $AiHubRoot = $AiHubCandidates[0].FullName
}
if (-not $OutputRoot) {
  $OutputRoot = Join-Path $RepoRoot ".artifacts/normalized-datasets"
}
if (-not $PublicRawRoot) {
  $PublicRawRoot = Join-Path $RepoRoot ".artifacts/public-datasets/raw"
}
$SourceInventory = Join-Path $RepoRoot "fixtures/public-datasets/sources.json"
$PrincetonDatabase = Join-Path $OutputRoot "princeton_leuven_privacy_policies/release_db.sqlite"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}
if (-not (Test-Path -LiteralPath $AiHubRoot -PathType Container)) {
  throw "AI Hub source directory was not found: $AiHubRoot"
}
if (-not (Test-Path -LiteralPath $OpenTermsArchiveZip -PathType Leaf)) {
  throw "Open Terms Archive ZIP was not found: $OpenTermsArchiveZip"
}
if (-not (Test-Path -LiteralPath $PublicRawRoot -PathType Container)) {
  throw "Collected public dataset root was not found: $PublicRawRoot"
}
if (-not $SkipPrinceton -and -not (Test-Path -LiteralPath $PrincetonDatabase -PathType Leaf)) {
  if (-not (Test-Path -LiteralPath $PrincetonXz -PathType Leaf)) {
    throw "Princeton XZ source was not found: $PrincetonXz"
  }
  Push-Location $ApiRoot
  try {
    $env:PYTHONPATH = $ApiRoot
    & $Python -m app.services.dataset_adapters.princeton prepare $PrincetonXz $OutputRoot
    if ($LASTEXITCODE -ne 0) {
      throw "Princeton database preparation failed with exit code $LASTEXITCODE"
    }
  }
  finally {
    Pop-Location
  }
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

Push-Location $ApiRoot
try {
  $env:PYTHONDONTWRITEBYTECODE = "1"
  $env:PYTHONPATH = $ApiRoot
  $env:PYTHONIOENCODING = "utf-8"
  $Arguments = @(
    "-m", "app.services.dataset_adapters.cli",
    "--aihub-root", $AiHubRoot,
    "--open-terms-archive-zip", $OpenTermsArchiveZip,
    "--public-raw-root", $PublicRawRoot,
    "--source-inventory", $SourceInventory,
    "--output-root", $OutputRoot
  )
  if ($SkipPrinceton) {
    $Arguments += "--skip-princeton"
  }
  else {
    $Arguments += @("--princeton-database", $PrincetonDatabase)
  }
  & $Python @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Public terms dataset conversion failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}
