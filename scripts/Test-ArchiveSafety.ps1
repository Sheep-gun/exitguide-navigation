$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "ExitGuide.Common.psm1") -Force

$RepoRoot = Get-ExitGuideRepoRoot
$ArtifactsDir = Join-Path $RepoRoot ".artifacts"
$Scratch = Join-Path $ArtifactsDir ("archive-safety-test-" + [System.Guid]::NewGuid().ToString("N"))
$SafeRoot = Join-Path $Scratch "safe"
$UnsafeRoot = Join-Path $Scratch "unsafe"
$SecretRoot = Join-Path $Scratch "secret"
$TermsRoot = Join-Path $Scratch "terms-leak"
$SafeArchive = Join-Path $Scratch "safe.zip"
$UnsafeArchive = Join-Path $Scratch "unsafe.zip"
$SecretArchive = Join-Path $Scratch "secret.zip"
$TermsArchive = Join-Path $Scratch "terms-leak.zip"

New-Item -ItemType Directory -Path $SafeRoot, $UnsafeRoot, $SecretRoot, $TermsRoot -Force | Out-Null

try {
  Test-ExitGuideChildPath -Path $Scratch -Parent $ArtifactsDir | Out-Null

  Set-Content -LiteralPath (Join-Path $SafeRoot "README.md") -Value "safe archive fixture" -Encoding UTF8
  Compress-Archive -LiteralPath $SafeRoot -DestinationPath $SafeArchive -Force
  Test-ExitGuideArchiveClean -ArchivePath $SafeArchive | Out-Null

  Set-Content -LiteralPath (Join-Path $UnsafeRoot ".env") -Value "OPENAI_API_KEY=redacted" -Encoding UTF8
  Compress-Archive -LiteralPath $UnsafeRoot -DestinationPath $UnsafeArchive -Force
  try {
    Test-ExitGuideArchiveClean -ArchivePath $UnsafeArchive | Out-Null
    throw "Archive safety check did not reject .env"
  }
  catch {
    if ($_.Exception.Message -notmatch "sensitive/raw path") {
      throw
    }
  }

  $FakeToken = "token " + "sk-" + "testsecret000000000000000000000"
  Set-Content -LiteralPath (Join-Path $SecretRoot "notes.md") -Value $FakeToken -Encoding UTF8
  Compress-Archive -LiteralPath $SecretRoot -DestinationPath $SecretArchive -Force
  try {
    Test-ExitGuideArchiveClean -ArchivePath $SecretArchive | Out-Null
    throw "Archive safety check did not reject sensitive-looking content"
  }
  catch {
    if ($_.Exception.Message -notmatch "sensitive-looking content") {
      throw
    }
  }

  $TermsCaptureDir = Join-Path $TermsRoot "terms-captures/inbox"
  New-Item -ItemType Directory -Path $TermsCaptureDir -Force | Out-Null
  Set-Content -LiteralPath (Join-Path $TermsCaptureDir "capture.json") -Value "{}" -Encoding UTF8
  Set-Content -LiteralPath (Join-Path $TermsRoot "terms-corpus.sqlite") -Value "sqlite bytes" -Encoding UTF8
  Compress-Archive -LiteralPath $TermsRoot -DestinationPath $TermsArchive -Force
  try {
    Test-ExitGuideArchiveClean -ArchivePath $TermsArchive | Out-Null
    throw "Archive safety check did not reject terms capture/corpus paths"
  }
  catch {
    if ($_.Exception.Message -notmatch "sensitive/raw path") {
      throw
    }
  }

  Write-Host "Archive safety checks passed."
}
finally {
  if (Test-Path -LiteralPath $Scratch) {
    Test-ExitGuideChildPath -Path $Scratch -Parent $ArtifactsDir | Out-Null
    Remove-Item -LiteralPath $Scratch -Recurse -Force
  }
}
