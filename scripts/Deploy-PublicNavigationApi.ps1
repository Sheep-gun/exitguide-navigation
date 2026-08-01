param(
  [string]$SshHost = "exitguide-gpu",
  [string]$SshConfig = "$HOME\.ssh\exitguide-navigation-config",
  [string]$RemoteRoot = "/home/exitnav/workspace/universal-navigation-api",
  [string]$EnvFile = "",
  [string]$Commit = "HEAD",
  [switch]$IncludeWorkingTree,
  [switch]$PreserveTunnel
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Artifacts = Join-Path $RepoRoot ".artifacts"
$SourceArchive = Join-Path $Artifacts "public-navigation-api.tar.gz"
$RuntimeEnv = Join-Path $Artifacts "public-navigation-api.env"
$Installer = Join-Path $RepoRoot "deploy/server/install-public-api.sh"
$OpenSshRoot = Join-Path $env:WINDIR "System32\OpenSSH"
$Ssh = Join-Path $OpenSshRoot "ssh.exe"

if (-not $EnvFile) {
  $EnvFile = Join-Path $RepoRoot ".env"
}

foreach ($RequiredPath in @($Ssh, $SshConfig, $EnvFile, $Installer)) {
  if (-not (Test-Path -LiteralPath $RequiredPath -PathType Leaf)) {
    throw "Required deployment file was not found: $RequiredPath"
  }
}

function Send-FileOverSsh {
  param(
    [Parameter(Mandatory = $true)][string]$LocalPath,
    [Parameter(Mandatory = $true)][string]$RemotePath
  )

  $RemoteTemp = "$RemotePath.upload-$PID"
  $RemoteCommand = "umask 077; cat > '$RemoteTemp' && mv '$RemoteTemp' '$RemotePath'"
  $StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
  $StartInfo.FileName = $Ssh
  $StartInfo.Arguments = "-F `"$SshConfig`" $SshHost `"$RemoteCommand`""
  $StartInfo.UseShellExecute = $false
  $StartInfo.RedirectStandardInput = $true
  $StartInfo.RedirectStandardOutput = $true
  $StartInfo.RedirectStandardError = $true
  $StartInfo.CreateNoWindow = $true

  $Process = [System.Diagnostics.Process]::new()
  $Process.StartInfo = $StartInfo
  if (-not $Process.Start()) {
    throw "Could not start OpenSSH for deployment upload."
  }

  $InputFile = [System.IO.File]::OpenRead($LocalPath)
  try {
    $InputFile.CopyTo($Process.StandardInput.BaseStream)
    $Process.StandardInput.Close()
    $Process.WaitForExit()
  }
  finally {
    $InputFile.Dispose()
  }

  $StandardError = $Process.StandardError.ReadToEnd()
  if ($Process.ExitCode -ne 0) {
    throw "Could not upload deployment file: $LocalPath. $StandardError"
  }
  $Process.Dispose()
}

if ($RemoteRoot -notlike "/home/exitnav/workspace/*") {
  throw "RemoteRoot must stay under /home/exitnav/workspace."
}

New-Item -ItemType Directory -Path $Artifacts -Force | Out-Null

$EnvLines = Get-Content -LiteralPath $EnvFile
$SelectedNames = @("EXAONE_API_KEY", "EXAONE_MODEL", "EXAONE_BASE_URL", "EXAONE_TEAM")
$SelectedLines = [System.Collections.Generic.List[string]]::new()
foreach ($Name in $SelectedNames) {
  $Line = $EnvLines | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -First 1
  if ($Line) {
    $SelectedLines.Add($Line)
  }
}

$ApiKeyLine = $SelectedLines | Where-Object { $_ -match "^EXAONE_API_KEY=.+" } | Select-Object -First 1
if (-not $ApiKeyLine) {
  throw "EXAONE_API_KEY is missing from the local environment file."
}

$SelectedLines.Add("OCR_PROVIDER=mock")
$SelectedLines.Add("LLM_PROVIDER=exaone")
$SelectedLines.Add("NAVIGATION_AGENT_PROVIDER=exaone")
$SelectedLines.Add("NAVIGATION_AGENT_ALLOW_FALLBACK=true")
$SelectedLines.Add("NAVIGATION_AGENT_TIMEOUT_SECONDS=35")
$SelectedLines.Add("NAVIGATION_GRAPH_DB_PATH=$RemoteRoot/data/universal-navigation.sqlite")
# The function index is fully derived from the versioned JSON catalog.  Keep
# it on the GPU host's local disk instead of the network-mounted workspace;
# rebuilding the 175 MB SQLite index on NFS made every deployment spend many
# minutes in uninterruptible I/O wait.  The learned navigation graph remains
# on persistent storage above.
$SelectedLines.Add("NAVIGATION_FUNCTION_DB_PATH=/tmp/exitguide-navigation-function-catalog.sqlite")
[System.IO.File]::WriteAllLines($RuntimeEnv, $SelectedLines, [System.Text.UTF8Encoding]::new($false))

Push-Location $RepoRoot
try {
  if ($IncludeWorkingTree) {
    $TemporaryIndex = Join-Path $Artifacts "public-navigation-api.index-$PID"
    $PreviousIndex = $env:GIT_INDEX_FILE
    try {
      Remove-Item -LiteralPath $TemporaryIndex -Force -ErrorAction SilentlyContinue
      $env:GIT_INDEX_FILE = $TemporaryIndex
      & git read-tree HEAD
      & git add -A -- apps/api contracts fixtures
      $Tree = (& git write-tree).Trim()
      if ($LASTEXITCODE -ne 0 -or -not $Tree) {
        throw "Could not prepare the working-tree API snapshot."
      }
      # The catalogs are mostly JSON and compress extremely well.  Shipping an
      # uncompressed archive made every tuning iteration upload hundreds of MB.
      & git archive --format=tar.gz --output=$SourceArchive $Tree apps/api contracts fixtures
      if ($LASTEXITCODE -ne 0) {
        throw "Could not create the working-tree API source archive."
      }
    }
    finally {
      $env:GIT_INDEX_FILE = $PreviousIndex
      Remove-Item -LiteralPath $TemporaryIndex -Force -ErrorAction SilentlyContinue
    }
  } else {
    & git rev-parse --verify "$Commit^{commit}" | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "Git commit was not found: $Commit"
    }

    & git archive --format=tar.gz --output=$SourceArchive $Commit apps/api contracts fixtures
    if ($LASTEXITCODE -ne 0) {
      throw "Could not create the committed API source archive."
    }
  }
}
finally {
  Pop-Location
}

$RemoteIncoming = "$RemoteRoot/incoming"
& $Ssh -F $SshConfig $SshHost "mkdir -p '$RemoteIncoming'"
if ($LASTEXITCODE -ne 0) {
  throw "Could not prepare the remote deployment directory."
}

Send-FileOverSsh -LocalPath $SourceArchive -RemotePath "$RemoteIncoming/source.tar.gz"
Send-FileOverSsh -LocalPath $RuntimeEnv -RemotePath "$RemoteIncoming/runtime.env"
Send-FileOverSsh -LocalPath $Installer -RemotePath "$RemoteIncoming/install-public-api.sh"

$InstallCommand = "'$RemoteIncoming/install-public-api.sh'"
if ($PreserveTunnel) {
  $InstallCommand = "EXITGUIDE_PRESERVE_TUNNEL=1 $InstallCommand"
}
$Output = & $Ssh -F $SshConfig $SshHost "chmod 700 '$RemoteIncoming/install-public-api.sh' && $InstallCommand"
if ($LASTEXITCODE -ne 0) {
  throw "Remote public API deployment failed."
}

$PublicUrlLine = $Output | Where-Object { $_ -match "^PUBLIC_API_URL=https://" } | Select-Object -Last 1
if (-not $PublicUrlLine) {
  throw "Deployment completed without a public API URL."
}

$PublicUrl = ($PublicUrlLine -split "=", 2)[1]
Write-Host "Public Navigation API is ready: $PublicUrl"
Write-Output $PublicUrl
