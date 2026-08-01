$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$OpenApiPath = Join-Path $RepoRoot ".artifacts/openapi.json"
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"

if (-not (Test-Path -LiteralPath $OpenApiPath)) {
  throw "OpenAPI artifact was not found. Run .\scripts\Export-OpenApi.ps1 first."
}

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$Script = @'
import json
from pathlib import Path
import sys

openapi_path = Path(sys.argv[1])
payload = json.loads(openapi_path.read_text(encoding="utf-8"))

required_paths = {
    "/v1/status",
    "/v1/providers",
    "/v1/readiness",
    "/v1/demo-quality",
    "/v1/goals",
    "/v1/demo-scenarios",
    "/v1/demo-flows",
    "/v1/synthetic-screens",
    "/v1/consent-cases",
    "/v1/consent-cases/quality",
    "/v1/terms-corpus",
    "/v1/terms-corpus/search",
    "/v1/terms-corpus/quality",
    "/v1/collection-registry",
    "/v1/collection-registry/quality",
    "/v1/navigation/routes",
    "/v1/navigation/guide",
    "/v1/navigation/agent/observe",
    "/v1/navigation/agent/graph",
    "/v1/navigation/agent/performance",
    "/v1/navigation/agent/performance/complete",
    "/v1/navigation/functions",
    "/v1/dark-pattern/inspect",
    "/v1/prompt/demo",
    "/v1/analyze",
    "/v1/analyze/demo",
    "/v1/analyze/flow",
    "/v1/analyze/flow/upload",
}

paths = set(payload.get("paths", {}))
missing_paths = sorted(required_paths - paths)
if missing_paths:
    raise AssertionError(f"OpenAPI artifact is missing path(s): {', '.join(missing_paths)}")

schemas = payload.get("components", {}).get("schemas", {})
required_schemas = {
    "AnalysisResponse",
    "FlowAnalysisResponse",
    "FlowAnalysisRequest",
    "DemoQualityResponse",
    "DemoReadinessResponse",
    "ConsentCaseCatalog",
    "ConsentCaseQualityResponse",
    "TermsCorpusCatalog",
    "TermsSearchResponse",
    "TermsCorpusQualityResponse",
    "CollectionRegistryCatalog",
    "CollectionRegistryQualityResponse",
    "NavigationRouteCatalog",
    "NavigationGuideRequest",
    "NavigationGuideResponse",
    "UniversalNavigationObserveRequest",
    "UniversalNavigationObserveResponse",
    "UniversalNavigationClientTiming",
    "UniversalNavigationPerformance",
    "UniversalNavigationCompletionTiming",
    "DarkPatternInspectRequest",
    "DarkPatternInspectResponse",
    "PromptPreviewResponse",
}
missing_schemas = sorted(required_schemas - set(schemas))
if missing_schemas:
    raise AssertionError(f"OpenAPI artifact is missing schema(s): {', '.join(missing_schemas)}")

flow_request = schemas["FlowAnalysisRequest"]["properties"]["scenario_ids"]
if flow_request.get("minItems") != 2 or flow_request.get("maxItems") != 6:
    raise AssertionError("FlowAnalysisRequest.scenario_ids must document a 2-6 item range")

flow_response_properties = schemas["FlowAnalysisResponse"]["properties"]
for field in ("flow_id", "screen_count", "highest_risk_screen_number", "risk_path"):
    if field not in flow_response_properties:
        raise AssertionError(f"FlowAnalysisResponse is missing {field}")

analysis_response_properties = schemas["AnalysisResponse"]["properties"]
if "analysis_id" not in analysis_response_properties:
    raise AssertionError("AnalysisResponse is missing analysis_id")
if analysis_response_properties["analysis_id"].get("pattern") != "^an_[a-f0-9]{12}$":
    raise AssertionError("AnalysisResponse.analysis_id must document the deterministic trace-id pattern")

if flow_response_properties["flow_id"].get("pattern") != "^fl_[a-f0-9]{12}$":
    raise AssertionError("FlowAnalysisResponse.flow_id must document the deterministic trace-id pattern")
'@

$Script | & $Python - $OpenApiPath
if ($LASTEXITCODE -ne 0) {
  throw "OpenAPI contract validation failed with exit code $LASTEXITCODE"
}

Write-Host "OpenAPI contract checks passed."
