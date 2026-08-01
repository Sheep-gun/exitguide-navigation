from __future__ import annotations

"""Fail-closed validator for emulator-observation navigation corpora.

The validator deliberately keeps emulator observations separate from the
canonical function catalog.  It validates one resumable collection run and
the repository governance boundary that surrounds it; it never rewrites the
corpus or promotes a discovered route.
"""

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OBSERVATION_ROOT = ROOT / ".artifacts" / "navigation-observations"

EXPECTED_CATALOG_VERSION = "15.0.0"
EXPECTED_CATALOG_SHA256 = (
    "e0eeef03195a48ec8172421926d08c30823bc678c72ea72082bb513dbec36e24"
)
EXPECTED_EQUIVALENCE_SHA256 = (
    "197aa0253c0353e439a6679a3597efed25297c44c554a15c0402a30f077ab2e8"
)
EXPECTED_DOMAIN_COUNT = 179
EXPECTED_FUNCTION_COUNT = 2866
EXPECTED_TERMINAL_FUNCTION_COUNT = 2660
EXPECTED_INTENT_COUNT = 2660

REQUIRED_TABLES = frozenset(
    {
        "apps",
        "runs",
        "screens",
        "elements",
        "transitions",
        "goals",
        "failures",
        "metrics",
        "annotations",
    }
)

# Each tuple is one semantic field.  The first spelling is the preferred
# schema name; later spellings are accepted compatibility aliases.
REQUIRED_COLUMN_GROUPS: Mapping[str, tuple[tuple[str, ...], ...]] = {
    "apps": (
        ("app_package",),
        ("app_name",),
        ("app_version",),
        ("locale",),
    ),
    "runs": (
        ("run_id",),
        ("provenance",),
        ("route_lifecycle", "route_status"),
        ("started_at", "collected_at", "created_at"),
    ),
    "screens": (
        ("screen_id",),
        ("run_id",),
        ("app_package",),
        ("app_name",),
        ("app_version",),
        ("locale",),
        ("screen_signature", "screen_fingerprint"),
        ("screenshot_path",),
        ("accessibility_tree_path", "ui_tree_path"),
        ("activity_name",),
        ("title_text", "window_title"),
        ("visible_texts_json", "visible_texts"),
        ("content_descriptions_json", "content_descriptions"),
        ("resource_ids_json", "resource_ids"),
        ("scrollable_regions_json", "scrollable_regions"),
        ("screen_type",),
        ("prerequisites_json", "prerequisites"),
        ("contains_personal_data", "has_personal_data"),
        ("collected_at", "observed_at"),
    ),
    "elements": (
        ("element_id",),
        ("screen_id",),
        ("text",),
        ("content_description",),
        ("resource_id",),
        ("class_name",),
        ("bounds_json", "bounds"),
        ("clickable",),
        ("enabled",),
        ("selected",),
        ("inferred_icon_semantics_json", "icon_semantics_json", "icon_meaning"),
        ("semantic_function_id",),
        ("synonyms_json", "synonyms"),
        ("expected_outcome",),
        ("risk_level",),
        ("is_final_action", "final_action"),
        ("confidence",),
        ("evidence_json", "evidence"),
    ),
    "transitions": (
        ("transition_id",),
        ("run_id",),
        ("source_screen_id",),
        ("target_screen_id",),
        ("action_type",),
        ("element_id",),
        ("coordinates_json", "click_coordinates_json", "coordinates"),
        ("scroll_direction",),
        ("scroll_distance",),
        ("transition_ms", "transition_time_ms"),
        ("success",),
        ("back_available",),
        ("is_loop", "loop_detected"),
        ("error_text", "error_message"),
        ("auto_executed",),
        ("unsafe_action", "unsafe_click"),
        ("is_final_action", "final_action"),
    ),
    "goals": (
        ("goal_id",),
        ("run_id",),
        ("app_package",),
        ("user_goal", "goal_text"),
        ("standard_goal_id", "target_function"),
        ("terminal_candidate_screen_id", "destination_screen_id"),
        ("terminal_candidate_element_id", "destination_element_id"),
        ("status",),
    ),
    "failures": (
        ("failure_id",),
        ("run_id",),
        ("app_package",),
        ("user_goal", "goal_text"),
        ("screen_id",),
        ("selected_candidate",),
        ("correct_candidate",),
        ("failure_reason",),
        ("required_synonym_or_label", "required_label"),
        ("policy_change",),
        ("retest_result",),
    ),
    "metrics": (
        ("metric_id",),
        ("run_id",),
        ("app_package",),
    ),
    "annotations": (
        ("annotation_id",),
        ("run_id",),
        ("entity_type",),
        ("entity_id",),
        ("annotation_json", "value_json", "annotation"),
    ),
}

REQUIRED_WIDE_METRIC_GROUPS: Mapping[str, tuple[str, ...]] = {
    "perception_clickable_recall": (
        "perception_clickable_recall",
        "clickable_element_recall",
    ),
    "perception_icon_text_link_accuracy": (
        "perception_icon_text_link_accuracy",
        "icon_text_link_accuracy",
    ),
    "semantic_goal_match_accuracy": (
        "semantic_goal_match_accuracy",
        "goal_function_match_accuracy",
    ),
    "semantic_disambiguation_accuracy": (
        "semantic_disambiguation_accuracy",
        "similar_function_disambiguation_accuracy",
    ),
    "destination_found_success": (
        "destination_found_success",
        "destination_found",
        "destination_success",
    ),
    "wrong_terminal_destination": (
        "wrong_terminal_destination",
        "wrong_terminal",
    ),
    "exploration_time_ms": ("exploration_time_ms", "duration_ms"),
    "click_count": ("click_count",),
    "scroll_count": ("scroll_count",),
    "back_count": ("back_count",),
    "repeat_screen_visit_count": (
        "repeat_screen_visit_count",
        "revisit_count",
    ),
    "user_intervention_count": ("user_intervention_count",),
    "unsafe_auto_click_count": ("unsafe_auto_click_count", "unsafe_click_count"),
    "final_action_auto_click_count": (
        "final_action_auto_click_count",
        "final_auto_click_count",
    ),
    "graph_reuse_rate": ("graph_reuse_rate", "update_graph_reuse_rate"),
}

# A normalized/long metrics table is also accepted.  These names let a corpus
# retain raw measurements and derived median/P95 rows without a wide table.
REQUIRED_LONG_METRIC_ALIASES: Mapping[str, frozenset[str]] = {
    semantic: frozenset(re.sub(r"[^a-z0-9]+", "", alias.casefold()) for alias in aliases)
    for semantic, aliases in REQUIRED_WIDE_METRIC_GROUPS.items()
}

TEXT_SUFFIXES = frozenset({".json", ".jsonl", ".xml", ".txt", ".md", ".csv", ".tsv"})
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)")
KOREAN_RESIDENT_ID_PATTERN = re.compile(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)")
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "api_key",
        re.compile(
            r"(?i)(?:api[_ -]?key|secret|access[_ -]?token|authorization)[\"']?\s*[=:]\s*[\"']?"
            r"(?:bearer\s+)?[A-Za-z0-9_./+~=-]{12,}"
        ),
    ),
    ("friendli_key", re.compile(r"\bflp_[A-Za-z0-9_-]{16,}\b")),
    ("generic_secret_key", re.compile(r"\b(?:sk|pk)_[A-Za-z0-9_-]{20,}\b")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}\b")),
)


def _finding(code: str, message: str, location: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "location": location}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def _sqlite_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _pick(columns: set[str], *names: str) -> str | None:
    return next((name for name in names if name in columns), None)


def _scalar(connection: sqlite3.Connection, query: str, parameters: Sequence[Any] = ()) -> Any:
    row = connection.execute(query, tuple(parameters)).fetchone()
    return None if row is None else row[0]


def _is_truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y", "unsafe", "final"}
    return bool(value)


def _nested(mapping: Mapping[str, Any], *paths: str) -> Any:
    for path in paths:
        value: Any = mapping
        found = True
        for part in path.split("."):
            if not isinstance(value, Mapping) or part not in value:
                found = False
                break
            value = value[part]
        if found:
            return value
    return None


def _validate_canonical(repo_root: Path, errors: list[dict[str, str]], checks: dict[str, Any]) -> None:
    catalog_path = repo_root / "fixtures" / "navigation" / "function-catalog.v1.json"
    equivalence_path = repo_root / "fixtures" / "navigation" / "function-equivalence.v1.json"
    if not catalog_path.is_file():
        errors.append(_finding("canonical_missing", "canonical V15 catalog is missing", str(catalog_path)))
        return
    if not equivalence_path.is_file():
        errors.append(
            _finding("equivalence_missing", "function-equivalence overlay is missing", str(equivalence_path))
        )
        return

    catalog_sha = _sha256(catalog_path)
    equivalence_sha = _sha256(equivalence_path)
    checks["canonical_catalog_sha256"] = catalog_sha
    checks["equivalence_sha256"] = equivalence_sha
    if catalog_sha != EXPECTED_CATALOG_SHA256:
        errors.append(
            _finding(
                "canonical_sha_mismatch",
                f"expected frozen V15 SHA-256 {EXPECTED_CATALOG_SHA256}, got {catalog_sha}",
                str(catalog_path),
            )
        )
    if equivalence_sha != EXPECTED_EQUIVALENCE_SHA256:
        errors.append(
            _finding(
                "equivalence_sha_mismatch",
                f"expected frozen equivalence SHA-256 {EXPECTED_EQUIVALENCE_SHA256}, got {equivalence_sha}",
                str(equivalence_path),
            )
        )

    try:
        catalog = _load_json(catalog_path)
        equivalence = _load_json(equivalence_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        errors.append(_finding("canonical_parse_error", str(error), str(catalog_path)))
        return

    functions = catalog.get("functions", []) if isinstance(catalog, Mapping) else []
    intents = catalog.get("intents", []) if isinstance(catalog, Mapping) else []
    domains = {
        str(item.get("domain", ""))
        for item in functions
        if isinstance(item, Mapping) and str(item.get("domain", ""))
    }
    terminal_count = sum(
        1 for item in functions if isinstance(item, Mapping) and _is_truthy(item.get("terminal"))
    )
    actual = {
        "version": catalog.get("catalog_version") if isinstance(catalog, Mapping) else None,
        "domains": len(domains),
        "functions": len(functions),
        "terminal_functions": terminal_count,
        "intents": len(intents),
    }
    expected = {
        "version": EXPECTED_CATALOG_VERSION,
        "domains": EXPECTED_DOMAIN_COUNT,
        "functions": EXPECTED_FUNCTION_COUNT,
        "terminal_functions": EXPECTED_TERMINAL_FUNCTION_COUNT,
        "intents": EXPECTED_INTENT_COUNT,
    }
    checks["canonical_catalog"] = actual
    if actual != expected:
        errors.append(
            _finding("canonical_shape_mismatch", f"expected frozen V15 shape {expected}, got {actual}", str(catalog_path))
        )

    provenance = equivalence.get("provenance", {}) if isinstance(equivalence, Mapping) else {}
    eq_counts = equivalence.get("audit_counts", {}) if isinstance(equivalence, Mapping) else {}
    if isinstance(provenance, Mapping):
        eq_version = provenance.get("catalog_version")
        if eq_version != EXPECTED_CATALOG_VERSION:
            errors.append(
                _finding(
                    "equivalence_version_mismatch",
                    f"equivalence overlay must target {EXPECTED_CATALOG_VERSION}, got {eq_version!r}",
                    str(equivalence_path),
                )
            )
    if isinstance(eq_counts, Mapping):
        expected_counts = {
            "physical_function_count": EXPECTED_FUNCTION_COUNT,
            "physical_intent_count": EXPECTED_INTENT_COUNT,
        }
        for key, expected_value in expected_counts.items():
            value = eq_counts.get(key)
            if value is not None and value != expected_value:
                errors.append(
                    _finding(
                        "equivalence_count_mismatch",
                        f"{key} must be {expected_value}, got {value!r}",
                        str(equivalence_path),
                    )
                )


def _validate_version_governance(
    repo_root: Path, errors: list[dict[str, str]], checks: dict[str, Any]
) -> None:
    forbidden_v22_globs = (
        "scripts/navigation_catalog_v22*",
        "apps/api/tests/navigation_catalog_v22*",
        "fixtures/navigation/**/*v22*",
        "docs/NAVIGATION_COVERAGE_GAPS_V22*",
    )
    forbidden_v22 = sorted(
        {
            str(path.relative_to(repo_root)).replace("\\", "/")
            for pattern in forbidden_v22_globs
            for path in repo_root.glob(pattern)
            if path.is_file()
        }
    )
    checks["v22_artifacts"] = forbidden_v22
    if forbidden_v22:
        errors.append(
            _finding(
                "v22_artifact_present",
                "V22+ catalog artifacts are forbidden without explicit approval: " + ", ".join(forbidden_v22),
                str(repo_root),
            )
        )

    research_path = repo_root / "docs" / "NAVIGATION_COVERAGE_GAPS_V21_RESEARCH.md"
    if not research_path.is_file():
        errors.append(_finding("v21_research_missing", "V21 research-only document is missing", str(research_path)))
    else:
        research_head = research_path.read_text(encoding="utf-8", errors="replace")[:2000].casefold()
        if "research-only" not in research_head or "noncanonical" not in research_head:
            errors.append(
                _finding(
                    "v21_not_research_only",
                    "V21 document must explicitly remain research-only and noncanonical",
                    str(research_path),
                )
            )

    forbidden_v21_globs = (
        "scripts/navigation_catalog_v21_data.py",
        "apps/api/tests/navigation_catalog_v21*",
        "fixtures/navigation/**/*v21*",
    )
    implemented_v21 = sorted(
        {
            str(path.relative_to(repo_root)).replace("\\", "/")
            for pattern in forbidden_v21_globs
            for path in repo_root.glob(pattern)
            if path.is_file()
        }
    )
    checks["v21_implementation_artifacts"] = implemented_v21
    if implemented_v21:
        errors.append(
            _finding(
                "v21_implementation_present",
                "V21 must remain research-only; implementation artifacts found: " + ", ".join(implemented_v21),
                str(repo_root),
            )
        )


def _validate_manifest(
    manifest_path: Path, errors: list[dict[str, str]], checks: dict[str, Any]
) -> Mapping[str, Any]:
    if not manifest_path.is_file():
        errors.append(_finding("manifest_missing", "manifest.json is required", str(manifest_path)))
        return {}
    try:
        manifest = _load_json(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        errors.append(_finding("manifest_parse_error", str(error), str(manifest_path)))
        return {}
    if not isinstance(manifest, Mapping):
        errors.append(_finding("manifest_shape", "manifest must be a JSON object", str(manifest_path)))
        return {}

    provenance = _nested(manifest, "provenance", "dataset.provenance", "governance.provenance")
    route_lifecycle = _nested(
        manifest,
        "route_lifecycle",
        "route_lifecycle_status",
        "governance.route_lifecycle",
        "graph_candidate.route_lifecycle",
    )
    checks["manifest_provenance"] = provenance
    checks["manifest_route_lifecycle"] = route_lifecycle
    if provenance != "emulator_observation":
        errors.append(
            _finding(
                "invalid_provenance",
                f"manifest provenance must be 'emulator_observation', got {provenance!r}",
                str(manifest_path),
            )
        )
    if route_lifecycle != "shadow":
        errors.append(
            _finding(
                "route_not_shadow",
                f"emulator candidate routes must remain shadow, got {route_lifecycle!r}",
                str(manifest_path),
            )
        )

    catalog = _nested(manifest, "canonical_catalog", "governance.canonical_catalog")
    if not isinstance(catalog, Mapping):
        errors.append(
            _finding("manifest_canonical_missing", "manifest canonical_catalog object is required", str(manifest_path))
        )
    else:
        expected_catalog = {
            "version": EXPECTED_CATALOG_VERSION,
            "sha256": EXPECTED_CATALOG_SHA256,
            "equivalence_sha256": EXPECTED_EQUIVALENCE_SHA256,
            "domain_count": EXPECTED_DOMAIN_COUNT,
            "function_count": EXPECTED_FUNCTION_COUNT,
            "terminal_function_count": EXPECTED_TERMINAL_FUNCTION_COUNT,
            "intent_count": EXPECTED_INTENT_COUNT,
        }
        for key, expected in expected_catalog.items():
            actual = catalog.get(key)
            if actual != expected:
                errors.append(
                    _finding(
                        "manifest_canonical_mismatch",
                        f"canonical_catalog.{key} must be {expected!r}, got {actual!r}",
                        str(manifest_path),
                    )
                )

    mutation = _nested(
        manifest,
        "canonical_catalog_mutation",
        "canonical_mutation_allowed",
        "governance.canonical_catalog_mutation",
    )
    if mutation not in {False, 0, "false"}:
        errors.append(
            _finding(
                "canonical_mutation_enabled",
                "emulator observations may not mutate or promote the canonical catalog",
                str(manifest_path),
            )
        )

    proposed = _nested(manifest, "proposed_catalog_version", "governance.proposed_catalog_version")
    if proposed is not None:
        match = re.search(r"\d+", str(proposed))
        if match and int(match.group()) >= 21:
            errors.append(
                _finding(
                    "forbidden_catalog_proposal",
                    f"run manifest may not implement/promote V21 or V22+: {proposed!r}",
                    str(manifest_path),
                )
            )

    return manifest


def _run_profile(run_dir: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve completion gates without treating a capture checkpoint as a graph run."""

    collector_manifest: Mapping[str, Any] = {}
    collector_manifest_path = run_dir / "collector-manifest.json"
    if collector_manifest_path.is_file():
        try:
            loaded = _load_json(collector_manifest_path)
            if isinstance(loaded, Mapping):
                collector_manifest = loaded
        except (OSError, UnicodeError, json.JSONDecodeError):
            # The regular JSON validation reports malformed files.  Profile
            # resolution remains conservative if this optional file is bad.
            collector_manifest = {}

    checkpoint: Mapping[str, Any] = {}
    checkpoint_path = run_dir / "checkpoint.json"
    if checkpoint_path.is_file():
        try:
            loaded = _load_json(checkpoint_path)
            if isinstance(loaded, Mapping):
                checkpoint = loaded
        except (OSError, UnicodeError, json.JSONDecodeError):
            checkpoint = {}

    explicit_mode = _nested(manifest, "run_mode", "mode", "collection.run_mode")
    capture_only = bool(
        _nested(manifest, "capture_only", "collection.capture_only") is True
        or collector_manifest.get("capture_only") is True
        or str(explicit_mode or "").casefold() == "capture_only"
    )
    mode = "capture_only" if capture_only else str(explicit_mode or "completed_exploration").casefold()

    status = _nested(manifest, "status", "run_status", "collection.status")
    checkpoint_state = checkpoint.get("state", {}) if isinstance(checkpoint, Mapping) else {}
    if status is None and isinstance(checkpoint_state, Mapping):
        status = checkpoint_state.get("task_status") or checkpoint_state.get("status")
    status = str(status or ("captured" if capture_only else "completed")).casefold()
    in_progress = status in {
        "created",
        "pending",
        "running",
        "in_progress",
        "capturing",
        "exploring",
        "paused",
        "resumable",
    }
    completed_exploration = not capture_only and not in_progress and mode in {
        "completed_exploration",
        "exploration",
        "graph_exploration",
    }
    screenshot_policy = str(
        _nested(manifest, "screenshot_policy", "collection.screenshot_policy")
        or collector_manifest.get("screenshot_policy")
        or "required"
    ).casefold()
    planned_app_packages = sorted(
        {
            str(task.get("app_package", "")).strip()
            for task in collector_manifest.get("tasks", [])
            if isinstance(task, Mapping) and str(task.get("app_package", "")).strip()
        }
    )
    planned_task_ids = sorted(
        {
            str(task.get("task_id", "")).strip()
            for task in collector_manifest.get("tasks", [])
            if isinstance(task, Mapping) and str(task.get("task_id", "")).strip()
        }
    )
    return {
        "run_mode": mode,
        "status": status,
        "capture_only": capture_only,
        "in_progress": in_progress,
        "completed_exploration": completed_exploration,
        "require_completed_graph": completed_exploration,
        "screenshot_policy": screenshot_policy,
        "planned_app_packages": planned_app_packages,
        "planned_task_ids": planned_task_ids,
    }


def _validate_schema(
    connection: sqlite3.Connection, errors: list[dict[str, str]], checks: dict[str, Any], db_path: Path
) -> dict[str, set[str]]:
    tables = _sqlite_tables(connection)
    missing_tables = sorted(REQUIRED_TABLES - tables)
    checks["corpus_tables"] = sorted(tables)
    if missing_tables:
        errors.append(
            _finding(
                "missing_tables",
                "required corpus tables missing: " + ", ".join(missing_tables),
                str(db_path),
            )
        )

    columns_by_table: dict[str, set[str]] = {}
    for table in sorted(REQUIRED_TABLES & tables):
        columns = _columns(connection, table)
        columns_by_table[table] = columns
        missing_groups = ["/".join(group) for group in REQUIRED_COLUMN_GROUPS[table] if not any(name in columns for name in group)]
        if missing_groups:
            errors.append(
                _finding(
                    "missing_columns",
                    f"{table} missing required semantic columns: " + ", ".join(missing_groups),
                    str(db_path),
                )
            )
    return columns_by_table


def _validate_references(
    connection: sqlite3.Connection,
    columns: Mapping[str, set[str]],
    profile: Mapping[str, Any],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
    db_path: Path,
) -> None:
    if not REQUIRED_TABLES.issubset(columns):
        return

    foreign_key_errors = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
    checks["sqlite_foreign_key_errors"] = len(foreign_key_errors)
    if foreign_key_errors:
        errors.append(
            _finding(
                "foreign_key_violation",
                f"SQLite foreign_key_check returned {len(foreign_key_errors)} violation(s)",
                str(db_path),
            )
        )

    reference_queries = (
        (
            "screen_run_reference",
            "SELECT COUNT(*) FROM screens s LEFT JOIN runs r ON r.run_id=s.run_id "
            "WHERE s.run_id IS NULL OR TRIM(s.run_id)='' OR r.run_id IS NULL",
        ),
        (
            "element_screen_reference",
            "SELECT COUNT(*) FROM elements e LEFT JOIN screens s ON s.screen_id=e.screen_id "
            "WHERE e.screen_id IS NULL OR TRIM(e.screen_id)='' OR s.screen_id IS NULL",
        ),
        (
            "transition_run_reference",
            "SELECT COUNT(*) FROM transitions t LEFT JOIN runs r ON r.run_id=t.run_id "
            "WHERE t.run_id IS NULL OR TRIM(t.run_id)='' OR r.run_id IS NULL",
        ),
        (
            "transition_source_reference",
            "SELECT COUNT(*) FROM transitions t LEFT JOIN screens s ON s.screen_id=t.source_screen_id "
            "WHERE t.source_screen_id IS NULL OR TRIM(t.source_screen_id)='' OR s.screen_id IS NULL",
        ),
        (
            "transition_target_reference",
            "SELECT COUNT(*) FROM transitions t LEFT JOIN screens s ON s.screen_id=t.target_screen_id "
            "WHERE t.target_screen_id IS NOT NULL AND TRIM(t.target_screen_id)<>'' AND s.screen_id IS NULL",
        ),
        (
            "transition_element_reference",
            "SELECT COUNT(*) FROM transitions t LEFT JOIN elements e ON e.element_id=t.element_id "
            "WHERE t.element_id IS NOT NULL AND TRIM(t.element_id)<>'' AND e.element_id IS NULL",
        ),
        (
            "transition_element_ownership",
            "SELECT COUNT(*) FROM transitions t JOIN elements e ON e.element_id=t.element_id "
            "WHERE t.element_id IS NOT NULL AND TRIM(t.element_id)<>'' AND e.screen_id<>t.source_screen_id",
        ),
        (
            "screen_app_reference",
            "SELECT COUNT(*) FROM screens s LEFT JOIN apps a ON a.app_package=s.app_package "
            "WHERE s.app_package IS NULL OR TRIM(s.app_package)='' OR a.app_package IS NULL",
        ),
        (
            "goal_run_reference",
            "SELECT COUNT(*) FROM goals g LEFT JOIN runs r ON r.run_id=g.run_id "
            "WHERE g.run_id IS NULL OR TRIM(g.run_id)='' OR r.run_id IS NULL",
        ),
        (
            "goal_screen_reference",
            "SELECT COUNT(*) FROM goals g LEFT JOIN screens s ON s.screen_id=g.terminal_candidate_screen_id "
            "WHERE g.terminal_candidate_screen_id IS NOT NULL AND TRIM(g.terminal_candidate_screen_id)<>'' "
            "AND s.screen_id IS NULL",
        ),
        (
            "goal_element_reference",
            "SELECT COUNT(*) FROM goals g LEFT JOIN elements e ON e.element_id=g.terminal_candidate_element_id "
            "WHERE g.terminal_candidate_element_id IS NOT NULL AND TRIM(g.terminal_candidate_element_id)<>'' "
            "AND e.element_id IS NULL",
        ),
        (
            "goal_terminal_ownership",
            "SELECT COUNT(*) FROM goals g JOIN elements e ON e.element_id=g.terminal_candidate_element_id "
            "WHERE g.terminal_candidate_screen_id IS NOT NULL "
            "AND TRIM(g.terminal_candidate_screen_id)<>'' "
            "AND e.screen_id<>g.terminal_candidate_screen_id",
        ),
        (
            "failure_run_reference",
            "SELECT COUNT(*) FROM failures f LEFT JOIN runs r ON r.run_id=f.run_id "
            "WHERE f.run_id IS NULL OR TRIM(f.run_id)='' OR r.run_id IS NULL",
        ),
        (
            "failure_screen_reference",
            "SELECT COUNT(*) FROM failures f LEFT JOIN screens s ON s.screen_id=f.screen_id "
            "WHERE f.screen_id IS NOT NULL AND TRIM(f.screen_id)<>'' AND s.screen_id IS NULL",
        ),
        (
            "metric_run_reference",
            "SELECT COUNT(*) FROM metrics m LEFT JOIN runs r ON r.run_id=m.run_id "
            "WHERE m.run_id IS NULL OR TRIM(m.run_id)='' OR r.run_id IS NULL",
        ),
        (
            "metric_app_reference",
            "SELECT COUNT(*) FROM metrics m LEFT JOIN apps a ON a.app_package=m.app_package "
            "WHERE m.app_package IS NOT NULL AND TRIM(m.app_package)<>'' AND a.app_package IS NULL",
        ),
        (
            "annotation_run_reference",
            "SELECT COUNT(*) FROM annotations a LEFT JOIN runs r ON r.run_id=a.run_id "
            "WHERE a.run_id IS NULL OR TRIM(a.run_id)='' OR r.run_id IS NULL",
        ),
    )
    for code, query in reference_queries:
        count = int(_scalar(connection, query) or 0)
        checks[code] = count
        if count:
            errors.append(
                _finding("referential_integrity", f"{code} has {count} invalid row(s)", str(db_path))
            )

    observed_packages = {
        str(row[0]).strip()
        for row in connection.execute("SELECT app_package FROM apps WHERE app_package IS NOT NULL")
        if str(row[0]).strip()
    }
    allowed_packages = set(observed_packages)
    if profile.get("capture_only") or profile.get("in_progress"):
        allowed_packages.update(str(item) for item in profile.get("planned_app_packages", []))
    for table in ("goals", "failures"):
        invalid_packages: list[str] = []
        planned_task_ids = set(str(item) for item in profile.get("planned_task_ids", []))
        payload_expression = "payload_json" if "payload_json" in columns[table] else "NULL"
        for package, payload_json in connection.execute(
            f'SELECT app_package, {payload_expression} FROM "{table}"'
        ):
            package = str(package or "").strip()
            if package in allowed_packages:
                continue
            linked_capture_failure = False
            if table == "failures" and (profile.get("capture_only") or profile.get("in_progress")):
                try:
                    payload = json.loads(str(payload_json or "{}"))
                except json.JSONDecodeError:
                    payload = {}
                linked_capture_failure = (
                    isinstance(payload, Mapping)
                    and str(payload.get("task_id", "")) in planned_task_ids
                    and str(payload.get("failure_source", "")) == "collector"
                )
            if not linked_capture_failure:
                invalid_packages.append(package)
        checks[f"{table[:-1]}_app_reference"] = len(invalid_packages)
        if invalid_packages:
            errors.append(
                _finding(
                    "referential_integrity",
                    f"{table[:-1]}_app_reference has {len(invalid_packages)} invalid row(s)",
                    str(db_path),
                )
            )

    for table, identifier in (
        ("apps", "app_package"),
        ("runs", "run_id"),
        ("screens", "screen_id"),
        ("elements", "element_id"),
        ("transitions", "transition_id"),
        ("goals", "goal_id"),
        ("failures", "failure_id"),
        ("metrics", "metric_id"),
        ("annotations", "annotation_id"),
    ):
        empty_count = int(
            _scalar(
                connection,
                f'SELECT COUNT(*) FROM "{table}" WHERE "{identifier}" IS NULL OR TRIM(CAST("{identifier}" AS TEXT))=""',
            )
            or 0
        )
        duplicate_count = int(
            _scalar(
                connection,
                f'SELECT COUNT(*) FROM (SELECT "{identifier}" FROM "{table}" GROUP BY "{identifier}" HAVING COUNT(*)>1)',
            )
            or 0
        )
        if empty_count or duplicate_count:
            errors.append(
                _finding(
                    "invalid_identifier",
                    f"{table}.{identifier}: empty={empty_count}, duplicate_groups={duplicate_count}",
                    str(db_path),
                )
            )

    row_counts = {
        table: int(_scalar(connection, f'SELECT COUNT(*) FROM "{table}"') or 0)
        for table in sorted(REQUIRED_TABLES)
    }
    checks["corpus_row_counts"] = row_counts
    required_nonempty = ["apps", "runs", "screens", "elements", "goals", "metrics"]
    if profile.get("require_completed_graph"):
        required_nonempty.append("transitions")
    for table in required_nonempty:
        if row_counts[table] == 0:
            errors.append(
                _finding(
                    "required_corpus_empty",
                    f"completed corpus requires at least one {table} row",
                    str(db_path),
                )
            )


def _validate_run_governance_rows(
    connection: sqlite3.Connection,
    columns: Mapping[str, set[str]],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
    db_path: Path,
) -> None:
    if "runs" not in columns:
        return
    provenance_values = {
        str(row[0]) for row in connection.execute("SELECT DISTINCT provenance FROM runs")
    }
    lifecycle_column = _pick(columns["runs"], "route_lifecycle", "route_status")
    lifecycle_values = (
        {str(row[0]) for row in connection.execute(f'SELECT DISTINCT "{lifecycle_column}" FROM runs')}
        if lifecycle_column
        else set()
    )
    checks["run_provenance_values"] = sorted(provenance_values)
    checks["run_route_lifecycle_values"] = sorted(lifecycle_values)
    if provenance_values != {"emulator_observation"}:
        errors.append(
            _finding(
                "invalid_provenance",
                f"all run rows must use emulator_observation provenance, got {sorted(provenance_values)}",
                str(db_path),
            )
        )
    if lifecycle_values != {"shadow"}:
        errors.append(
            _finding(
                "route_not_shadow",
                f"all run rows must use shadow route lifecycle, got {sorted(lifecycle_values)}",
                str(db_path),
            )
        )

    governed_columns = {
        "provenance": "emulator_observation",
        "route_lifecycle": "shadow",
        "canonical_catalog_version": EXPECTED_CATALOG_VERSION,
        "canonical_catalog_sha256": EXPECTED_CATALOG_SHA256,
        "canonical_equivalence_sha256": EXPECTED_EQUIVALENCE_SHA256,
    }
    for table, table_columns in sorted(columns.items()):
        for column, expected in governed_columns.items():
            if column not in table_columns:
                continue
            values = {
                str(row[0])
                for row in connection.execute(f'SELECT DISTINCT "{column}" FROM "{table}"')
            }
            checks[f"{table}_{column}_values"] = sorted(values)
            if values and values != {expected}:
                errors.append(
                    _finding(
                        "record_governance_mismatch",
                        f"{table}.{column} must contain only {expected!r}, got {sorted(values)}",
                        str(db_path),
                    )
                )


def _validate_evidence_paths(
    connection: sqlite3.Connection,
    columns: Mapping[str, set[str]],
    run_dir: Path,
    profile: Mapping[str, Any],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
) -> None:
    if "screens" not in columns:
        return
    screen_columns = columns["screens"]
    privacy_column = _pick(screen_columns, "privacy_status", "screenshot_privacy_status")
    redacted_column = _pick(screen_columns, "screenshot_redacted", "is_screenshot_redacted")
    evidence_mode_column = _pick(screen_columns, "evidence_mode")
    privacy_verified_column = _pick(screen_columns, "privacy_verified")
    select_columns = ["screen_id", "screenshot_path", "accessibility_tree_path", "contains_personal_data"]
    select_columns = [
        _pick(screen_columns, column, "ui_tree_path" if column == "accessibility_tree_path" else column)
        for column in select_columns
    ]
    if any(column is None for column in select_columns):
        return
    extra_columns = [
        column
        for column in (
            privacy_column,
            redacted_column,
            evidence_mode_column,
            privacy_verified_column,
        )
        if column
    ]
    query_columns = [*select_columns, *extra_columns]
    rows = connection.execute(
        "SELECT " + ", ".join(f'"{column}"' for column in query_columns) + " FROM screens"
    ).fetchall()
    missing = 0
    escaped = 0
    privacy_failures = 0
    run_resolved = run_dir.resolve()
    for row in rows:
        values = dict(zip(query_columns, row))
        screen_id = str(values[select_columns[0]])
        evidence_mode = str(values.get(evidence_mode_column, "")).strip().casefold()
        for index, column in enumerate(select_columns[1:3]):
            raw_path = str(values[column] or "").strip()
            if not raw_path:
                is_screenshot = index == 0
                permitted_absence = (
                    bool(profile.get("in_progress"))
                    or evidence_mode in {"metadata_only", "omitted"}
                    or (
                        is_screenshot
                        and (
                            bool(profile.get("capture_only"))
                            or str(profile.get("screenshot_policy")) in {"none", "metadata_only", "disabled"}
                            or evidence_mode == "verified_metadata"
                        )
                    )
                )
                if permitted_absence:
                    continue
                missing += 1
                errors.append(
                    _finding("missing_evidence", f"screen {screen_id} has empty {column}", str(run_dir))
                )
                continue
            candidate = Path(raw_path)
            resolved = candidate.resolve() if candidate.is_absolute() else (run_dir / candidate).resolve()
            try:
                resolved.relative_to(run_resolved)
            except ValueError:
                escaped += 1
                errors.append(
                    _finding(
                        "evidence_path_escape",
                        f"screen {screen_id} {column} escapes the run directory: {raw_path}",
                        str(run_dir),
                    )
                )
                continue
            if not resolved.is_file():
                missing += 1
                errors.append(
                    _finding(
                        "missing_evidence",
                        f"screen {screen_id} references missing {column}: {raw_path}",
                        str(run_dir),
                    )
                )

        has_personal = _is_truthy(values[select_columns[3]])
        if has_personal:
            privacy_value = str(values.get(privacy_column, "")).casefold() if privacy_column else ""
            redacted_value = _is_truthy(values.get(redacted_column)) if redacted_column else False
            privacy_verified = (
                _is_truthy(values.get(privacy_verified_column)) if privacy_verified_column else False
            )
            screenshot_path = str(values[select_columns[1]] or "").casefold()
            if screenshot_path and not (
                redacted_value
                or privacy_value in {"redacted", "masked"}
                or "redacted" in screenshot_path
                or "masked" in screenshot_path
                or (
                    str(profile.get("screenshot_policy")) == "redacted"
                    and privacy_verified
                    and evidence_mode == "verified_evidence"
                )
            ):
                privacy_failures += 1
                errors.append(
                    _finding(
                        "personal_screenshot_unprotected",
                        f"screen {screen_id} contains personal data without redaction/omission evidence",
                        str(run_dir),
                    )
                )
    checks["evidence_missing_count"] = missing
    checks["evidence_path_escape_count"] = escaped
    checks["personal_screenshot_unprotected_count"] = privacy_failures


def _validate_safety(
    connection: sqlite3.Connection,
    columns: Mapping[str, set[str]],
    manifest: Mapping[str, Any],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
    db_path: Path,
) -> None:
    transition_unsafe = transition_final = element_final = 0
    if "transitions" in columns:
        unsafe_column = _pick(columns["transitions"], "unsafe_action", "unsafe_click")
        final_column = _pick(columns["transitions"], "is_final_action", "final_action")
        if unsafe_column:
            transition_unsafe = int(
                _scalar(
                    connection,
                    f'SELECT COUNT(*) FROM transitions WHERE auto_executed=1 AND "{unsafe_column}"=1',
                )
                or 0
            )
        if final_column:
            transition_final = int(
                _scalar(
                    connection,
                    f'SELECT COUNT(*) FROM transitions WHERE auto_executed=1 AND "{final_column}"=1',
                )
                or 0
            )
    if "transitions" in columns and "elements" in columns:
        element_final_column = _pick(columns["elements"], "is_final_action", "final_action")
        if element_final_column:
            element_final = int(
                _scalar(
                    connection,
                    f'SELECT COUNT(*) FROM transitions t JOIN elements e ON e.element_id=t.element_id '
                    f'WHERE t.auto_executed=1 AND e."{element_final_column}"=1',
                )
                or 0
            )
        if "risk_level" in columns["elements"]:
            risky_auto = int(
                _scalar(
                    connection,
                    "SELECT COUNT(*) FROM transitions t JOIN elements e ON e.element_id=t.element_id "
                    "WHERE t.auto_executed=1 AND LOWER(e.risk_level) IN ('high','critical','unsafe')",
                )
                or 0
            )
            transition_unsafe += risky_auto

    checks["unsafe_auto_transition_count"] = transition_unsafe
    checks["final_action_auto_transition_count"] = transition_final + element_final
    if transition_unsafe:
        errors.append(
            _finding(
                "unsafe_auto_click",
                f"unsafe/high-risk automatic actions found: {transition_unsafe}",
                str(db_path),
            )
        )
    if transition_final or element_final:
        errors.append(
            _finding(
                "final_action_auto_click",
                f"automatic final-action transitions found: transition={transition_final}, element={element_final}",
                str(db_path),
            )
        )

    for semantic, paths in {
        "unsafe_auto_click_count": (
            "safety.unsafe_auto_click_count",
            "metrics.unsafe_auto_click_count",
            "unsafe_auto_click_count",
        ),
        "final_action_auto_click_count": (
            "safety.final_action_auto_click_count",
            "metrics.final_action_auto_click_count",
            "final_action_auto_click_count",
        ),
    }.items():
        value = _nested(manifest, *paths)
        if value is None:
            errors.append(
                _finding(
                    "manifest_safety_metric_missing",
                    f"manifest must state {semantic}=0",
                    str(db_path.parent / "manifest.json"),
                )
            )
        else:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = -1.0
            if numeric != 0:
                errors.append(
                    _finding(
                        "manifest_safety_metric_nonzero",
                        f"manifest {semantic} must be 0, got {value!r}",
                        str(db_path.parent / "manifest.json"),
                    )
                )


def _normalize_metric_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _validate_metrics(
    connection: sqlite3.Connection,
    columns: Mapping[str, set[str]],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
    db_path: Path,
) -> None:
    metric_columns = columns.get("metrics", set())
    if not metric_columns:
        return
    missing: list[str] = []
    metric_name_column = _pick(metric_columns, "metric_name", "name", "metric_key")
    metric_dimension_column = _pick(metric_columns, "metric_dimension", "dimension", "stage")
    if metric_name_column:
        observed = {
            _normalize_metric_name(row[0])
            for row in connection.execute(
                f'SELECT DISTINCT "{metric_name_column}" FROM metrics WHERE "{metric_name_column}" IS NOT NULL'
            )
        }
        for semantic, aliases in REQUIRED_LONG_METRIC_ALIASES.items():
            if not (observed & aliases):
                missing.append(semantic)
    else:
        for semantic, aliases in REQUIRED_WIDE_METRIC_GROUPS.items():
            if not any(alias in metric_columns for alias in aliases):
                missing.append(semantic)

    dimensions: set[str] = set()
    if metric_name_column and metric_dimension_column:
        dimensions = {
            str(row[0]).strip().casefold()
            for row in connection.execute(
                f'SELECT DISTINCT "{metric_dimension_column}" FROM metrics '
                f'WHERE "{metric_dimension_column}" IS NOT NULL'
            )
        }
        expected_dimensions = {"perception", "semantics", "policy"}
        absent_dimensions = sorted(expected_dimensions - dimensions)
        if absent_dimensions:
            errors.append(
                _finding(
                    "missing_metric_dimensions",
                    "metrics must separately cover perception, semantics, and policy; missing: "
                    + ", ".join(absent_dimensions),
                    str(db_path),
                )
            )
    else:
        # In wide form, separately named perception, semantics and policy
        # columns establish the three dimensions even if ``metric_dimension``
        # labels the row's primary stage (for example, ``policy``).
        dimensions = {"perception", "semantics", "policy"}
        if metric_dimension_column:
            supplied = {
                str(row[0]).strip().casefold()
                for row in connection.execute(
                    f'SELECT DISTINCT "{metric_dimension_column}" FROM metrics '
                    f'WHERE "{metric_dimension_column}" IS NOT NULL'
                )
            }
            # ``run_summary`` is an aggregate row over the three explicitly
            # named wide metric families, not a fourth evaluation dimension.
            unexpected = sorted(supplied - {"perception", "semantics", "policy", "run_summary"})
            if unexpected:
                errors.append(
                    _finding(
                        "invalid_metric_dimension",
                        "unsupported metric dimension labels: " + ", ".join(unexpected),
                        str(db_path),
                    )
                )

    checks["metric_dimensions"] = sorted(dimensions)
    checks["missing_metric_fields"] = sorted(missing)
    if missing:
        errors.append(
            _finding(
                "missing_metric_fields",
                "required evaluation metrics missing: " + ", ".join(sorted(missing)),
                str(db_path),
            )
        )

    for semantic, aliases in (
        ("unsafe_auto_click_count", REQUIRED_WIDE_METRIC_GROUPS["unsafe_auto_click_count"]),
        ("final_action_auto_click_count", REQUIRED_WIDE_METRIC_GROUPS["final_action_auto_click_count"]),
    ):
        count_value = 0.0
        if metric_name_column:
            value_column = _pick(metric_columns, "metric_value", "value", "numeric_value")
            if value_column:
                normalized_aliases = REQUIRED_LONG_METRIC_ALIASES[semantic]
                for name, value in connection.execute(
                    f'SELECT "{metric_name_column}", "{value_column}" FROM metrics'
                ):
                    if _normalize_metric_name(name) in normalized_aliases:
                        try:
                            count_value += float(value or 0)
                        except (TypeError, ValueError):
                            count_value += 1
        else:
            column = _pick(metric_columns, *aliases)
            if column:
                count_value = float(_scalar(connection, f'SELECT COALESCE(SUM("{column}"),0) FROM metrics') or 0)
        checks[f"metrics_{semantic}"] = count_value
        if count_value != 0:
            errors.append(
                _finding(
                    semantic,
                    f"aggregate {semantic} must be 0, got {count_value:g}",
                    str(db_path),
                )
            )


def _validate_graph_candidate(
    graph_path: Path,
    profile: Mapping[str, Any],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
) -> None:
    if not graph_path.is_file():
        checks["graph_candidate_present"] = False
        if profile.get("require_completed_graph"):
            errors.append(
                _finding("graph_candidate_missing", "graph-candidate.sqlite is required", str(graph_path))
            )
        return
    checks["graph_candidate_present"] = True
    try:
        connection = sqlite3.connect(f"file:{graph_path.as_posix()}?mode=ro", uri=True)
        try:
            tables = _sqlite_tables(connection)
            if "universal_routes" in tables:
                columns = _columns(connection, "universal_routes")
                route_count = int(_scalar(connection, "SELECT COUNT(*) FROM universal_routes") or 0)
                checks["graph_route_count"] = route_count
                if profile.get("require_completed_graph") and route_count == 0:
                    errors.append(
                        _finding(
                            "graph_routes_empty",
                            "completed exploration requires at least one shadow route",
                            str(graph_path),
                        )
                    )
                status_column = _pick(columns, "status", "lifecycle_status", "route_lifecycle")
                if not status_column:
                    errors.append(
                        _finding("graph_route_status_missing", "universal_routes lacks lifecycle/status", str(graph_path))
                    )
                    return
                non_shadow = int(
                    _scalar(
                        connection,
                        f'SELECT COUNT(*) FROM universal_routes WHERE "{status_column}"<>\'shadow\' '
                        f'OR "{status_column}" IS NULL',
                    )
                    or 0
                )
                if "provisional" in columns:
                    non_shadow += int(
                        _scalar(connection, "SELECT COUNT(*) FROM universal_routes WHERE provisional<>1") or 0
                    )
                checks["graph_non_shadow_routes"] = non_shadow
                if non_shadow:
                    errors.append(
                        _finding(
                            "route_not_shadow",
                            f"graph candidate contains {non_shadow} non-shadow/non-provisional route row(s)",
                            str(graph_path),
                        )
                    )
            elif "routes" in tables:
                columns = _columns(connection, "routes")
                route_count = int(_scalar(connection, "SELECT COUNT(*) FROM routes") or 0)
                checks["graph_route_count"] = route_count
                if profile.get("require_completed_graph") and route_count == 0:
                    errors.append(
                        _finding(
                            "graph_routes_empty",
                            "completed exploration requires at least one shadow route",
                            str(graph_path),
                        )
                    )
                status_column = _pick(columns, "status", "lifecycle_status", "route_lifecycle")
                if not status_column:
                    errors.append(_finding("graph_route_status_missing", "routes lacks lifecycle/status", str(graph_path)))
                else:
                    non_shadow = int(
                        _scalar(
                            connection,
                            f'SELECT COUNT(*) FROM routes WHERE "{status_column}"<>\'shadow\' OR "{status_column}" IS NULL',
                        )
                        or 0
                    )
                    checks["graph_non_shadow_routes"] = non_shadow
                    if non_shadow:
                        errors.append(
                            _finding(
                                "route_not_shadow",
                                f"graph candidate contains {non_shadow} non-shadow route row(s)",
                                str(graph_path),
                            )
                        )
            else:
                errors.append(
                    _finding(
                        "graph_routes_missing",
                        "graph candidate must contain universal_routes or routes table",
                        str(graph_path),
                    )
                )
        finally:
            connection.close()
    except sqlite3.Error as error:
        errors.append(_finding("graph_sqlite_error", str(error), str(graph_path)))


def _luhn_valid(value: str) -> bool:
    digits = [int(character) for character in re.sub(r"\D", "", value)]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _sensitive_matches(text: str) -> list[str]:
    matches: set[str] = set()
    if EMAIL_PATTERN.search(text):
        matches.add("email")
    if PHONE_PATTERN.search(text):
        matches.add("phone")
    if KOREAN_RESIDENT_ID_PATTERN.search(text):
        matches.add("korean_resident_id")
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            matches.add(label)
    card_pattern = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
    if any(_luhn_valid(match.group()) for match in card_pattern.finditer(text)):
        matches.add("payment_card")
    return sorted(matches)


HUMAN_CONTENT_FIELDS = frozenset(
    {
        "text",
        "texts",
        "label",
        "labels",
        "content_description",
        "content_descriptions",
        "visible_text",
        "visible_texts",
        "title",
        "title_text",
        "window_title",
        "hint",
        "hint_text",
        "user_goal",
        "goal_text",
        "error",
        "error_text",
        "error_message",
        "error_content",
        "evidence",
        "evidence_json",
        "failure_reason",
        "cause",
        "selected_candidate",
        "selected_candidates",
        "correct_candidate",
        "correct_candidates",
        "required_synonym_or_label",
        "missing_synonym_or_rule",
        "policy_change",
        "policy_correction",
        "retest_result",
        "retry_result",
        "expected_outcome",
        "expected_result",
        "icon_inference",
        "inferred_icon_semantics",
        "synonym",
        "synonyms",
        "description",
        "subtitle",
        "summary",
        "tooltip",
        "accessibility_label",
        "ocr_text",
        "reason",
        "rationale",
        "message",
        "app_name",
    }
)
STRUCTURAL_FIELD_PARTS = frozenset(
    {
        "id",
        "hash",
        "sha",
        "fingerprint",
        "signature",
        "coordinate",
        "coordinates",
        "bounds",
        "version",
        "count",
        "sequence",
        "timestamp",
        "recorded_at",
        "collected_at",
        "created_at",
        "updated_at",
        "path",
        "url",
        "package",
        "resource",
        "index",
        "confidence",
        "rate",
        "duration",
        "distance",
        "value",
    }
)
JSON_CONTAINER_COLUMNS = frozenset(
    {
        "payload_json",
        "envelope_json",
        "evidence_json",
        "annotation_json",
        "value_json",
        "visible_texts_json",
        "content_descriptions_json",
        "synonyms_json",
        "inferred_icon_semantics_json",
    }
)


def _normalized_field_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().casefold()).strip("_")


def _is_structural_field(field_name: Any) -> bool:
    normalized = _normalized_field_name(field_name)
    parts = set(normalized.split("_"))
    return bool(parts & STRUCTURAL_FIELD_PARTS) or normalized.endswith("_id")


def _is_human_content_field(field_name: Any) -> bool:
    normalized = _normalized_field_name(field_name)
    if _is_structural_field(normalized):
        return False
    return (
        normalized in HUMAN_CONTENT_FIELDS
        or normalized.endswith("_text")
        or normalized.endswith("_label")
        or normalized.endswith("_hint")
        or normalized.endswith("_error")
        or normalized.endswith("_message")
        or normalized.endswith("_reason")
        or normalized.endswith("_description")
    )


def _looks_like_structural_identifier(value: str) -> bool:
    stripped = value.strip()
    return bool(
        re.fullmatch(r"[0-9a-fA-F]{20,}", stripped)
        or re.fullmatch(
            r"(?:task|obs|screen|element|transition|metric|goal|app|route|session|local|run)_[A-Za-z0-9_.:-]+",
            stripped,
            re.IGNORECASE,
        )
        or ":id/" in stripped
    )


def _iter_human_content(
    value: Any,
    *,
    location: str,
    human_container: bool = False,
) -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_location = f"{location}.{key}" if location else str(key)
            if _is_structural_field(key):
                continue
            child_human = _is_human_content_field(key)
            # A human-content container (notably evidence) may contain nested
            # rationale/source text, but structural keys inside it remain
            # excluded above.
            yield from _iter_human_content(
                child,
                location=child_location,
                human_container=human_container or child_human,
            )
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _iter_human_content(
                child,
                location=f"{location}[{index}]",
                human_container=human_container,
            )
        return
    if human_container and isinstance(value, (str, int)):
        text = str(value)
        if text and not _looks_like_structural_identifier(text):
            yield location, text


def _iter_json_human_content(path: Path) -> Iterable[tuple[str, str]]:
    if path.suffix.casefold() == ".jsonl":
        with path.open("r", encoding="utf-8", errors="replace") as source:
            for line_number, raw_line in enumerate(source, 1):
                if not raw_line.strip():
                    continue
                try:
                    payload = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                yield from _iter_human_content(payload, location=f"line[{line_number}]")
        return
    try:
        payload = _load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return
    yield from _iter_human_content(payload, location="json")


def _iter_xml_human_content(path: Path) -> Iterable[tuple[str, str]]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return
    for index, element in enumerate(root.iter()):
        if element.text and element.text.strip():
            yield f"xml[{index}].text", element.text
        for key, value in element.attrib.items():
            if _is_human_content_field(key) and value:
                yield f"xml[{index}].{key}", value


def _iter_delimited_human_content(path: Path) -> Iterable[tuple[str, str]]:
    delimiter = "\t" if path.suffix.casefold() == ".tsv" else ","
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as source:
            for row_number, row in enumerate(csv.DictReader(source, delimiter=delimiter), 2):
                yield from _iter_human_content(row, location=f"row[{row_number}]")
    except (OSError, csv.Error):
        return


def _text_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{table}")')
        if "CHAR" in str(row[2]).upper()
        or "TEXT" in str(row[2]).upper()
        or not str(row[2]).strip()
    ]


def _iter_database_values(
    connection: sqlite3.Connection,
    *,
    human_only: bool,
) -> Iterable[tuple[str, str]]:
    for table in sorted(_sqlite_tables(connection)):
        for column in _text_columns(connection, table):
            if human_only and not (
                _is_human_content_field(column) or column in JSON_CONTAINER_COLUMNS
            ):
                continue
            # envelope_json duplicates payload_json and primarily adds IDs and
            # hashes; payload_json is the privacy-relevant part.
            if human_only and table == "event_log" and column == "envelope_json":
                continue
            query = f'SELECT rowid, "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'
            try:
                rows = connection.execute(query)
                row_label = "rowid"
            except sqlite3.OperationalError:
                rows = connection.execute(f'SELECT "{column}" FROM "{table}"')
                row_label = "index"
            for index, row in enumerate(rows):
                row_identifier, value = (row[0], row[1]) if row_label == "rowid" else (index, row[0])
                if not isinstance(value, str) or not value:
                    continue
                location = f"{table}.{column}[{row_label}={row_identifier}]"
                if human_only and column in JSON_CONTAINER_COLUMNS:
                    try:
                        payload = json.loads(value)
                    except json.JSONDecodeError:
                        continue
                    base_column = column[:-5] if column.endswith("_json") else column
                    yield from _iter_human_content(
                        payload,
                        location=location,
                        human_container=_is_human_content_field(base_column),
                    )
                elif human_only:
                    if not _looks_like_structural_identifier(value):
                        yield location, value
                else:
                    yield location, value


def _secret_matches(text: str) -> list[str]:
    return sorted(label for label, pattern in SECRET_PATTERNS if pattern.search(text))


def _validate_sensitive_data(
    run_dir: Path,
    connection: sqlite3.Connection,
    errors: list[dict[str, str]],
    checks: dict[str, Any],
) -> None:
    findings: set[tuple[str, tuple[str, ...]]] = set()
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            errors.append(_finding("evidence_read_error", str(error), str(path)))
            continue
        relative = str(path.relative_to(run_dir)).replace("\\", "/")
        # Secret assignments/tokens are unsafe in every field, including a
        # mistakenly persisted api_key field.  Numeric PII is only meaningful
        # in human-facing content, never in IDs, hashes or coordinates.
        secret_labels = _secret_matches(text)
        if secret_labels:
            findings.add((relative, tuple(secret_labels)))

        if path.suffix.casefold() in {".json", ".jsonl"}:
            human_values = _iter_json_human_content(path)
        elif path.suffix.casefold() == ".xml":
            human_values = _iter_xml_human_content(path)
        elif path.suffix.casefold() in {".csv", ".tsv"}:
            human_values = _iter_delimited_human_content(path)
        else:
            human_values = (("document", text),)
        for location, value in human_values:
            labels = _sensitive_matches(value)
            if labels:
                findings.add((f"{relative}:{location}", tuple(labels)))

    for location, value in _iter_database_values(connection, human_only=False):
        labels = _secret_matches(value)
        if labels:
            findings.add((f"corpus.sqlite:{location}", tuple(labels)))
    for location, value in _iter_database_values(connection, human_only=True):
        labels = _sensitive_matches(value)
        if labels:
            findings.add((f"corpus.sqlite:{location}", tuple(labels)))

    checks["sensitive_data_findings"] = len(findings)
    ordered_findings = sorted(findings)
    for location, labels in ordered_findings[:100]:
        errors.append(
            _finding(
                "sensitive_data_detected",
                "persisted corpus contains sensitive pattern(s): " + ", ".join(labels),
                location,
            )
        )
    if len(ordered_findings) > 100:
        errors.append(
            _finding(
                "sensitive_data_detected",
                f"{len(ordered_findings) - 100} additional sensitive findings suppressed",
                str(run_dir),
            )
        )


def _validate_expected_files(
    run_dir: Path,
    profile: Mapping[str, Any],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
) -> None:
    base_files = (
        "manifest.json",
        "checkpoint.json",
        "corpus.sqlite",
        "observations.jsonl",
    )
    completed_exploration_files = (
        "elements.jsonl",
        "transitions.jsonl",
        "failures.jsonl",
        "metrics.jsonl",
        "graph-candidate.sqlite",
    )
    required_files = base_files + (
        completed_exploration_files if profile.get("require_completed_graph") else ()
    )
    missing = [name for name in required_files if not (run_dir / name).is_file()]
    checks["missing_run_files"] = missing
    if missing:
        errors.append(
            _finding("missing_run_files", "required run files missing: " + ", ".join(missing), str(run_dir))
        )

    checkpoint_path = run_dir / "checkpoint.json"
    if checkpoint_path.is_file():
        try:
            checkpoint = _load_json(checkpoint_path)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(_finding("checkpoint_parse_error", str(error), str(checkpoint_path)))
        else:
            if not isinstance(checkpoint, Mapping):
                errors.append(
                    _finding("checkpoint_shape", "checkpoint must be a JSON object", str(checkpoint_path))
                )
            else:
                expected_identity = {
                    "provenance": "emulator_observation",
                    "route_lifecycle": "shadow",
                    "canonical_catalog_version": EXPECTED_CATALOG_VERSION,
                    "canonical_catalog_sha256": EXPECTED_CATALOG_SHA256,
                    "canonical_equivalence_sha256": EXPECTED_EQUIVALENCE_SHA256,
                }
                for key, expected in expected_identity.items():
                    actual = checkpoint.get(key)
                    if actual != expected:
                        errors.append(
                            _finding(
                                "checkpoint_governance_mismatch",
                                f"checkpoint {key} must be {expected!r}, got {actual!r}",
                                str(checkpoint_path),
                            )
                        )
                mutation = checkpoint.get(
                    "canonical_mutation_allowed",
                    checkpoint.get("canonical_catalog_mutation"),
                )
                if mutation not in {False, 0, "false"}:
                    errors.append(
                        _finding(
                            "checkpoint_canonical_mutation_enabled",
                            "checkpoint must keep canonical mutation disabled",
                            str(checkpoint_path),
                        )
                    )

    jsonl_candidates = sorted(
        {path.name for path in run_dir.glob("*.jsonl")} | {name for name in required_files if name.endswith(".jsonl")}
    )
    for name in jsonl_candidates:
        path = run_dir / name
        if path.suffix == ".jsonl" and path.is_file():
            with path.open("r", encoding="utf-8") as source:
                for line_number, raw_line in enumerate(source, 1):
                    if not raw_line.strip():
                        continue
                    try:
                        value = json.loads(raw_line)
                    except json.JSONDecodeError as error:
                        errors.append(
                            _finding(
                                "jsonl_parse_error",
                                f"line {line_number}: {error}",
                                str(path),
                            )
                        )
                        break
                    if not isinstance(value, Mapping):
                        errors.append(
                            _finding(
                                "jsonl_shape",
                                f"line {line_number} must contain a JSON object",
                                str(path),
                            )
                        )
                        break
                    if name == "observations.jsonl":
                        expected_event_identity = {
                            "provenance": "emulator_observation",
                            "route_lifecycle": "shadow",
                            "canonical_catalog_version": EXPECTED_CATALOG_VERSION,
                            "canonical_catalog_sha256": EXPECTED_CATALOG_SHA256,
                            "canonical_equivalence_sha256": EXPECTED_EQUIVALENCE_SHA256,
                        }
                        for key, expected in expected_event_identity.items():
                            actual = value.get(key)
                            if actual != expected:
                                errors.append(
                                    _finding(
                                        "observation_event_governance_mismatch",
                                        f"line {line_number} {key} must be {expected!r}, got {actual!r}",
                                        str(path),
                                    )
                                )


def validate_corpus(run_dir: Path | str, *, repo_root: Path | str = ROOT) -> dict[str, Any]:
    run_dir = Path(run_dir).expanduser().resolve()
    repo_root = Path(repo_root).expanduser().resolve()
    errors: list[dict[str, str]] = []
    checks: dict[str, Any] = {}

    _validate_canonical(repo_root, errors, checks)
    _validate_version_governance(repo_root, errors, checks)
    manifest = _validate_manifest(run_dir / "manifest.json", errors, checks)
    profile = _run_profile(run_dir, manifest)
    checks["run_profile"] = profile
    _validate_expected_files(run_dir, profile, errors, checks)

    db_path = run_dir / "corpus.sqlite"
    if db_path.is_file():
        try:
            connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
            try:
                columns = _validate_schema(connection, errors, checks, db_path)
                _validate_references(connection, columns, profile, errors, checks, db_path)
                _validate_run_governance_rows(connection, columns, errors, checks, db_path)
                _validate_evidence_paths(connection, columns, run_dir, profile, errors, checks)
                _validate_safety(connection, columns, manifest, errors, checks, db_path)
                _validate_metrics(connection, columns, errors, checks, db_path)
                _validate_sensitive_data(run_dir, connection, errors, checks)
            finally:
                connection.close()
        except sqlite3.Error as error:
            errors.append(_finding("corpus_sqlite_error", str(error), str(db_path)))

    _validate_graph_candidate(run_dir / "graph-candidate.sqlite", profile, errors, checks)
    return {
        "schema_version": 1,
        "validator": "emulator_observation_corpus",
        "run_dir": str(run_dir),
        "ok": not errors,
        "error_count": len(errors),
        "errors": errors,
        "checks": checks,
    }


def _latest_run(observation_root: Path) -> Path:
    candidates = sorted(
        (path for path in observation_root.iterdir() if path.is_dir()),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    ) if observation_root.is_dir() else []
    if not candidates:
        raise FileNotFoundError(f"no observation run found under {observation_root}")
    return candidates[-1]


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="run directory containing manifest.json and corpus.sqlite; defaults to newest run",
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--observation-root",
        type=Path,
        default=DEFAULT_OBSERVATION_ROOT,
        help="parent used to select the newest run when --run-dir is omitted",
    )
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        run_dir = args.run_dir or _latest_run(args.observation_root)
        report = validate_corpus(run_dir, repo_root=args.repo_root)
    except (OSError, ValueError) as error:
        report = {
            "schema_version": 1,
            "validator": "emulator_observation_corpus",
            "ok": False,
            "error_count": 1,
            "errors": [_finding("validator_input_error", str(error))],
            "checks": {},
        }
    print(json.dumps(report, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
