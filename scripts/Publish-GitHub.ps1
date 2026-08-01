param(
  [string]$RepositoryName = "exitguide",
  [ValidateSet("private", "public", "internal")]
  [string]$Visibility = "private",
  [string]$DefaultBranch = "main",
  [string]$Description = "ExitGuide AI Android-first dark-pattern guidance MVP",
  [switch]$CreateDraftPullRequest
)

$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "ExitGuide.Common.psm1") -Force

$RepoRoot = Get-ExitGuideRepoRoot
$Git = Resolve-ExitGuideGitCommand -RepoRoot $RepoRoot
$Gh = Resolve-ExitGuideGhCommand -RepoRoot $RepoRoot

if (-not $Git) {
  throw "git.exe was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

if (-not $Gh) {
  throw "GitHub CLI was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$GitBin = Split-Path -Parent $Git
$env:Path = "$GitBin;$env:Path"

function Assert-LastExitCode {
  param([string]$Step)

  if ($LASTEXITCODE -ne 0) {
    throw "$Step failed with exit code $LASTEXITCODE"
  }
}

function Invoke-NativeStatus {
  param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,

    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )

  $PreviousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $Output = & $FilePath @Arguments 2>&1
    return [pscustomobject]@{
      ExitCode = $LASTEXITCODE
      Text = (($Output | Out-String).Trim())
    }
  }
  catch {
    return [pscustomobject]@{
      ExitCode = 1
      Text = $_.Exception.Message
    }
  }
  finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
  }
}

Push-Location $RepoRoot
try {
  $AuthStatus = Invoke-NativeStatus -FilePath $Gh -Arguments @("auth", "status")
  if ($AuthStatus.ExitCode -ne 0) {
    throw "GitHub CLI is not authenticated. Run: $Gh auth login --web --git-protocol https"
  }

  $CurrentBranch = (& $Git branch --show-current).Trim()
  if (-not $CurrentBranch) {
    throw "Cannot publish from a detached HEAD."
  }

  & $Git diff --check
  Assert-LastExitCode "git diff --check"

  & $Git status --short --branch
  Assert-LastExitCode "git status"

  $OriginStatus = Invoke-NativeStatus -FilePath $Git -Arguments @("remote", "get-url", "origin")
  $OriginUrl = if ($OriginStatus.ExitCode -eq 0) { $OriginStatus.Text } else { "" }
  if (-not $OriginUrl) {
    $Login = (& $Gh api user --jq ".login").Trim()
    Assert-LastExitCode "gh api user"
    $RepositoryFullName = "$Login/$RepositoryName"

    Write-Host "Creating GitHub repository $RepositoryFullName as $Visibility..."
    & $Gh repo create $RepositoryFullName "--$Visibility" --description $Description --source $RepoRoot --remote origin
    Assert-LastExitCode "gh repo create"

    if (-not (& $Git branch --list $DefaultBranch)) {
      & $Git branch $DefaultBranch HEAD
      Assert-LastExitCode "git branch $DefaultBranch"
    }

    Write-Host "Pushing $DefaultBranch..."
    & $Git push -u origin $DefaultBranch
    Assert-LastExitCode "git push $DefaultBranch"
  } else {
    $RepositoryFullName = (& $Gh repo view --json nameWithOwner --jq ".nameWithOwner").Trim()
    Assert-LastExitCode "gh repo view"
  }

  if ($CurrentBranch -ne $DefaultBranch) {
    Write-Host "Pushing $CurrentBranch..."
    & $Git push -u origin $CurrentBranch
    Assert-LastExitCode "git push $CurrentBranch"
  }

  if ($CreateDraftPullRequest -and $CurrentBranch -ne $DefaultBranch) {
    $BodyPath = Join-Path ([System.IO.Path]::GetTempPath()) ("exitguide-pr-" + [System.Guid]::NewGuid().ToString("N") + ".md")
    try {
      @"
## Summary

- Publishes the current ExitGuide development branch.
- Keeps the deterministic local quality gate, transfer archive, and GitHub workflow scaffolding intact.

## Validation

- .\scripts\Complete-WorkBlock.ps1
"@ | Set-Content -Encoding UTF8 -LiteralPath $BodyPath

      & $Gh pr create --draft --repo $RepositoryFullName --base $DefaultBranch --head $CurrentBranch --title "[codex] continue ExitGuide development" --body-file $BodyPath
      Assert-LastExitCode "gh pr create"
    }
    finally {
      Remove-Item -LiteralPath $BodyPath -Force -ErrorAction SilentlyContinue
    }
  }

  Write-Host "GitHub publish path ready for $RepositoryFullName"
}
finally {
  Pop-Location
}
