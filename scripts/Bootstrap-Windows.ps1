$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "ExitGuide.Common.psm1") -Force

$RepoRoot = Get-ExitGuideRepoRoot
$NodeVersion = "v24.15.0"
$NodeDirName = "node-$NodeVersion-win-x64"
$ToolsDir = Join-Path $RepoRoot ".tools"
$DownloadsDir = Join-Path $ToolsDir "downloads"
$NodeDir = Join-Path $ToolsDir $NodeDirName
$NodeZip = Join-Path $DownloadsDir "$NodeDirName.zip"
$NodeUrl = "https://nodejs.org/dist/$NodeVersion/$NodeDirName.zip"
$GitVersion = "2.54.0"
$GitDirName = "mingit-$GitVersion"
$GitDir = Join-Path $ToolsDir $GitDirName
$GitZip = Join-Path $DownloadsDir "MinGit-$GitVersion-64-bit.zip"
$GitUrl = "https://github.com/git-for-windows/git/releases/download/v$GitVersion.windows.1/MinGit-$GitVersion-64-bit.zip"
$GhVersion = "2.92.0"
$GhDirName = "gh-$GhVersion"
$GhDir = Join-Path $ToolsDir $GhDirName
$GhZip = Join-Path $DownloadsDir "gh_$GhVersion`_windows_amd64.zip"
$GhUrl = "https://github.com/cli/cli/releases/download/v$GhVersion/gh_$GhVersion`_windows_amd64.zip"

$ApiRoot = Join-Path $RepoRoot "apps/api"
$MobileRoot = Join-Path $RepoRoot "apps/mobile"

function Resolve-PythonCommand {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    & python --version | Out-Null
    if ($LASTEXITCODE -eq 0) {
      return "python"
    }
  }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    & py -3 --version | Out-Null
    if ($LASTEXITCODE -eq 0) {
      return "py -3"
    }
  }

  throw "Python 3 was not found. Install Python 3.12+ or run this from a Codex environment with Python available."
}

function Resolve-GitCommand {
  return Resolve-ExitGuideGitCommand -RepoRoot $RepoRoot
}

function Resolve-GhCommand {
  return Resolve-ExitGuideGhCommand -RepoRoot $RepoRoot
}

function Install-PortableGit {
  if (Resolve-GitCommand) {
    Write-Host "Git is available."
    return
  }

  Write-Host "Downloading project-local MinGit $GitVersion..."
  if (-not (Test-Path -LiteralPath $GitZip)) {
    Invoke-WebRequest -Uri $GitUrl -OutFile $GitZip
  }

  $TempExtract = Join-Path $ToolsDir ("mingit-extract-" + [System.Guid]::NewGuid().ToString("N"))
  Expand-Archive -LiteralPath $GitZip -DestinationPath $TempExtract -Force

  if (Test-Path -LiteralPath $GitDir) {
    Test-ExitGuideChildPath -Path $GitDir -Parent $ToolsDir | Out-Null
    Remove-Item -LiteralPath $GitDir -Recurse -Force
  }
  Test-ExitGuideChildPath -Path $TempExtract -Parent $ToolsDir | Out-Null
  Move-Item -LiteralPath $TempExtract -Destination $GitDir
  Write-Host "Project-local Git installed at $GitDir"
}

function Install-PortableGh {
  if (Resolve-GhCommand) {
    Write-Host "GitHub CLI is available."
    return
  }

  Write-Host "Downloading project-local GitHub CLI $GhVersion..."
  if (-not (Test-Path -LiteralPath $GhZip)) {
    Invoke-WebRequest -Uri $GhUrl -OutFile $GhZip
  }

  $TempExtract = Join-Path $ToolsDir ("gh-extract-" + [System.Guid]::NewGuid().ToString("N"))
  Expand-Archive -LiteralPath $GhZip -DestinationPath $TempExtract -Force

  if (Test-Path -LiteralPath $GhDir) {
    Test-ExitGuideChildPath -Path $GhDir -Parent $ToolsDir | Out-Null
    Remove-Item -LiteralPath $GhDir -Recurse -Force
  }
  Test-ExitGuideChildPath -Path $TempExtract -Parent $ToolsDir | Out-Null
  Move-Item -LiteralPath $TempExtract -Destination $GhDir
  Write-Host "Project-local GitHub CLI installed at $GhDir"
}

function Assert-LastExitCode {
  param([string]$Step)

  if ($LASTEXITCODE -ne 0) {
    throw "$Step failed with exit code $LASTEXITCODE"
  }
}

Push-Location $RepoRoot
try {
Write-Host "Bootstrapping ExitGuide in $RepoRoot"
$Python = Resolve-PythonCommand

New-Item -ItemType Directory -Path $DownloadsDir -Force | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $NodeDir "npm.cmd"))) {
  Write-Host "Downloading project-local Node.js $NodeVersion..."
  Invoke-WebRequest -Uri $NodeUrl -OutFile $NodeZip
  Expand-Archive -LiteralPath $NodeZip -DestinationPath $ToolsDir -Force
} else {
  Write-Host "Project-local Node.js already exists."
}

Install-PortableGit
Install-PortableGh

$NodeRoot = Join-Path $RepoRoot ".tools/$NodeDirName"
$env:Path = "$NodeRoot;$env:Path"

Write-Host "Installing mobile dependencies..."
Set-Location $MobileRoot
& (Join-Path $NodeRoot "npm.cmd") install
Assert-LastExitCode "npm install"

Write-Host "Preparing API virtual environment..."
Set-Location $ApiRoot
if (-not (Test-Path -LiteralPath ".venv/Scripts/python.exe")) {
  Invoke-Expression "$Python -m venv .venv"
  Assert-LastExitCode "python venv"
}
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
Assert-LastExitCode "pip install"

Write-Host "Regenerating synthetic demo screens..."
Set-Location $RepoRoot
& ".\apps\api\.venv\Scripts\python.exe" ".\scripts\Generate-SyntheticScreens.py"
Assert-LastExitCode "synthetic screen generation"

Write-Host "Regenerating mobile assets..."
& ".\apps\api\.venv\Scripts\python.exe" ".\scripts\Generate-MobileAssets.py"
Assert-LastExitCode "mobile asset generation"

Write-Host "Running checks..."
powershell -ExecutionPolicy Bypass -File ".\scripts\Test-All.ps1" -SkipExpoDoctor -SkipTestEnvironment
Assert-LastExitCode "local checks"

Write-Host ""
Write-Host "Bootstrap complete. Start development servers with:"
Write-Host "  .\scripts\Start-Api.ps1"
Write-Host "  .\scripts\Start-Mobile-Interactive.ps1"
Write-Host "  .\scripts\Start-JudgeDemo.ps1"
Write-Host ""
Write-Host "Then run:"
Write-Host "  .\scripts\Get-DevUrls.ps1"
}
finally {
  Pop-Location
}
