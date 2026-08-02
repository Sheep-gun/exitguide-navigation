param(
  [Parameter(Mandatory = $true)]
  [string]$LocalRelativePath,
  [Parameter(Mandatory = $true)]
  [string]$RemotePath
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$AllowedRemoteRoot = "/home/exitnav/workspace/universal-navigation-api/"
if (-not $RemotePath.StartsWith($AllowedRemoteRoot, [StringComparison]::Ordinal) -or
    $RemotePath -notmatch '^/home/exitnav/workspace/universal-navigation-api/[A-Za-z0-9._/-]+$') {
  throw "RemotePath must be a literal path inside $AllowedRemoteRoot"
}
$Source = [IO.Path]::GetFullPath((Join-Path $RepoRoot $LocalRelativePath))
if (-not $Source.StartsWith($RepoRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
    -not (Test-Path -LiteralPath $Source -PathType Leaf)) {
  throw "LocalRelativePath must name a file inside the repository"
}

$Ssh = "C:\Windows\System32\OpenSSH\ssh.exe"
$SshConfig = "C:\Users\YangGeon\.ssh\exitguide-navigation-config"
if (-not (Test-Path -LiteralPath $Ssh) -or -not (Test-Path -LiteralPath $SshConfig)) {
  throw "ExitGuide Windows OpenSSH or SSH config is missing"
}

$RemoteDirectory = $RemotePath.Substring(0, $RemotePath.LastIndexOf('/'))
$RemoteTemporary = "$RemotePath.upload-$PID"
$RemoteCommand = "umask 077; mkdir -p '$RemoteDirectory'; cat > '$RemoteTemporary' && mv '$RemoteTemporary' '$RemotePath'"
$StartInfo = [Diagnostics.ProcessStartInfo]::new()
$StartInfo.FileName = $Ssh
$StartInfo.Arguments = "-F `"$SshConfig`" exitguide-gpu `"$RemoteCommand`""
$StartInfo.UseShellExecute = $false
$StartInfo.RedirectStandardInput = $true
$StartInfo.RedirectStandardOutput = $true
$StartInfo.RedirectStandardError = $true
$StartInfo.CreateNoWindow = $true

$Process = [Diagnostics.Process]::new()
$Process.StartInfo = $StartInfo
if (-not $Process.Start()) {
  throw "Could not start OpenSSH for artifact upload"
}
$InputFile = [IO.File]::OpenRead($Source)
try {
  $InputFile.CopyTo($Process.StandardInput.BaseStream)
  $Process.StandardInput.Close()
  $Process.WaitForExit()
}
finally {
  $InputFile.Dispose()
}
$ErrorOutput = $Process.StandardError.ReadToEnd()
if ($Process.ExitCode -ne 0) {
  throw "SSH artifact upload failed with exit code $($Process.ExitCode): $ErrorOutput"
}
$Process.Dispose()

$LocalInfo = Get-Item -LiteralPath $Source
$LocalHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()
$RemoteHashOutput = & $Ssh -F $SshConfig exitguide-gpu "sha256sum '$RemotePath'"
if ($LASTEXITCODE -ne 0) {
  throw "Could not verify uploaded artifact"
}
$RemoteHash = (($RemoteHashOutput | Where-Object { $_ -match '^[a-fA-F0-9]{64}\s' } | Select-Object -Last 1) -split '\s+')[0].ToLowerInvariant()
if ($RemoteHash -ne $LocalHash) {
  throw "Uploaded artifact checksum mismatch: local=$LocalHash remote=$RemoteHash"
}
Write-Host "Uploaded $($LocalInfo.FullName) -> $RemotePath"
Write-Host "bytes=$($LocalInfo.Length) sha256=$LocalHash"
