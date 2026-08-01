$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Checks = @{
  "apps/mobile/src/components/ProofCard.tsx" = @("traceId", "formatProofCard(proofCard, traceId)")
  "apps/mobile/src/components/AnalysisResult.tsx" = @("traceId={analysis.analysis_id}")
  "apps/mobile/src/components/FlowResult.tsx" = @("traceId={flow.flow_id}")
  "apps/mobile/src/components/AnalysisHistory.tsx" = @("item.analysis.analysis_id")
  "apps/mobile/src/components/FlowHistory.tsx" = @("item.flow.flow_id")
}

foreach ($RelativePath in $Checks.Keys) {
  $Path = Join-Path $RepoRoot $RelativePath
  if (-not (Test-Path -LiteralPath $Path)) {
    throw "Missing mobile trace display source: $RelativePath"
  }

  $Text = Get-Content -Raw -LiteralPath $Path
  foreach ($Fragment in $Checks[$RelativePath]) {
    if (-not $Text.Contains($Fragment)) {
      throw "$RelativePath is missing trace display fragment: $Fragment"
    }
  }
}

Write-Host "Mobile trace display checks passed."
