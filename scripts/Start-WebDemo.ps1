$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$WebRoot = Join-Path $RepoRoot "apps/web-demo"
$VenvPython = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"

Push-Location $WebRoot
try {
  if (Test-Path $VenvPython) {
    & $VenvPython -m http.server 8020 --bind 127.0.0.1
    if ($LASTEXITCODE -ne 0) {
      exit $LASTEXITCODE
    }
    return
  }

  $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
  if ($PyLauncher) {
    & $PyLauncher.Source -3 -m http.server 8020 --bind 127.0.0.1
    if ($LASTEXITCODE -ne 0) {
      exit $LASTEXITCODE
    }
    return
  }

  $Python = Get-Command python -ErrorAction SilentlyContinue
  if ($Python) {
    & $Python.Source -m http.server 8020 --bind 127.0.0.1
    if ($LASTEXITCODE -ne 0) {
      exit $LASTEXITCODE
    }
    return
  }

  throw "Python was not found. Run .\scripts\Bootstrap-Windows.ps1 first, or install Python 3."
}
finally {
  Pop-Location
}
