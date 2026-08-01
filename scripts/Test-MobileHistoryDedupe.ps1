$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$AnalysisHook = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/src/hooks/useAnalysisHistory.ts")
$FlowHook = Get-Content -Raw -LiteralPath (Join-Path $RepoRoot "apps/mobile/src/hooks/useFlowHistory.ts")

foreach ($Fragment in @("analysisHistoryKey", "analysis.analysis_id", "items.filter((item) => analysisHistoryKey(item.analysis) !== nextKey)")) {
  if (-not $AnalysisHook.Contains($Fragment)) {
    throw "useAnalysisHistory.ts is missing dedupe fragment: $Fragment"
  }
}

foreach ($Fragment in @("flowHistoryKey", "flow.flow_id", "items.filter((item) => flowHistoryKey(item.flow) !== nextKey)")) {
  if (-not $FlowHook.Contains($Fragment)) {
    throw "useFlowHistory.ts is missing dedupe fragment: $Fragment"
  }
}

Write-Host "Mobile history dedupe checks passed."
