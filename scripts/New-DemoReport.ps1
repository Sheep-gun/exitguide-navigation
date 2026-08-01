$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"

Push-Location $ApiRoot
try {
  $env:PYTHONDONTWRITEBYTECODE = "1"
  $env:PYTHONPATH = $ApiRoot
  & $Python tests/demo_report.py
}
finally {
  Pop-Location
}

if ($LASTEXITCODE -ne 0) {
  throw "Demo report generation failed with exit code $LASTEXITCODE"
}
