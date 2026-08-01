$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$Script = @'
from pathlib import Path
import re
import sys

repo_root = Path(sys.argv[1])
sys.path.insert(0, str(repo_root / "apps" / "api"))

from app.main import app

method_pattern = re.compile(r"`?(GET|POST|PUT|PATCH|DELETE)\s+(/[^`\s:)]+)", re.IGNORECASE)


def actual_routes() -> set[tuple[str, str]]:
    payload = app.openapi()
    routes: set[tuple[str, str]] = set()
    for path, methods in payload.get("paths", {}).items():
        for method in methods:
            normalized = method.upper()
            if normalized in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                routes.add((normalized, path))
    return routes


def documented_routes(path: Path) -> set[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    return {
        (match.group(1).upper(), match.group(2).rstrip(".,"))
        for match in method_pattern.finditer(text)
    }


actual = actual_routes()
openapi = app.openapi()
documents = [
    repo_root / "docs" / "API_CONTRACT.md",
    repo_root / "docs" / "HANDOFF.md",
]
api_contract_text = (repo_root / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")

failures: list[str] = []
for document in documents:
    documented = documented_routes(document)
    missing = sorted(actual - documented)
    stale = sorted(documented - actual)
    if missing:
        rendered = ", ".join(f"{method} {path}" for method, path in missing)
        failures.append(f"{document.relative_to(repo_root)} missing route(s): {rendered}")
    if stale:
        rendered = ", ".join(f"{method} {path}" for method, path in stale)
        failures.append(f"{document.relative_to(repo_root)} has stale route(s): {rendered}")

schema_field_contracts = {
    "AnalysisResponse": [
        "analysis_id",
        "goal_id",
        "goal_label",
        "screen_title",
        "analysis_mode",
        "overall_risk",
        "alignment_score",
        "risk_counts",
        "recommended_action",
        "proof_card",
    ],
    "FlowAnalysisResponse": [
        "flow_id",
        "goal_id",
        "goal_label",
        "overall_risk",
        "alignment_score",
        "screen_count",
        "highest_risk_screen_number",
        "risk_counts",
        "risk_path",
        "screens",
        "proof_card",
    ],
}

schemas = openapi.get("components", {}).get("schemas", {})
for schema_name, required_fields in schema_field_contracts.items():
    schema = schemas.get(schema_name)
    if not schema:
        failures.append(f"OpenAPI schema missing {schema_name}")
        continue
    properties = schema.get("properties", {})
    for field in required_fields:
        if field not in properties:
            failures.append(f"OpenAPI schema {schema_name} missing field {field}")
        if f"`{field}`" not in api_contract_text and f"`{field}[]`" not in api_contract_text:
            failures.append(f"docs/API_CONTRACT.md does not document {schema_name}.{field}")

if failures:
    raise SystemExit("\n".join(failures))

print("Documentation contract sync checks passed.")
'@

$Script | & $Python - $RepoRoot
if ($LASTEXITCODE -ne 0) {
  throw "Documentation sync checks failed with exit code $LASTEXITCODE"
}
