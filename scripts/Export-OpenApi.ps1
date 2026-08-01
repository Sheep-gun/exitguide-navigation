$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"
$OutputPath = Join-Path $RepoRoot ".artifacts/openapi.json"

if (-not (Test-Path $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

New-Item -ItemType Directory -Path (Split-Path -Parent $OutputPath) -Force | Out-Null
$PreviousPythonPath = [System.Environment]::GetEnvironmentVariable("PYTHONPATH", "Process")
$HadPythonPath = $null -ne $PreviousPythonPath
$PreviousOpenApiOutput = [System.Environment]::GetEnvironmentVariable("EXITGUIDE_OPENAPI_OUTPUT", "Process")
$HadOpenApiOutput = $null -ne $PreviousOpenApiOutput

Push-Location $ApiRoot
try {
  $env:PYTHONPATH = $ApiRoot
  $env:EXITGUIDE_OPENAPI_OUTPUT = $OutputPath

  @"
import json
import os
from pathlib import Path

from app.main import app

output_path = Path(os.environ["EXITGUIDE_OPENAPI_OUTPUT"])
output_path.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {output_path}")
"@ | & $Python -
}
finally {
  if ($HadOpenApiOutput) {
    $env:EXITGUIDE_OPENAPI_OUTPUT = $PreviousOpenApiOutput
  } else {
    Remove-Item Env:\EXITGUIDE_OPENAPI_OUTPUT -ErrorAction SilentlyContinue
  }

  if ($HadPythonPath) {
    $env:PYTHONPATH = $PreviousPythonPath
  } else {
    Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
  }

  Pop-Location
}
