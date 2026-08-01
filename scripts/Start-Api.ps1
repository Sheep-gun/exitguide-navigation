$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"

Import-Module (Join-Path $PSScriptRoot "ExitGuide.Common.psm1") -Force
Import-ExitGuideEnvFile -EnvFile (Join-Path $RepoRoot ".env") | Out-Null

if (-not (Test-Path $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$env:PYTHONDONTWRITEBYTECODE = "1"

Push-Location $ApiRoot
try {
  & $Python -m uvicorn app.main:app --host 0.0.0.0 --port 8010
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
}
finally {
  Pop-Location
}
