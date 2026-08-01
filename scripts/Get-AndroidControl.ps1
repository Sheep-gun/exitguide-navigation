param(
  [string]$Destination = ".artifacts/android-control/raw",
  [int[]]$Shard = @(),
  [switch]$All
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$TargetRoot = if ([System.IO.Path]::IsPathRooted($Destination)) {
  [System.IO.Path]::GetFullPath($Destination)
} else {
  [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Destination))
}
New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null

$BaseUrl = "https://storage.googleapis.com/gresearch/android_control"
$Curl = Join-Path $env:WINDIR "System32/curl.exe"
if (-not (Test-Path -LiteralPath $Curl)) {
  throw "Windows curl.exe was not found."
}

function Receive-AndroidControlFile {
  param([Parameter(Mandatory = $true)][string]$Name)
  $OutputPath = Join-Path $TargetRoot $Name
  & $Curl --fail --location --continue-at - --output $OutputPath "$BaseUrl/$Name"
  if ($LASTEXITCODE -ne 0) {
    throw "AndroidControl download failed for $Name with exit code $LASTEXITCODE"
  }
}

# The split metadata is small and always useful. Running this script with no
# shard flags intentionally downloads only these files.
Receive-AndroidControlFile -Name "splits.json"
Receive-AndroidControlFile -Name "test_subsplits.json"

$RequestedShards = if ($All) { 0..19 } else { $Shard }
foreach ($Index in ($RequestedShards | Sort-Object -Unique)) {
  if ($Index -lt 0 -or $Index -gt 19) {
    throw "AndroidControl shard must be between 0 and 19: $Index"
  }
  $Name = "android_control-{0:D5}-of-00020" -f $Index
  Receive-AndroidControlFile -Name $Name
}

if ($RequestedShards.Count -eq 0) {
  Write-Host "AndroidControl metadata downloaded to $TargetRoot. No 2.3-2.7 GB data shard was requested."
} else {
  Write-Host "AndroidControl shard download completed: $($RequestedShards -join ', ')"
}
