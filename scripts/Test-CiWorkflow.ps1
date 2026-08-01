$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$WorkflowPath = Join-Path $RepoRoot ".github/workflows/exitguide-checks.yml"
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"

if (-not (Test-Path -LiteralPath $WorkflowPath)) {
  throw "GitHub Actions workflow was not found."
}

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$Script = @'
from pathlib import Path
import sys

import yaml

workflow_path = Path(sys.argv[1])
payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

if not isinstance(payload, dict):
    raise AssertionError("workflow root must be a mapping")

trigger = payload.get("on", payload.get(True))
if not trigger:
    raise AssertionError("workflow must define push/pull_request triggers")

jobs = payload.get("jobs")
if not isinstance(jobs, dict) or "local-checks" not in jobs:
    raise AssertionError("workflow must define local-checks job")

steps = jobs["local-checks"].get("steps", [])
step_text = str(steps)
required = [
    "actions/checkout@v4",
    "actions/setup-python@v5",
    "actions/cache@v4",
    ".tools",
    "apps/mobile/node_modules",
    "Publish-GitHub.ps1",
    "Bootstrap-Windows.ps1",
]
missing = [item for item in required if item not in step_text]
if missing:
    raise AssertionError(f"workflow is missing required step(s): {', '.join(missing)}")
'@

$Script | & $Python - $WorkflowPath
if ($LASTEXITCODE -ne 0) {
  throw "CI workflow validation failed with exit code $LASTEXITCODE"
}

Write-Host "CI workflow checks passed."
