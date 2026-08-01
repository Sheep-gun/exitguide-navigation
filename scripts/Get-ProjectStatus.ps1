$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "ExitGuide.Common.psm1") -Force

$RepoRoot = Get-ExitGuideRepoRoot
$ArtifactsDir = Join-Path $RepoRoot ".artifacts"
$DemoReport = Join-Path $ArtifactsDir "demo-report.md"
$OpenApi = Join-Path $ArtifactsDir "openapi.json"
$TransferArchive = Join-Path $ArtifactsDir "exitguide-source.zip"
$WorkBlocksDir = Join-Path $ArtifactsDir "work-blocks"

function Get-GitText {
  param([string[]]$Arguments)

  Push-Location $RepoRoot
  try {
    $ErrorActionPreference = "Continue"
    $Output = & $Git @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) {
      return $null
    }
    return (($Output | Out-String).Trim())
  }
  catch {
    return $null
  }
  finally {
    Pop-Location
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

Write-Host "Project: $RepoRoot"

$Git = Resolve-ExitGuideGitCommand -RepoRoot $RepoRoot
$GitDir = Join-Path $RepoRoot ".git"
if ($Git -and (Test-Path -LiteralPath $GitDir)) {
  Write-Host "Git: available ($Git)"
  $Branch = Get-GitText -Arguments @("branch", "--show-current")
  if (-not $Branch) {
    $Branch = "(detached)"
  }

  $Commit = Get-GitText -Arguments @("rev-parse", "--short", "HEAD")
  if (-not $Commit) {
    $Commit = "no commits yet"
  }

  $Remote = Get-GitText -Arguments @("remote", "get-url", "origin")
  if (-not $Remote) {
    $Remote = "none configured"
  }

  $Porcelain = Get-GitText -Arguments @("status", "--porcelain")
  if ([string]::IsNullOrWhiteSpace($Porcelain)) {
    $WorkingTree = "clean"
  } else {
    $ChangedPathCount = @($Porcelain -split "`r?`n" | Where-Object { $_ }).Count
    $WorkingTree = "$ChangedPathCount changed path(s)"
  }

  Write-Host "Git branch: $Branch"
  Write-Host "Git commit: $Commit"
  Write-Host "Git remote origin: $Remote"
  Write-Host "Git working tree: $WorkingTree"
} elseif ($Git) {
  Write-Host "Git: command available ($Git), but this folder is not a git repository"
} else {
  Write-Host "Git: not found on PATH"
  Write-Host "GitHub plugin note: the connector can work with a known owner/repo, but it does not provide local git.exe."
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "Git install hint: winget install --id Git.Git -e --source winget"
  }
}

$Gh = Resolve-ExitGuideGhCommand -RepoRoot $RepoRoot
if ($Gh) {
  $GhAuthStatus = Invoke-NativeStatus -FilePath $Gh -Arguments @("auth", "status")
  if ($GhAuthStatus.ExitCode -eq 0) {
    Write-Host "GitHub CLI: authenticated ($Gh)"
  } else {
    Write-Host "GitHub CLI: installed but not authenticated ($Gh)"
    Write-Host "GitHub auth hint: .\.tools\gh-2.92.0\bin\gh.exe auth login --web --git-protocol https"
  }
} else {
  Write-Host "GitHub CLI: not found; run .\scripts\Bootstrap-Windows.ps1"
}

foreach ($Artifact in @($DemoReport, $OpenApi, $TransferArchive)) {
  if (Test-Path -LiteralPath $Artifact) {
    $Item = Get-Item -LiteralPath $Artifact
    Write-Host "$($Item.Name): $($Item.Length) bytes, updated $($Item.LastWriteTime)"
  } else {
    Write-Host "$(Split-Path -Leaf $Artifact): missing"
  }
}

if (Test-Path -LiteralPath $DemoReport) {
  $QualityLine = Get-Content -LiteralPath $DemoReport | Where-Object { $_ -like "- Result:*" } | Select-Object -Last 1
  if ($QualityLine) {
    Write-Host "Demo report quality: $QualityLine"
  }
}

if (Test-Path -LiteralPath $WorkBlocksDir) {
  $WorkBlocks = Get-ChildItem -LiteralPath $WorkBlocksDir -Filter "*.zip" -File | Sort-Object LastWriteTime -Descending
  Write-Host "Work-block snapshots: $($WorkBlocks.Count)"
  $WorkBlocks | Select-Object -First 5 | ForEach-Object {
    Write-Host "  $($_.Name) ($($_.LastWriteTime))"
  }
} else {
  Write-Host "Work-block snapshots: none"
}

function Test-HttpOk {
  param([string]$Uri)

  try {
    $Response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 1
    return $Response.StatusCode -eq 200
  }
  catch {
    return $false
  }
}

function Test-TcpOpen {
  param(
    [string]$HostName,
    [int]$Port
  )

  $Client = [System.Net.Sockets.TcpClient]::new()
  try {
    $Connect = $Client.BeginConnect($HostName, $Port, $null, $null)
    if ($Connect.AsyncWaitHandle.WaitOne(500) -and $Client.Connected) {
      $Client.EndConnect($Connect)
      return $true
    }
    return $false
  }
  catch {
    return $false
  }
  finally {
    $Client.Dispose()
  }
}

Write-Host "Running services:"
Write-Host "  API quality: $(if (Test-HttpOk 'http://127.0.0.1:8010/v1/demo-quality') { 'ready' } else { 'not detected' })"
Write-Host "  Web demo: $(if (Test-HttpOk 'http://127.0.0.1:8020/') { 'ready' } else { 'not detected' })"
Write-Host "  Expo Metro: $(if (Test-TcpOpen -HostName '127.0.0.1' -Port 8081) { 'port open' } else { 'not detected' })"

Write-Host "Primary check: .\scripts\Test-All.ps1"
