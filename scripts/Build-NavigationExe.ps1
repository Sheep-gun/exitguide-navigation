$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"
$EntryPoint = Join-Path $RepoRoot "apps/launcher/egl_navigation_mvp.py"
$DistDir = Join-Path $RepoRoot "dist"
$WorkDir = Join-Path $RepoRoot "build/navigation-exe"
$ExePath = Join-Path $DistDir "EGL-Navigation-MVP.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python -c "import PyInstaller" 2>$null
$PyInstallerImportExitCode = $LASTEXITCODE
$ErrorActionPreference = $PreviousErrorActionPreference
if ($PyInstallerImportExitCode -ne 0) {
  Write-Host "Installing PyInstaller into the project virtual environment..."
  & $Python -m pip install pyinstaller
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller installation failed with exit code $LASTEXITCODE"
  }
}

New-Item -ItemType Directory -Path $DistDir, $WorkDir -Force | Out-Null

$Arguments = @(
  "--noconfirm",
  "--clean",
  "--onefile",
  "--windowed",
  "--noupx",
  "--name", "EGL-Navigation-MVP",
  "--paths", (Join-Path $RepoRoot "apps/api"),
  "--add-data", ((Join-Path $RepoRoot "apps/web-demo") + ";apps/web-demo"),
  "--add-data", ((Join-Path $RepoRoot "fixtures") + ";fixtures"),
  "--collect-all", "uvicorn",
  "--hidden-import", "httptools",
  "--hidden-import", "websockets",
  "--distpath", $DistDir,
  "--workpath", $WorkDir,
  "--specpath", $WorkDir,
  $EntryPoint
)

& $Python -m PyInstaller @Arguments
if ($LASTEXITCODE -ne 0) {
  throw "Navigation executable build failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path -LiteralPath $ExePath)) {
  throw "Navigation executable was not created: $ExePath"
}

$SizeMb = [math]::Round((Get-Item -LiteralPath $ExePath).Length / 1MB, 1)
Write-Host "Built $ExePath ($SizeMb MB)"
