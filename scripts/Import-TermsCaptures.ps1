param(
  [string]$InputPath = "",
  [string]$OutputPath = "",
  [switch]$FailOnRejected
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

if (-not $InputPath) {
  $InputPath = Join-Path $RepoRoot ".artifacts/terms-captures/inbox"
}

if (-not $OutputPath) {
  $OutputPath = Join-Path $RepoRoot ".artifacts/terms-corpus.sqlite"
}

if (-not [System.IO.Path]::IsPathRooted($InputPath)) {
  $InputPath = Join-Path $RepoRoot $InputPath
}

if (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
  $OutputPath = Join-Path $RepoRoot $OutputPath
}

$Script = @'
from pathlib import Path
import sys

from app.services.terms_ingestion import ingest_terms_captures

result = ingest_terms_captures(Path(sys.argv[1]), Path(sys.argv[2]))
print(result.model_dump_json(indent=2))
if sys.argv[3] == "1" and result.rejected_count:
    sys.exit(2)
'@

Push-Location $ApiRoot
try {
  $env:PYTHONDONTWRITEBYTECODE = "1"
  $env:PYTHONPATH = $ApiRoot
  $Script | & $Python - $InputPath $OutputPath ($(if ($FailOnRejected) { "1" } else { "0" }))
  if ($LASTEXITCODE -ne 0) {
    throw "Terms capture import failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}
