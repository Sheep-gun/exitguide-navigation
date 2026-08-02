param(
  [Parameter(Mandatory = $true)]
  [string]$RemotePath,
  [Parameter(Mandatory = $true)]
  [string]$LocalRelativePath
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$AllowedRemoteRoot = "/home/exitnav/workspace/universal-navigation-api/"
if (-not $RemotePath.StartsWith($AllowedRemoteRoot, [StringComparison]::Ordinal) -or
    $RemotePath -notmatch '^/home/exitnav/workspace/universal-navigation-api/[A-Za-z0-9._/-]+$') {
  throw "RemotePath must be a literal path inside $AllowedRemoteRoot"
}
$Destination = [IO.Path]::GetFullPath((Join-Path $RepoRoot $LocalRelativePath))
if (-not $Destination.StartsWith($RepoRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
  throw "LocalRelativePath must stay inside the repository"
}
$DestinationDirectory = Split-Path -Parent $Destination
[IO.Directory]::CreateDirectory($DestinationDirectory) | Out-Null

$Ssh = "C:\Windows\System32\OpenSSH\ssh.exe"
$SshConfig = "C:\Users\YangGeon\.ssh\exitguide-navigation-config"
if (-not (Test-Path -LiteralPath $Ssh) -or -not (Test-Path -LiteralPath $SshConfig)) {
  throw "ExitGuide Windows OpenSSH or SSH config is missing"
}

$TransferRaw = $Destination + ".transfer.txt"
$TransferBase64 = $Destination + ".transfer.b64"
$TransferError = $Destination + ".transfer.err"
$Arguments = @(
  "-F",
  $SshConfig,
  "exitguide-gpu",
  "base64 $RemotePath"
)
$Process = Start-Process `
  -FilePath $Ssh `
  -ArgumentList $Arguments `
  -WindowStyle Hidden `
  -Wait `
  -PassThru `
  -RedirectStandardOutput $TransferRaw `
  -RedirectStandardError $TransferError
if ($Process.ExitCode -ne 0) {
  throw "SSH artifact transfer failed with exit code $($Process.ExitCode)"
}

$Reader = [IO.File]::OpenText($TransferRaw)
$Writer = [IO.StreamWriter]::new($TransferBase64, $false, [Text.Encoding]::ASCII)
try {
  while (($Line = $Reader.ReadLine()) -ne $null) {
    if ($Line -match '^[A-Za-z0-9+/=]+$') {
      $Writer.WriteLine($Line)
    }
  }
}
finally {
  $Reader.Dispose()
  $Writer.Dispose()
}

& certutil.exe -f -decode $TransferBase64 $Destination | Out-Null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Destination)) {
  throw "Transferred artifact could not be decoded"
}
[IO.File]::Delete($TransferRaw)
[IO.File]::Delete($TransferBase64)
[IO.File]::Delete($TransferError)

$Item = Get-Item -LiteralPath $Destination
$Hash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Copied $RemotePath -> $($Item.FullName)"
Write-Host "bytes=$($Item.Length) sha256=$Hash"
