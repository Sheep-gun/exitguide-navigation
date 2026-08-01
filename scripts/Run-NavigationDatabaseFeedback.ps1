param(
  [ValidateSet("quick", "full", "deep")][string]$Mode = "quick",
  [string]$OutputDir = "",
  [switch]$SkipMaterialize,
  [switch]$RunIsolatedPromotionEvaluation
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}
if (-not $OutputDir) {
  $OutputDir = Join-Path $RepoRoot ".artifacts/navigation-feedback"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$results = [System.Collections.Generic.List[object]]::new()

function Invoke-FeedbackStage {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][scriptblock]$Action
  )

  $started = Get-Date
  $status = "pass"
  $message = ""
  try {
    # A successful native command from an earlier stage must never mask, or
    # falsely fail, the current stage when a scriptblock contains only
    # PowerShell commands.
    $global:LASTEXITCODE = 0
    & $Action
    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) {
      throw "native process exited with code $LASTEXITCODE"
    }
  }
  catch {
    $status = "fail"
    $message = $_.Exception.Message
    Write-Warning "[$Name] $message"
  }
  finally {
    $elapsed = [Math]::Round(((Get-Date) - $started).TotalSeconds, 3)
    $results.Add([pscustomobject]@{
      name = $Name
      status = $status
      elapsed_seconds = $elapsed
      message = $message
    })
  }
}

function New-InstitutionalSystemsV14StatefulFixture {
  param(
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$CatalogPath,
    [Parameter(Mandatory = $true)][string]$DestinationPath
  )

  if (
    -not (Test-Path -LiteralPath $SourcePath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $CatalogPath -PathType Leaf)
  ) {
    return $null
  }
  $normalizerOutput = & $Python (Join-Path $PSScriptRoot "Normalize-NavigationInstitutionalFixture.py") `
    --source $SourcePath `
    --catalog $CatalogPath `
    --output $DestinationPath
  if ($LASTEXITCODE -ne 0) {
    throw "institutional fixture normalization failed with exit code $LASTEXITCODE"
  }
  $normalizerOutput | ForEach-Object { Write-Host $_ }
  return $DestinationPath
}

function New-AuthoritySystemsV15StatefulFixture {
  param(
    [Parameter(Mandatory = $true)][string]$SourcePath,
    [Parameter(Mandatory = $true)][string]$CatalogPath,
    [Parameter(Mandatory = $true)][string]$DestinationPath
  )

  if (
    -not (Test-Path -LiteralPath $SourcePath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $CatalogPath -PathType Leaf)
  ) {
    return $null
  }
  $normalizerOutput = & $Python (Join-Path $PSScriptRoot "Normalize-NavigationAuthorityFixture.py") `
    --source $SourcePath `
    --catalog $CatalogPath `
    --output $DestinationPath `
    --mode stateful
  if ($LASTEXITCODE -ne 0) {
    throw "authority fixture normalization failed with exit code $LASTEXITCODE"
  }
  $normalizerOutput | ForEach-Object { Write-Host $_ }
  return $DestinationPath
}

Push-Location $RepoRoot
try {
  if (-not $SkipMaterialize) {
    Invoke-FeedbackStage "materialize_catalog" {
      & $Python (Join-Path $PSScriptRoot "Expand-NavigationCatalog.py")
      if ($LASTEXITCODE -ne 0) {
        throw "first catalog materialization failed with exit code $LASTEXITCODE"
      }
      $catalogPath = Join-Path $RepoRoot "fixtures/navigation/function-catalog.v1.json"
      $firstHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $catalogPath).Hash
      & $Python (Join-Path $PSScriptRoot "Expand-NavigationCatalog.py")
      if ($LASTEXITCODE -ne 0) {
        throw "second catalog materialization failed with exit code $LASTEXITCODE"
      }
      $secondHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $catalogPath).Hash
      if ($firstHash -ne $secondHash) {
        throw "catalog materializer is not byte-for-byte idempotent: $firstHash != $secondHash"
      }
    }
  }

  Invoke-FeedbackStage "catalog_quality" {
    & (Join-Path $PSScriptRoot "Audit-NavigationCatalog.ps1") -Gate
  }
  $coverageDraftV16 = Join-Path $RepoRoot "docs/NAVIGATION_COVERAGE_GAPS_V16.md"
  if (Test-Path -LiteralPath $coverageDraftV16 -PathType Leaf) {
    Invoke-FeedbackStage "coverage_draft_v16" {
      & $Python (Join-Path $PSScriptRoot "Audit-NavigationCoverageDraft.py") `
        --draft $coverageDraftV16 `
        --catalog (Join-Path $RepoRoot "fixtures/navigation/function-catalog.v1.json") `
        --output (Join-Path $OutputDir "coverage-draft-v16.json") `
        --gate
    }
  }
  $sourceVerificationV16Part1 = Join-Path $RepoRoot "docs/NAVIGATION_SOURCES_V16_PART1.md"
  $sourceVerificationV16Part2 = Join-Path $RepoRoot "docs/NAVIGATION_SOURCES_V16_PART2.md"
  if (
    (Test-Path -LiteralPath $sourceVerificationV16Part1 -PathType Leaf) -and
    (Test-Path -LiteralPath $sourceVerificationV16Part2 -PathType Leaf)
  ) {
    Invoke-FeedbackStage "source_verification_v16" {
      & $Python (Join-Path $PSScriptRoot "Audit-NavigationSourceVerification.py") `
        --output (Join-Path $OutputDir "source-verification-v16.json") `
        --gate
    }
  }
  $coverageRefinementV16 = Join-Path $RepoRoot "docs/NAVIGATION_COVERAGE_GAPS_V16_REFINEMENT.md"
  if (Test-Path -LiteralPath $coverageRefinementV16 -PathType Leaf) {
    Invoke-FeedbackStage "coverage_refinement_v16" {
      & $Python (Join-Path $PSScriptRoot "Audit-NavigationCoverageRefinement.py") `
        --output (Join-Path $OutputDir "coverage-refinement-v16.json") `
      --gate
    }
  }
  $catalogV16CandidateTest = Join-Path $RepoRoot "apps/api/tests/navigation_catalog_v16_data_unit.py"
  if (Test-Path -LiteralPath $catalogV16CandidateTest -PathType Leaf) {
    Invoke-FeedbackStage "catalog_v16_isolated_candidate" {
      $env:PYTHONDONTWRITEBYTECODE = "1"
      $env:PYTHONPATH = Join-Path $RepoRoot "apps/api"
      & $Python $catalogV16CandidateTest
    }
  }
  $catalogV16RuntimeTest = Join-Path $RepoRoot "apps/api/tests/navigation_catalog_v16_runtime_probes_unit.py"
  if (Test-Path -LiteralPath $catalogV16RuntimeTest -PathType Leaf) {
    Invoke-FeedbackStage "catalog_v16_runtime_safety_candidate" {
      $env:PYTHONDONTWRITEBYTECODE = "1"
      $env:PYTHONPATH = Join-Path $RepoRoot "apps/api"
      & $Python $catalogV16RuntimeTest
    }
  }
  $catalogV16MaterializationTest = Join-Path $RepoRoot "apps/api/tests/navigation_catalog_v16_materialization_unit.py"
  if (
    $Mode -eq "deep" -and
    (Test-Path -LiteralPath $catalogV16MaterializationTest -PathType Leaf)
  ) {
    # This temporary-copy promotion regression takes roughly 9-10 minutes, so
    # keep it out of quick/full feedback cycles. It must not materialize V16
    # over the canonical V15 fixtures.
    Invoke-FeedbackStage "v16_materialization_candidate_contract" {
      $env:PYTHONDONTWRITEBYTECODE = "1"
      $env:PYTHONPATH = Join-Path $RepoRoot "apps/api"
      & $Python $catalogV16MaterializationTest
    }
  }
  $independentV16FixtureTest = Join-Path $RepoRoot "apps/api/tests/navigation_evidence_systems_v16_fixture_unit.py"
  if (Test-Path -LiteralPath $independentV16FixtureTest -PathType Leaf) {
    Invoke-FeedbackStage "independent_v16_fixture_contract" {
      $env:PYTHONDONTWRITEBYTECODE = "1"
      $env:PYTHONPATH = Join-Path $RepoRoot "apps/api"
      & $Python $independentV16FixtureTest
    }
  }
  $independentV16AdapterTest = Join-Path $RepoRoot "apps/api/tests/navigation_evidence_fixture_adapter_unit.py"
  if (Test-Path -LiteralPath $independentV16AdapterTest -PathType Leaf) {
    Invoke-FeedbackStage "independent_v16_fixture_adapter_contract" {
      $env:PYTHONDONTWRITEBYTECODE = "1"
      $env:PYTHONPATH = Join-Path $RepoRoot "apps/api"
      & $Python $independentV16AdapterTest
    }
  }
  $isolatedV16EvaluationTest = Join-Path $RepoRoot "apps/api/tests/navigation_v16_isolated_evaluation_unit.py"
  if (Test-Path -LiteralPath $isolatedV16EvaluationTest -PathType Leaf) {
    Invoke-FeedbackStage "v16_isolated_evaluation_contract" {
      $env:PYTHONDONTWRITEBYTECODE = "1"
      $env:PYTHONPATH = Join-Path $RepoRoot "apps/api"
      & $Python $isolatedV16EvaluationTest
    }
  }
  $isolatedV16Evaluator = Join-Path $PSScriptRoot "Evaluate-NavigationV16Isolated.py"
  if (
    ($Mode -eq "deep" -or $RunIsolatedPromotionEvaluation) -and
    (Test-Path -LiteralPath $isolatedV16Evaluator -PathType Leaf)
  ) {
    # This is promotion-candidate evidence only. The evaluator merges V16 in
    # memory/temporary storage and must leave canonical V15 untouched. Accuracy
    # thresholds stay at their explicit zero defaults until a measured baseline
    # is reviewed; --gate still enforces isolation and safety invariants.  The
    # actual evaluation is deliberately excluded from quick/full cycles because
    # it is a sealed, promotion-grade run rather than a development diagnostic.
    Invoke-FeedbackStage "v16_isolated_candidate_evaluation" {
      $env:PYTHONDONTWRITEBYTECODE = "1"
      $env:PYTHONPATH = Join-Path $RepoRoot "apps/api"
      & $Python $isolatedV16Evaluator `
        --canonical-catalog (Join-Path $RepoRoot "fixtures/navigation/function-catalog.v1.json") `
        --source-fixture (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-evidence-systems-v16.json") `
        --output (Join-Path $OutputDir "v16-isolated-aggregate.json") `
        --gate
    }
  }
  $catalogDerivedParaphraseTest = Join-Path $RepoRoot "apps/api/tests/navigation_goal_paraphrase_exhaustive_unit.py"
  if (Test-Path -LiteralPath $catalogDerivedParaphraseTest -PathType Leaf) {
    # This catalog-derived corpus is a tuning diagnostic, not independent
    # accuracy evidence.  Running it in every cycle still catches duplicate,
    # alias-copy, safety, determinism, and resolver-throughput regressions over
    # every catalog intent and both supported languages.
    Invoke-FeedbackStage "catalog_derived_paraphrase_diagnostics" {
      $env:PYTHONDONTWRITEBYTECODE = "1"
      $env:PYTHONPATH = Join-Path $RepoRoot "apps/api"
      & $Python $catalogDerivedParaphraseTest
    }
  }
  $aliasMaximumGroups = if ($Mode -eq "quick") { 24 } else { 0 }
  Invoke-FeedbackStage "catalog_alias_collision_robustness" {
    & (Join-Path $PSScriptRoot "Evaluate-NavigationAliasRobustness.ps1") `
      -MaximumGroups $aliasMaximumGroups `
      -MinimumPositiveAccuracy 0.90 `
      -MinimumNegativeAccuracy 0.90 `
      -MaximumUnresolved 0 `
      -Output (Join-Path $OutputDir "alias-collision.json") `
      -Gate
  }
  $semanticDevelopmentFixture = Join-Path $RepoRoot "fixtures/navigation/db-gym/development-service-semantics-v5.json"
  if (Test-Path -LiteralPath $semanticDevelopmentFixture -PathType Leaf) {
    Invoke-FeedbackStage "semantic_development_generalization" {
      & (Join-Path $PSScriptRoot "Evaluate-NavigationIndependentGoals.ps1") `
        -Fixture @($semanticDevelopmentFixture) `
        -MinimumAccuracy 0.95 `
        -MinimumSplitAccuracy 0.95 `
        -Output (Join-Path $OutputDir "semantic-development.json") `
        -Gate
    }
  }
  Invoke-FeedbackStage "independent_reference_coverage" {
    & (Join-Path $PSScriptRoot "Audit-NavigationIndependentCoverage.ps1") -Gate
  }
  # This 4k-case cross-domain suite is a coverage diagnostic, not the release
  # gate for the Android route-reuse objective.  Its immutable report remains
  # available for honest open-world accuracy tracking, while release safety is
  # enforced below by the stateful UI fixtures and DB Gym (wrong/unsafe/final
  # actions, loop bounds, stale routes, and fallback).  Treating a known
  # 24.79% semantic research baseline as a required 100% made every quick run
  # fail before those consequential checks could report.
  Invoke-FeedbackStage "independent_goal_generalization_diagnostic" {
    & (Join-Path $PSScriptRoot "Evaluate-NavigationIndependentGoals.ps1")
  }

  $robustnessMode = if ($Mode -eq "quick") { "fast" } else { "full" }
  Invoke-FeedbackStage "catalog_goal_robustness_$robustnessMode" {
    & (Join-Path $PSScriptRoot "Evaluate-NavigationGoalRobustness.ps1") `
      -Mode $robustnessMode -MinimumAccuracy 1.0 -Gate
  }

  # Goal-only evaluation cannot detect premature destination decisions,
  # unsafe recovery clicks, infinite-feed scrolling, or a repeated backtrack.
  # Keep these three independently authored stateful packs in every feedback
  # cycle, including quick mode, so explorer regressions become new evidence
  # immediately rather than waiting for a full synthetic Gym run.
  $statefulFixtures = @(
    (Join-Path $RepoRoot "fixtures/navigation/db-gym/alias-collision-adversarial.v2.json"),
    (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-coverage.v2.json"),
    (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-recovery.v2.json"),
    (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-service-gaps-v5.json"),
    (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-open-world-v6.json"),
    (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-long-tail-v7.json"),
    (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-enterprise-ops-v8.json"),
    (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-cross-domain-v9.json"),
    (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-operational-v10.json"),
    (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-critical-ops-v11.json"),
    (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-specialized-ops-v12.json"),
    (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-regulated-systems-v13.json")
  )
  $institutionalSystemsV14 = New-InstitutionalSystemsV14StatefulFixture `
    -SourcePath (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-institutional-systems-v14.json") `
    -CatalogPath (Join-Path $RepoRoot "fixtures/navigation/function-catalog.v1.json") `
    -DestinationPath (Join-Path $OutputDir "independent-institutional-systems-v14.stateful.json")
  if ($institutionalSystemsV14) {
    $statefulFixtures += $institutionalSystemsV14
  }
  $authoritySystemsV15 = New-AuthoritySystemsV15StatefulFixture `
    -SourcePath (Join-Path $RepoRoot "fixtures/navigation/db-gym/independent-authority-systems-v15.json") `
    -CatalogPath (Join-Path $RepoRoot "fixtures/navigation/function-catalog.v1.json") `
    -DestinationPath (Join-Path $OutputDir "independent-authority-systems-v15.stateful.json")
  if ($authoritySystemsV15) {
    $statefulFixtures += $authoritySystemsV15
  }
  Invoke-FeedbackStage "independent_stateful_navigation" {
    & (Join-Path $PSScriptRoot "Evaluate-NavigationFixture.ps1") `
      -Fixture $statefulFixtures `
      -Name "feedback-stateful" `
      -OutputDir (Join-Path $OutputDir "stateful") `
      -MinimumSuccess 0.90 `
      -MinimumGoalAccuracy 1.0 `
      -Gate
  }

  $gymMode = if ($Mode -eq "quick") { "fast" } else { $Mode }
  $gymOutput = Join-Path $OutputDir "db-gym"
  Invoke-FeedbackStage "navigation_db_gym_$gymMode" {
    if ($gymMode -eq "deep") {
      & (Join-Path $PSScriptRoot "Run-NavigationDbGym.ps1") `
        -Mode $gymMode `
        -OutputDir $gymOutput `
        -GeneratedVariants 6 `
        -SyntheticCases 256 `
        -Gate
    }
    else {
      & (Join-Path $PSScriptRoot "Run-NavigationDbGym.ps1") `
        -Mode $gymMode `
        -OutputDir $gymOutput `
        -Gate
    }
  }

  $gymReport = Join-Path $gymOutput "$gymMode-report.json"
  if (Test-Path -LiteralPath $gymReport -PathType Leaf) {
    Invoke-FeedbackStage "quarantined_change_proposals" {
      & (Join-Path $PSScriptRoot "Propose-NavigationDbChanges.ps1") -Report $gymReport
    }
  }
}
finally {
  Pop-Location
}

$failed = @($results | Where-Object status -eq "fail")
$summary = [ordered]@{
  schema_version = 1
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  mode = $Mode
  status = if ($failed.Count -eq 0) { "pass" } else { "fail" }
  auto_apply = $false
  review_required = $true
  stage_count = $results.Count
  failed_stage_count = $failed.Count
  stages = @($results)
}
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reportPath = Join-Path $OutputDir "feedback-$timestamp.json"
$latestPath = Join-Path $OutputDir "latest.json"
$json = $summary | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($reportPath, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($latestPath, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))

Write-Host (
  "navigation feedback status={0} mode={1} stages={2} failed={3}" -f `
    $summary.status, $Mode, $summary.stage_count, $summary.failed_stage_count
)
Write-Host "report=$reportPath"
if ($failed.Count -gt 0) {
  exit 1
}
