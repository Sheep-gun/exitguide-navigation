$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ScriptFiles = Get-ChildItem -LiteralPath (Join-Path $RepoRoot "scripts") -File |
  Where-Object { $_.Extension -in @(".ps1", ".psm1") }
$TotalErrors = 0

foreach ($ScriptFile in $ScriptFiles) {
  $ParseErrors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($ScriptFile.FullName, [ref]$null, [ref]$ParseErrors) | Out-Null
  if ($ParseErrors.Count) {
    $TotalErrors += $ParseErrors.Count
    Write-Host "PowerShell parse errors in $($ScriptFile.Name):"
    $ParseErrors | ForEach-Object { Write-Host "  $($_.Message)" }
  }
}

if ($TotalErrors -gt 0) {
  throw "$TotalErrors PowerShell parse error(s) found."
}

Write-Host "PowerShell script syntax checks passed."
