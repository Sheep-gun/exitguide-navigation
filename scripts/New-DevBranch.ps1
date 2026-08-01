param(
  [Parameter(Mandatory = $true)]
  [string]$BranchName,

  [switch]$InitIfMissing
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "ExitGuide.Common.psm1") -Force

$RepoRoot = Get-ExitGuideRepoRoot
$GitDir = Join-Path $RepoRoot ".git"
$Git = Resolve-ExitGuideGitCommand -RepoRoot $RepoRoot

if (-not $Git) {
  throw "git.exe was not found on PATH or under .tools/mingit-*/cmd. Install Git for Windows or keep using work-block snapshots."
}

if (-not (Test-Path -LiteralPath $GitDir)) {
  if (-not $InitIfMissing) {
    throw "This folder is not a Git repository. Re-run with -InitIfMissing to run git init, or clone the GitHub repo first."
  }
  Push-Location $RepoRoot
  try {
    & $Git init
    if ($LASTEXITCODE -ne 0) {
      throw "git init failed with exit code $LASTEXITCODE"
    }
  }
  finally {
    Pop-Location
  }
}

Push-Location $RepoRoot
try {
  & $Git switch -c $BranchName
  if ($LASTEXITCODE -ne 0) {
    throw "git switch -c $BranchName failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}

Write-Host "Created and switched to branch $BranchName"
