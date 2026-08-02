$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

Push-Location $ApiRoot
try {
  $env:PYTHONDONTWRITEBYTECODE = "1"
  $env:PYTHONPATH = $ApiRoot
  $UnitTests = @(
    "tests/contracts_unit.py",
    "tests/dataset_adapters_unit.py",
    "tests/public_dataset_adapters_unit.py",
    "tests/source_roles_unit.py",
    "tests/public_corpus_unit.py",
    "tests/review_packet_unit.py",
    "tests/review_results_unit.py",
    "tests/review_import_unit.py",
    "tests/rules_unit.py",
    "tests/demo_quality_unit.py",
    "tests/consent_case_dataset_unit.py",
    "tests/terms_corpus_unit.py",
    "tests/terms_ingestion_unit.py",
    "tests/collection_registry_unit.py",
    "tests/solar_demo_workflows_unit.py",
    "tests/navigation_unit.py",
    "tests/navigation_catalog_quality_unit.py",
    "tests/navigation_catalog_v3_data_unit.py",
    "tests/navigation_catalog_v4_data_unit.py",
    "tests/navigation_catalog_v5_data_unit.py",
    "tests/navigation_catalog_v6_data_unit.py",
    "tests/navigation_catalog_v7_data_unit.py",
    "tests/navigation_catalog_v8_data_unit.py",
    "tests/navigation_catalog_v9_data_unit.py",
    "tests/navigation_catalog_v10_data_unit.py",
    "tests/navigation_catalog_v11_data_unit.py",
    "tests/navigation_catalog_v12_data_unit.py",
    "tests/navigation_catalog_v13_data_unit.py",
    "tests/navigation_catalog_v14_data_unit.py",
    "tests/navigation_catalog_v15_data_unit.py",
    "tests/navigation_catalog_v16_data_unit.py",
    "tests/navigation_catalog_v16_materialization_unit.py",
    "tests/navigation_catalog_v16_runtime_probes_unit.py",
    "tests/navigation_evidence_systems_v16_fixture_unit.py",
    "tests/navigation_evidence_fixture_adapter_unit.py",
    "tests/navigation_v16_isolated_evaluation_unit.py",
    "tests/navigation_coverage_draft_audit_unit.py",
    "tests/navigation_source_verification_audit_unit.py",
    "tests/navigation_coverage_refinement_audit_unit.py",
    "tests/navigation_long_tail_v3_fixture_unit.py",
    "tests/navigation_broad_services_v4_fixture_unit.py",
    "tests/navigation_service_gaps_v5_fixture_unit.py",
    "tests/navigation_open_world_v6_fixture_unit.py",
    "tests/navigation_long_tail_v7_fixture_unit.py",
    "tests/navigation_enterprise_ops_v8_fixture_unit.py",
    "tests/navigation_cross_domain_v9_fixture_unit.py",
    "tests/navigation_operational_v10_fixture_unit.py",
    "tests/navigation_critical_ops_v11_fixture_unit.py",
    "tests/navigation_specialized_ops_v12_fixture_unit.py",
    "tests/navigation_regulated_systems_v13_fixture_unit.py",
    "tests/navigation_institutional_systems_v14_fixture_unit.py",
    "tests/navigation_authority_systems_v15_fixture_unit.py",
    "tests/navigation_authority_fixture_adapter_unit.py",
    "tests/navigation_development_service_semantics_v5_unit.py",
    "tests/navigation_public_productivity_system_unit.py",
    "tests/navigation_independent_coverage_unit.py",
    "tests/navigation_sealed_realistic_unit.py",
    "tests/navigation_goal_robustness_unit.py",
    "tests/navigation_goal_generalization_unit.py",
    "tests/navigation_goal_prose_development_unit.py",
    "tests/navigation_goal_prose_v15_development_unit.py",
    "tests/navigation_goal_paraphrase_exhaustive_unit.py",
    "tests/navigation_function_equivalence_unit.py",
    "tests/navigation_function_equivalence_runtime_unit.py",
    "tests/navigation_function_catalog_unit.py",
    "tests/navigation_function_catalog_performance_unit.py",
    "tests/navigation_goal_resolver_performance_unit.py",
    "tests/navigation_alias_robustness_unit.py",
    "tests/navigation_alias_context_overrides_unit.py",
    "tests/navigation_context_phrase_index_unit.py",
    "tests/navigation_goal_semantic_fallback_unit.py",
    "tests/navigation_goal_char_integration_unit.py",
    "tests/navigation_goal_char_retrieval_unit.py",
    "tests/navigation_db_gym_unit.py",
    "tests/navigation_recovery_fixture_unit.py",
    "tests/navigation_performance_unit.py",
    "tests/navigation_runtime_telemetry_unit.py",
    "tests/navigation_graph_merge_unit.py",
    "tests/android_control_index_unit.py",
    "tests/navigation_vlm_unit.py",
    "tests/universal_navigation_agent_unit.py",
    "tests/navigation_gold_recording_unit.py",
    "tests/navigation_gold_retrieval_unit.py",
    "tests/navigation_training_examples_unit.py",
    "tests/navigation_learning_queue_unit.py",
    "tests/navigation_agent_only_evaluation_unit.py",
    "tests/navigation_portable_backup_unit.py",
    "tests/navigation_policy_reranker_unit.py",
    "tests/universal_navigation_explorer_unit.py",
    "tests/navigation_semantics_safety_unit.py",
    "tests/universal_navigation_api_unit.py",
    "tests/universal_navigation_benchmark.py",
    "tests/cross_app_menu_benchmark.py",
    "tests/keep_real_device_awake_static_unit.py",
    "tests/real_device_action_safety_unit.py",
    "tests/real_device_privacy_unit.py",
    "tests/real_device_app_discovery_unit.py",
    "tests/real_device_observation_goal_manifest_unit.py",
    "tests/real_device_observation_corpus_unit.py",
    "tests/real_device_observation_collector_unit.py",
    "tests/real_device_observation_safety_unit.py",
    "tests/real_device_scroll_validation_unit.py",
    "tests/real_device_observation_loop_unit.py",
    "tests/real_device_function_graph_artifacts_unit.py",
    "tests/real_device_goal_candidates_unit.py",
    "tests/real_device_goal_task_planner_unit.py",
    "tests/real_device_task_metrics_unit.py",
    "tests/real_device_sensitive_navigation_unit.py",
    "tests/dark_pattern_unit.py",
    "tests/desktop_unit.py"
  )
  foreach ($UnitTest in $UnitTests) {
    & $Python $UnitTest
    if ($LASTEXITCODE -ne 0) {
      throw "API unit check $UnitTest failed with exit code $LASTEXITCODE"
    }
  }
}
finally {
  Pop-Location
}
