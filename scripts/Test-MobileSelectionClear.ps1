$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$HomeScreen = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/src/screens/HomeScreen.tsx")
$Screenshot = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/src/components/ScreenshotAnalyzer.tsx")
$Flow = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/src/components/FlowScreenshotAnalyzer.tsx")

foreach ($Fragment in @("clearScreenshotSelection", "clearFlowSelection", "onClear={clearScreenshotSelection}", "onClear={clearFlowSelection}")) {
  if (-not $HomeScreen.Contains($Fragment)) {
    throw "HomeScreen.tsx is missing selection-clear fragment: $Fragment"
  }
}

foreach ($Fragment in @("onClear", "clearText")) {
  if (-not $Screenshot.Contains($Fragment)) {
    throw "ScreenshotAnalyzer.tsx is missing selection-clear fragment: $Fragment"
  }
}

foreach ($Fragment in @("onClear", "clearText")) {
  if (-not $Flow.Contains($Fragment)) {
    throw "FlowScreenshotAnalyzer.tsx is missing selection-clear fragment: $Fragment"
  }
}

Write-Host "Mobile selection clear checks passed."
