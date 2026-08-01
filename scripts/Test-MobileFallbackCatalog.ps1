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

from app.services.flow_catalog import DEMO_FLOWS
from app.services.goals import GOAL_DESCRIPTIONS, GOAL_LABELS
from app.services.scenarios import DEMO_SCENARIOS


def read_source(relative_path: str) -> str:
    return (repo_root / relative_path).read_text(encoding="utf-8")


def extract_array(text: str, name: str) -> str:
    match = re.search(rf"export const {name}:.*?= \[(.*?)\];", text, re.DOTALL)
    if not match:
        raise AssertionError(f"Could not find {name}.")
    return match.group(1)


def extract_objects(array_source: str) -> list[str]:
    objects: list[str] = []
    depth = 0
    start: int | None = None
    for index, char in enumerate(array_source):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(array_source[start:index + 1])
                start = None
    return objects


def string_field(source: str, name: str) -> str:
    match = re.search(rf"{name}:\s*\"([^\"]*)\"", source)
    if not match:
        raise AssertionError(f"Could not find field {name}.")
    return match.group(1)


def description_field(source: str, descriptions: dict[str, str] | None = None) -> str:
    direct = re.search(r"description:\s*\"([^\"]*)\"", source)
    if direct:
        return direct.group(1)

    reference = re.search(r"description:\s*fallbackDescriptions\.([A-Za-z0-9_]+)", source)
    if reference and descriptions and reference.group(1) in descriptions:
        return descriptions[reference.group(1)]

    raise AssertionError("Could not find field description.")


def fallback_description_map(text: str) -> dict[str, str]:
    match = re.search(r"const fallbackDescriptions:.*?= \{(.*?)\};", text, re.DOTALL)
    if not match:
        raise AssertionError("Could not find fallbackDescriptions.")
    return dict(re.findall(r"([A-Za-z0-9_]+):\s*\"([^\"]*)\"", match.group(1)))


def string_list_field(source: str, name: str) -> tuple[str, ...]:
    match = re.search(rf"{name}:\s*\[(.*?)\]", source, re.DOTALL)
    if not match:
        raise AssertionError(f"Could not find list field {name}.")
    return tuple(re.findall(r"\"([^\"]*)\"", match.group(1)))


def fallback_goals() -> dict[str, tuple[str, str]]:
    source = read_source("apps/mobile/src/data/goals.ts")
    descriptions = fallback_description_map(source)
    body = extract_array(source, "fallbackGoals")
    return {
        string_field(item, "id"): (
            string_field(item, "title"),
            description_field(item, descriptions),
        )
        for item in extract_objects(body)
    }


def fallback_scenarios() -> dict[str, tuple[str, str, str, str]]:
    body = extract_array(read_source("apps/mobile/src/data/demoScenarios.ts"), "fallbackDemoScenarios")
    return {
        string_field(item, "id"): (
            string_field(item, "title"),
            description_field(item),
            string_field(item, "recommendedGoalId"),
            string_field(item, "fixtureFilename"),
        )
        for item in extract_objects(body)
    }


def fallback_flows() -> dict[str, tuple[str, str, str, tuple[str, ...]]]:
    body = extract_array(read_source("apps/mobile/src/data/demoFlows.ts"), "fallbackDemoFlows")
    return {
        string_field(item, "id"): (
            string_field(item, "title"),
            description_field(item),
            string_field(item, "goalId"),
            string_list_field(item, "scenarioIds"),
        )
        for item in extract_objects(body)
    }


expected_goals = {
    goal_id: (GOAL_LABELS[goal_id], description)
    for goal_id, description in GOAL_DESCRIPTIONS.items()
}
expected_scenarios = {
    scenario.id: (
        scenario.label,
        scenario.description,
        scenario.recommended_goal_id,
        scenario.fixture_filename,
    )
    for scenario in DEMO_SCENARIOS.values()
}
expected_flows = {
    flow.id: (
        flow.label,
        flow.description,
        flow.goal_id,
        tuple(flow.scenario_ids),
    )
    for flow in DEMO_FLOWS.values()
}

failures: list[str] = []
if fallback_goals() != expected_goals:
    failures.append("mobile fallback goal IDs, labels, or descriptions do not match API goals")
if fallback_scenarios() != expected_scenarios:
    failures.append("mobile fallback scenario IDs, labels, descriptions, goal references, or fixture filenames do not match API scenarios")
if fallback_flows() != expected_flows:
    failures.append("mobile fallback flow IDs, labels, descriptions, goal references, or scenario paths do not match API flows")

if failures:
    raise SystemExit("\n".join(failures))

print("Mobile fallback catalog checks passed.")
'@

$Script | & $Python - $RepoRoot
if ($LASTEXITCODE -ne 0) {
  throw "Mobile fallback catalog checks failed with exit code $LASTEXITCODE"
}
