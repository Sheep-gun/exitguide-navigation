param(
  [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

if (-not $OutputPath) {
  $OutputPath = Join-Path $RepoRoot ".artifacts/terms-corpus.sqlite"
}

if (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
  $OutputPath = Join-Path $RepoRoot $OutputPath
}

$Script = @'
from pathlib import Path
import sys

from app.services.terms_corpus import build_terms_corpus_sqlite

output = build_terms_corpus_sqlite(Path(sys.argv[1]))
print(f"wrote {output}")
'@

Push-Location $ApiRoot
try {
  $env:PYTHONDONTWRITEBYTECODE = "1"
  $env:PYTHONPATH = $ApiRoot
  $Script | & $Python - $OutputPath
  if ($LASTEXITCODE -ne 0) {
    throw "Terms corpus build failed with exit code $LASTEXITCODE"
  }
}
finally {
  Pop-Location
}
