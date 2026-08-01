from __future__ import annotations

"""Build privacy-safe review artifacts from a validated physical-device run.

Only ``corpus.sqlite`` and ``graph-candidate.sqlite`` are used as observation
inputs.  Raw screen evidence is never opened.  The generated data remains a
shadow candidate and cannot mutate or promote the frozen canonical V15 catalog.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3
import statistics
import sys
import unicodedata
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.emulator_observation_corpus import (  # noqa: E402
    CANONICAL_CATALOG_SHA256,
    CANONICAL_CATALOG_VERSION,
    CANONICAL_COUNTS,
    CANONICAL_EQUIVALENCE_SHA256,
)
from app.services.real_device_observation_corpus import (  # noqa: E402
    DATASET_ROLE,
    PROVENANCE,
    REVIEW_STATUS,
    ROUTE_LIFECYCLE,
)


VALIDATOR_PATH = ROOT / "scripts" / "Validate-RealDeviceObservationCorpus.py"
DEFAULT_APP_MANIFEST = ROOT / "fixtures" / "navigation" / "real-device-observation-apps.v1.json"
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
EQUIVALENCE_PATH = ROOT / "fixtures" / "navigation" / "function-equivalence.v1.json"

OUTPUT_FILENAMES = (
    "common-menu-synonyms.json",
    "destination-candidates.jsonl",
    "manual-validation.json",
    "navigation-report.json",
)
VERIFIED_EVIDENCE_MODES = frozenset({"verified_evidence", "verified_metadata"})
SAFE_ROUTE_STATUSES = frozenset({"shadow", "candidate"})
PROMOTION_RECOMMENDATION = "not_recommended_until_human_review"

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)")
RESIDENT_ID_RE = re.compile(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)")
FRIENDLI_KEY_RE = re.compile(r"\bflp_[A-Za-z0-9_-]{16,}\b")
BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}\b")
GENERIC_SECRET_RE = re.compile(
    r"(?i)(?:api[_ -]?key|secret|access[_ -]?token|authorization)\s*[=:]\s*"
    r"(?:bearer\s+)?[A-Za-z0-9_./+~=-]{12,}"
)
SOCIAL_HANDLE_RE = re.compile(r"(?<![A-Za-z0-9_@])@[A-Za-z0-9_][A-Za-z0-9_.]{1,29}\b")
KOREAN_ROAD_ADDRESS_RE = re.compile(
    r"(?:서울(?:특별시)?|부산(?:광역시)?|대구(?:광역시)?|인천(?:광역시)?|"
    r"광주(?:광역시)?|대전(?:광역시)?|울산(?:광역시)?|세종(?:특별자치시)?|"
    r"경기(?:도)?|강원(?:특별자치도|도)?|충청[남북]도|전라[남북]도|"
    r"경상[남북]도|제주(?:특별자치도|도)?)\s+"
    r"[가-힣0-9·.-]+(?:시|군|구)?(?:\s+[가-힣0-9·.-]+(?:시|군|구))?\s+"
    r"[가-힣0-9·.-]+(?:로|길|동|읍|면|리)\s*\d",
)
KOREAN_LOCAL_ADDRESS_RE = re.compile(
    r"[가-힣]{1,12}(?:시|군|구)\s+[가-힣0-9·.-]{1,24}(?:로|길|동|읍|면|리)\s*\d"
)
SENSITIVE_PATTERN_MAP = {
    "email": EMAIL_RE,
    "phone": PHONE_RE,
    "resident_id": RESIDENT_ID_RE,
    "friendli_key": FRIENDLI_KEY_RE,
    "bearer_token": BEARER_RE,
    "generic_secret": GENERIC_SECRET_RE,
    "social_handle": SOCIAL_HANDLE_RE,
    "korean_road_address": KOREAN_ROAD_ADDRESS_RE,
    "korean_local_address": KOREAN_LOCAL_ADDRESS_RE,
}
SENSITIVE_PATTERNS = tuple(SENSITIVE_PATTERN_MAP.values())
SHA256_RE = re.compile(r"[0-9a-f]{64}")
FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "user_goal",
        "goal_text",
        "title_text",
        "visible_texts",
        "content_descriptions",
        "screenshot_path",
        "accessibility_tree_path",
        "raw_accessibility_tree",
        "raw_ocr",
    }
)
SOURCE_PRIVACY_FIELDS: dict[str, tuple[str, ...]] = {
    "apps": ("app_name",),
    "screens": (
        "title_text",
        "visible_texts_json",
        "content_descriptions_json",
        "prerequisite",
        "prerequisites_json",
    ),
    "elements": (
        "text",
        "content_description",
        "synonyms_json",
        "expected_result",
        "expected_outcome",
        "evidence_json",
    ),
    "transitions": ("error_content", "error_text"),
    "goals": ("goal_text", "expected_terminal", "evidence_json"),
    "failures": (
        "user_goal",
        "selected_candidate",
        "correct_candidate",
        "failure_reason",
        "missing_synonym_or_rule",
        "required_synonym_or_label",
        "policy_correction",
        "policy_change",
        "retry_result",
        "retest_result",
    ),
    "annotations": ("label", "value_json", "reviewer"),
    "graph_screens": ("title", "structure_json"),
    "graph_routes": ("steps_json",),
}
NON_SEMANTIC_NESTED_KEYS = frozenset(
    {
        "id",
        "element_id",
        "element_key",
        "parent_id",
        "action_id",
        "screen_id",
        "screen_fingerprint",
        "resource_id",
        "sha256",
        "hash",
        "fingerprint",
        "bounds",
        "coordinates",
        "package",
        "app_package",
        "activity",
        "activity_name",
        "class_name",
        "timestamp",
    }
)


class ArtifactBuildError(RuntimeError):
    pass


def build_artifacts(
    run_directory: Path | str,
    *,
    repo_root: Path | str = ROOT,
    app_manifest_path: Path | str = DEFAULT_APP_MANIFEST,
    overwrite: bool = False,
) -> dict[str, Any]:
    run_directory = Path(run_directory).expanduser().resolve()
    repo_root = Path(repo_root).expanduser().resolve()
    app_manifest_path = Path(app_manifest_path).expanduser().resolve()
    corpus_path = run_directory / "corpus.sqlite"
    graph_path = run_directory / "graph-candidate.sqlite"
    for source in (corpus_path, graph_path):
        if not source.is_file():
            raise ArtifactBuildError(f"required validated source is missing: {source.name}")
    _reject_quarantined_source(run_directory)
    output_paths = {name: run_directory / name for name in OUTPUT_FILENAMES}
    collisions = sorted(path.name for path in output_paths.values() if path.exists())
    if collisions and not overwrite:
        raise ArtifactBuildError(
            "refusing to replace existing review artifacts without --force: " + ", ".join(collisions)
        )

    validation = _validate_run(run_directory, repo_root, app_manifest_path)
    if not validation.get("ok"):
        codes = sorted(
            {
                str(item.get("code", "validation_error"))
                for item in validation.get("errors", [])
                if isinstance(item, Mapping)
            }
        )
        raise ArtifactBuildError("physical run validation failed: " + ", ".join(codes))

    source_hashes_before = {
        corpus_path.name: _sha256_file(corpus_path),
        graph_path.name: _sha256_file(graph_path),
    }
    catalog = _load_v15_catalog(repo_root)
    with _read_only_sqlite(corpus_path) as corpus, _read_only_sqlite(graph_path) as graph:
        source = _read_source_rows(corpus, graph)
        _assert_source_privacy_safe(source)
        if len(source["runs"]) != 1:
            raise ArtifactBuildError("validated source must contain exactly one run row")
        source_run_id = _safe_identifier(source["runs"][0].get("run_id"), "run")
        synonyms, label_diagnostics = _build_synonym_artifact(source, catalog)
        destinations = _build_destination_candidates(source, catalog)
        report = _build_navigation_report(
            source,
            destinations,
            label_diagnostics,
            validation,
            source_hashes_before,
        )
        manual = _build_manual_validation(source, destinations, label_diagnostics, report)

    synonyms["source_run_id"] = source_run_id
    report["source_run_id"] = source_run_id
    manual["source_run_id"] = source_run_id
    for destination in destinations:
        destination["source_run_id"] = source_run_id

    generated: dict[str, Any] = {
        "common-menu-synonyms.json": synonyms,
        "manual-validation.json": manual,
        "navigation-report.json": report,
    }
    for name, payload in generated.items():
        _assert_privacy_safe(payload, location=name)
    for destination in destinations:
        _assert_privacy_safe(destination, location="destination-candidates.jsonl")

    source_hashes_after = {
        corpus_path.name: _sha256_file(corpus_path),
        graph_path.name: _sha256_file(graph_path),
    }
    if source_hashes_after != source_hashes_before:
        raise ArtifactBuildError("source databases changed during read-only artifact generation")

    staging_directory = run_directory / f".function-graph-artifacts.{uuid.uuid4().hex}.staging"
    staging_directory.mkdir(mode=0o700)
    staged_paths = {name: staging_directory / name for name in OUTPUT_FILENAMES}
    try:
        for name, payload in generated.items():
            _atomic_write_json(staged_paths[name], payload)
        _atomic_write_jsonl(staged_paths["destination-candidates.jsonl"], destinations)
        _validate_staged_artifact_set(staged_paths)
        staged_hashes = {
            name: _sha256_file(path) for name, path in sorted(staged_paths.items())
        }
        _publish_artifact_set(
            staged_paths=staged_paths,
            output_paths=output_paths,
            overwrite=overwrite,
            expected_hashes=staged_hashes,
        )
    finally:
        _remove_flat_temporary_directory(staging_directory)
    output_hashes = {name: _sha256_file(path) for name, path in sorted(output_paths.items())}
    if output_hashes != staged_hashes:
        raise ArtifactBuildError("published artifact set does not match the validated staged set")
    return {
        "ok": True,
        "run_directory": str(run_directory),
        "provenance": PROVENANCE,
        "dataset_role": DATASET_ROLE,
        "route_lifecycle": ROUTE_LIFECYCLE,
        "canonical_promotion": PROMOTION_RECOMMENDATION,
        "source_sha256": source_hashes_before,
        "output_sha256": output_hashes,
        "counts": {
            "synonym_entries": len(synonyms["entries"]),
            "destination_candidates": len(destinations),
            "manual_review_items": len(manual["review_items"]),
            "apps": len(report["apps"]),
        },
    }


def _reject_quarantined_source(run_directory: Path) -> None:
    marker_path = run_directory / "QUARANTINED.json"
    if not marker_path.exists():
        return
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArtifactBuildError(
            "source eligibility rejected: source_quarantine_marker_invalid"
        ) from error
    if not isinstance(marker, Mapping):
        raise ArtifactBuildError(
            "source eligibility rejected: source_quarantine_marker_invalid"
        )
    reason_codes: list[str] = []
    if str(marker.get("status") or "").strip().casefold() == "quarantined":
        reason_codes.append("source_run_quarantined")
    if marker.get("builder_input_allowed") is False:
        reason_codes.append("builder_input_disallowed")
    if reason_codes:
        raise ArtifactBuildError(
            "source eligibility rejected: " + ",".join(sorted(reason_codes))
        )


def _validate_run(run_directory: Path, repo_root: Path, app_manifest_path: Path) -> Mapping[str, Any]:
    spec = importlib.util.spec_from_file_location(
        "exitguide_real_device_artifact_validator", VALIDATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise ArtifactBuildError("real-device validator could not be loaded")
    validator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = validator
    spec.loader.exec_module(validator)
    report = validator.validate_corpus(
        run_directory,
        repo_root=repo_root,
        app_manifest_path=app_manifest_path,
    )
    if not isinstance(report, Mapping):
        raise ArtifactBuildError("real-device validator returned an invalid report")
    return report


def _read_source_rows(corpus: sqlite3.Connection, graph: sqlite3.Connection) -> dict[str, Any]:
    source: dict[str, Any] = {}
    for table in (
        "apps",
        "runs",
        "screens",
        "elements",
        "transitions",
        "goals",
        "failures",
        "metrics",
        "annotations",
    ):
        source[table] = _table_rows(corpus, table)
    source["graph_apps"] = _table_rows(graph, "universal_apps")
    source["graph_screens"] = _table_rows(graph, "universal_screens")
    source["graph_routes"] = _table_rows(graph, "universal_routes")
    for route in source["graph_routes"]:
        status = str(route.get("status") or "").casefold()
        if status not in SAFE_ROUTE_STATUSES or int(route.get("provisional") or 0) != 1:
            raise ArtifactBuildError("graph candidate contains a serving or non-provisional route")
    return source


def _load_v15_catalog(repo_root: Path) -> dict[str, Any]:
    catalog_path = repo_root / CATALOG_PATH.relative_to(ROOT)
    equivalence_path = repo_root / EQUIVALENCE_PATH.relative_to(ROOT)
    if _sha256_file(catalog_path) != CANONICAL_CATALOG_SHA256:
        raise ArtifactBuildError("frozen V15 catalog SHA-256 mismatch")
    if _sha256_file(equivalence_path) != CANONICAL_EQUIVALENCE_SHA256:
        raise ArtifactBuildError("frozen V15 equivalence SHA-256 mismatch")
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if payload.get("catalog_version") != CANONICAL_CATALOG_VERSION:
        raise ArtifactBuildError("frozen V15 catalog version mismatch")
    functions = {
        str(item["function_id"]): item
        for item in payload.get("functions", [])
        if isinstance(item, Mapping) and item.get("function_id")
    }
    equivalence = json.loads(equivalence_path.read_text(encoding="utf-8"))
    canonical_by_id = {function_id: function_id for function_id in functions}
    for item in equivalence.get("classes", []):
        if not isinstance(item, Mapping):
            continue
        canonical = str(item.get("canonical_function_id") or "")
        if not canonical:
            continue
        canonical_by_id[canonical] = canonical
        for alias in item.get("alias_function_ids", []):
            canonical_by_id[str(alias)] = canonical
    alias_index: dict[str, set[str]] = defaultdict(set)
    for function_id, item in functions.items():
        labels = [item.get("name_ko"), item.get("name_en")]
        raw_aliases = item.get("aliases", {})
        if isinstance(raw_aliases, Mapping):
            for values in raw_aliases.values():
                if isinstance(values, list):
                    labels.extend(values)
        elif isinstance(raw_aliases, list):
            labels.extend(raw_aliases)
        for label in labels:
            normalized = _normalize_label(label)
            if normalized:
                alias_index[normalized].add(canonical_by_id.get(function_id, function_id))
    return {
        "functions": functions,
        "canonical_by_id": canonical_by_id,
        "alias_index": alias_index,
    }


def _build_synonym_artifact(
    source: Mapping[str, Any], catalog: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    screens = {str(row.get("screen_id")): row for row in source["screens"]}
    aggregates: dict[str, dict[str, Any]] = {}
    excluded_metadata_only: list[dict[str, str]] = []
    ambiguous: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    for element in source["elements"]:
        element_id = _safe_identifier(element.get("element_id"), "element")
        screen_id = str(element.get("screen_id") or "")
        screen = screens.get(screen_id, {})
        app_package = _safe_identifier(screen.get("app_package"), "app")
        payload = _payload(element)
        if (
            int(element.get("privacy_verified") or 0) != 1
            or str(element.get("evidence_mode") or "") not in VERIFIED_EVIDENCE_MODES
            or payload.get("privacy_verified") is not True
        ):
            excluded_metadata_only.append(
                {"element_id": element_id, "app_package": app_package, "reason": "metadata_only"}
            )
            continue
        labels = _observed_labels(element)
        if not labels:
            continue
        raw_function_id = str(element.get("semantic_function_id") or "").strip()
        canonical_id = ""
        mapping_method = ""
        if raw_function_id in catalog["canonical_by_id"]:
            canonical_id = str(catalog["canonical_by_id"][raw_function_id])
            mapping_method = "observed_semantic_function_id"
        else:
            exact_candidates: set[str] = set()
            for label in labels:
                exact_candidates.update(catalog["alias_index"].get(_normalize_label(label), set()))
            if len(exact_candidates) == 1:
                canonical_id = next(iter(exact_candidates))
                mapping_method = "unique_exact_v15_label"
            elif len(exact_candidates) > 1:
                ambiguous.append(
                    {
                        "element_id": element_id,
                        "app_package": app_package,
                        "candidate_function_ids": sorted(exact_candidates),
                    }
                )
                continue
        if not canonical_id or canonical_id not in catalog["functions"]:
            unmapped.append(
                {
                    "element_id": element_id,
                    "app_package": app_package,
                    "observed_semantic_function_id": _safe_identifier(raw_function_id, "function")
                    if raw_function_id
                    else None,
                }
            )
            continue
        aggregate = aggregates.setdefault(
            canonical_id,
            {
                "labels": Counter(),
                "apps": set(),
                "elements": set(),
                "mapping_methods": set(),
                "confidences": [],
            },
        )
        aggregate["labels"].update(labels)
        aggregate["apps"].add(app_package)
        aggregate["elements"].add(element_id)
        aggregate["mapping_methods"].add(mapping_method)
        confidence = _number(element.get("confidence"))
        if confidence is not None:
            aggregate["confidences"].append(confidence)

    entries: list[dict[str, Any]] = []
    for function_id, aggregate in sorted(aggregates.items()):
        definition = catalog["functions"][function_id]
        observed_labels = [
            {"label": label, "observation_count": count}
            for label, count in sorted(
                aggregate["labels"].items(), key=lambda item: (-item[1], item[0].casefold())
            )
        ]
        entries.append(
            {
                "semantic_function_id": function_id,
                "v15_mapping_status": "mapped_candidate",
                "mapping_methods": sorted(aggregate["mapping_methods"]),
                "observed_labels": observed_labels,
                "v15_reference_labels": _catalog_reference_labels(definition),
                "app_packages": sorted(aggregate["apps"]),
                "app_count": len(aggregate["apps"]),
                "element_ids": sorted(aggregate["elements"]),
                "observation_count": sum(item["observation_count"] for item in observed_labels),
                "confidence": _mean_or_none(aggregate["confidences"]),
                "risk_level": _safe_token(definition.get("risk_level")),
                "terminal": bool(definition.get("terminal")),
                "state_changing": bool(definition.get("state_changing")),
                "lifecycle": "candidate",
                "route_lifecycle": ROUTE_LIFECYCLE,
                "canonical_write_allowed": False,
                "human_review_required": True,
            }
        )
    artifact = {
        **_artifact_header("common_menu_synonyms"),
        "description": "Observed, privacy-reviewed labels mapped conservatively to frozen V15 functions.",
        "metadata_only_elements_excluded": len(excluded_metadata_only),
        "ambiguous_mapping_count": len(ambiguous),
        "unmapped_count": len(unmapped),
        "entries": entries,
    }
    return artifact, {
        "metadata_only": excluded_metadata_only,
        "ambiguous": ambiguous,
        "unmapped": unmapped,
    }


def _build_destination_candidates(
    source: Mapping[str, Any], catalog: Mapping[str, Any]
) -> list[dict[str, Any]]:
    screens = {str(row.get("screen_id")): row for row in source["screens"]}
    elements = {str(row.get("element_id")): row for row in source["elements"]}
    graph_apps = {str(row.get("app_key")): str(row.get("app_package")) for row in source["graph_apps"]}
    routes_by_target: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for route in source["graph_routes"]:
        app_package = _safe_identifier(graph_apps.get(str(route.get("app_key"))), "app")
        target = str(route.get("target_function") or "")
        canonical_id = str(catalog["canonical_by_id"].get(target, target))
        route_summary = {
            "route_id": _safe_identifier(route.get("route_id"), "route"),
            "status": str(route.get("status")),
            "provisional": bool(route.get("provisional")),
            "step_count": _json_list_length(route.get("steps_json")),
            "confidence": _number(route.get("confidence")),
            "destination_screen_id": _safe_identifier(
                route.get("destination_screen_fingerprint"), "screen"
            ),
        }
        routes_by_target[(app_package, canonical_id)].append(route_summary)

    failures_by_goal = Counter(str(row.get("goal_id") or "") for row in source["failures"])
    candidates: list[dict[str, Any]] = []
    represented_routes: set[str] = set()
    for goal in sorted(source["goals"], key=lambda row: str(row.get("goal_id"))):
        goal_id = _safe_identifier(goal.get("goal_id"), "goal")
        app_package = _safe_identifier(goal.get("app_package"), "app")
        raw_function_id = str(
            goal.get("standard_goal_id")
            or goal.get("canonical_goal_id")
            or goal.get("semantic_function_id")
            or ""
        )
        canonical_id = str(catalog["canonical_by_id"].get(raw_function_id, raw_function_id))
        definition = catalog["functions"].get(canonical_id, {})
        screen_id_raw = str(goal.get("terminal_candidate_screen_id") or "")
        element_id_raw = str(goal.get("terminal_candidate_element_id") or "")
        screen = screens.get(screen_id_raw)
        element = elements.get(element_id_raw)
        label = _verified_element_label(element) if element else None
        routes = sorted(routes_by_target.get((app_package, canonical_id), []), key=lambda row: row["route_id"])
        represented_routes.update(route["route_id"] for route in routes)
        candidate_id = "destination_" + hashlib.sha256(
            f"{goal_id}|{app_package}|{canonical_id}|{screen_id_raw}|{element_id_raw}".encode("utf-8")
        ).hexdigest()[:20]
        destination_observed = screen is not None or element is not None
        candidates.append(
            {
                **_record_header(),
                "candidate_id": candidate_id,
                "goal_id": goal_id,
                "app_package": app_package,
                "semantic_function_id": _safe_identifier(canonical_id, "function")
                if canonical_id
                else None,
                "v15_mapping_status": "mapped_candidate" if definition else "unmapped_candidate",
                "terminal_screen_id": _safe_identifier(screen_id_raw, "screen") if screen_id_raw else None,
                "terminal_element_id": _safe_identifier(element_id_raw, "element") if element_id_raw else None,
                "terminal_label": label,
                "destination_observed": destination_observed,
                "goal_status": _safe_token(goal.get("status")),
                "confidence": _number(goal.get("terminal_confidence")),
                "risk_level": _safe_token(element.get("risk_level") if element else definition.get("risk_level")),
                "is_final_action": bool(
                    (element or {}).get("is_final_action") or definition.get("terminal")
                ),
                "state_changing": bool(definition.get("state_changing")),
                "failure_count": int(failures_by_goal.get(str(goal.get("goal_id") or ""), 0)),
                "shadow_routes": routes,
                "manual_confirmation_required": True,
                "serving_allowed": False,
                "human_review_required": True,
            }
        )
    for (app_package, canonical_id), routes in sorted(routes_by_target.items()):
        for route in routes:
            if route["route_id"] in represented_routes:
                continue
            definition = catalog["functions"].get(canonical_id, {})
            candidates.append(
                {
                    **_record_header(),
                    "candidate_id": "destination_route_" + route["route_id"],
                    "goal_id": None,
                    "app_package": app_package,
                    "semantic_function_id": _safe_identifier(canonical_id, "function"),
                    "v15_mapping_status": "mapped_candidate" if definition else "unmapped_candidate",
                    "terminal_screen_id": route["destination_screen_id"],
                    "terminal_element_id": None,
                    "terminal_label": None,
                    "destination_observed": True,
                    "goal_status": "route_only_candidate",
                    "confidence": route["confidence"],
                    "risk_level": _safe_token(definition.get("risk_level")),
                    "is_final_action": bool(definition.get("terminal")),
                    "state_changing": bool(definition.get("state_changing")),
                    "failure_count": 0,
                    "shadow_routes": [route],
                    "manual_confirmation_required": True,
                    "serving_allowed": False,
                    "human_review_required": True,
                }
            )
    return sorted(candidates, key=lambda item: item["candidate_id"])


def _build_navigation_report(
    source: Mapping[str, Any],
    destinations: list[dict[str, Any]],
    label_diagnostics: Mapping[str, Any],
    validation: Mapping[str, Any],
    source_hashes: Mapping[str, str],
) -> dict[str, Any]:
    apps = {str(row.get("app_package") or "") for row in source["apps"] if row.get("app_package")}
    apps.update(str(row.get("app_package") or "") for row in source["screens"] if row.get("app_package"))
    screen_app = {str(row.get("screen_id")): str(row.get("app_package")) for row in source["screens"]}
    element_app = {
        str(row.get("element_id")): screen_app.get(str(row.get("screen_id")), "")
        for row in source["elements"]
    }
    graph_app_by_key = {str(row.get("app_key")): str(row.get("app_package")) for row in source["graph_apps"]}
    graph_routes_by_app = Counter(
        graph_app_by_key.get(str(row.get("app_key")), "") for row in source["graph_routes"]
    )
    report_apps: list[dict[str, Any]] = []
    for app_package_raw in sorted(apps):
        app_package = _safe_identifier(app_package_raw, "app")
        app_rows = [row for row in source["apps"] if str(row.get("app_package")) == app_package_raw]
        screens = [row for row in source["screens"] if str(row.get("app_package")) == app_package_raw]
        screen_ids = {str(row.get("screen_id")) for row in screens}
        elements = [row for row in source["elements"] if str(row.get("screen_id")) in screen_ids]
        element_ids = {str(row.get("element_id")) for row in elements}
        transitions = [row for row in source["transitions"] if str(row.get("source_screen_id")) in screen_ids]
        goals = [row for row in source["goals"] if str(row.get("app_package")) == app_package_raw]
        failures = [row for row in source["failures"] if str(row.get("app_package")) == app_package_raw]
        metrics = [row for row in source["metrics"] if str(row.get("app_package")) == app_package_raw]
        annotations = [
            row
            for row in source["annotations"]
            if str(row.get("entity_id")) in screen_ids | element_ids
        ]
        app_destinations = [item for item in destinations if item["app_package"] == app_package]
        report_apps.append(
            {
                "app_package": app_package,
                "app_name": _first_safe_label(row.get("app_name") for row in app_rows),
                "versions": sorted(
                    {
                        _safe_token(row.get("app_version"))
                        for row in [*app_rows, *screens]
                        if _safe_token(row.get("app_version"))
                    }
                ),
                "counts": {
                    "screens": len(screens),
                    "elements": len(elements),
                    "transitions": len(transitions),
                    "goals": len(goals),
                    "failures": len(failures),
                    "annotations": len(annotations),
                    "destination_candidates": len(app_destinations),
                    "shadow_routes": int(graph_routes_by_app.get(app_package_raw, 0)),
                },
                "screen_types": _safe_counter(
                    _payload(row).get("screen_type") or row.get("screen_type") for row in screens
                ),
                "boundaries": _boundary_summary(screens, elements),
                "goal_statuses": _safe_counter(row.get("status") for row in goals),
                "failure_reasons": _safe_counter(row.get("failure_reason") for row in failures),
                "performance": _performance_summary(metrics, transitions),
            }
        )
    overall_metrics = _performance_summary(source["metrics"], source["transitions"])
    if overall_metrics["unsafe_auto_click_count"] != 0 or overall_metrics["final_action_auto_click_count"] != 0:
        raise ArtifactBuildError("validated source violates zero automatic unsafe/final action invariant")
    return {
        **_artifact_header("navigation_report"),
        "source_validation": {
            "validator": _safe_token(validation.get("validator")),
            "ok": bool(validation.get("ok")),
            "error_count": int(validation.get("error_count") or 0),
        },
        "source_database_sha256": dict(source_hashes),
        "scope_note": "Rates are null when the validated corpus has no corresponding measurement.",
        "metrics_definition": {
            "success_rate": "sum(success_count) / sum(attempt_count) for rows carrying both explicit counts",
            "false_positive_rate": "sum(false_positive_count) / sum(attempt_count) for rows carrying both explicit counts",
            "p95": "nearest-rank percentile over observed task measurements",
        },
        "overall": {
            "counts": {
                "apps": len(report_apps),
                "screens": len(source["screens"]),
                "elements": len(source["elements"]),
                "transitions": len(source["transitions"]),
                "goals": len(source["goals"]),
                "failures": len(source["failures"]),
                "destination_candidates": len(destinations),
                "shadow_routes": len(source["graph_routes"]),
                "metadata_only_elements_excluded_from_semantics": len(label_diagnostics["metadata_only"]),
            },
            "performance": overall_metrics,
        },
        "apps": report_apps,
        "canonical_promotion": {
            "recommendation": PROMOTION_RECOMMENDATION,
            "canonical_write_allowed": False,
        },
    }


def _build_manual_validation(
    source: Mapping[str, Any],
    destinations: list[dict[str, Any]],
    label_diagnostics: Mapping[str, Any],
    report: Mapping[str, Any],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for destination in destinations:
        reasons = ["confirm destination on current physical app version"]
        if destination["v15_mapping_status"] != "mapped_candidate":
            reasons.append("confirm semantic function mapping")
        if destination["is_final_action"]:
            reasons.append("confirm user-owned final-action boundary")
        if destination["failure_count"]:
            reasons.append("retest recorded failure path")
        items.append(
            {
                "review_id": "review_" + destination["candidate_id"],
                "review_type": "destination_candidate",
                "app_package": destination["app_package"],
                "candidate_id": destination["candidate_id"],
                "reasons": reasons,
                "required_outcome": "human_confirmed_or_rejected",
            }
        )
    for kind in ("metadata_only", "ambiguous", "unmapped"):
        for item in label_diagnostics[kind]:
            items.append(
                {
                    "review_id": "review_label_"
                    + hashlib.sha256(_canonical_json(item).encode("utf-8")).hexdigest()[:18],
                    "review_type": f"semantic_label_{kind}",
                    "app_package": item.get("app_package"),
                    "element_id": item.get("element_id"),
                    "reasons": [
                        "collect privacy-reviewed semantic evidence"
                        if kind == "metadata_only"
                        else "human semantic mapping required"
                    ],
                    "required_outcome": "human_confirmed_or_rejected",
                }
            )
    for failure in source["failures"]:
        items.append(
            {
                "review_id": "review_failure_" + _safe_identifier(failure.get("failure_id"), "failure"),
                "review_type": "recorded_failure",
                "app_package": _safe_identifier(failure.get("app_package"), "app"),
                "failure_id": _safe_identifier(failure.get("failure_id"), "failure"),
                "failure_reason": _safe_note(failure.get("failure_reason")),
                "policy_change": _safe_note(failure.get("policy_change") or failure.get("policy_correction")),
                "retest_result": _safe_token(failure.get("retest_result") or failure.get("retry_result")),
                "reasons": ["verify failure cause and repeat the corrected path"],
                "required_outcome": "retested_on_physical_device",
            }
        )
    items.sort(key=lambda item: item["review_id"])
    return {
        **_artifact_header("manual_validation_queue"),
        "summary": {
            "review_item_count": len(items),
            "destination_candidate_count": len(destinations),
            "recorded_failure_count": len(source["failures"]),
            "metadata_only_semantic_exclusion_count": len(label_diagnostics["metadata_only"]),
        },
        "review_items": items,
        "required_physical_follow_up": [
            "confirm each destination and back-navigation path on the recorded app version",
            "confirm authentication and verification boundaries without storing entered values",
            "confirm every consequential final control remains user-operated",
            "repeat successful tasks after a fresh app launch and after an app update",
            "retest every failure after synonym or policy changes",
        ],
        "canonical_promotion": {
            "recommendation": PROMOTION_RECOMMENDATION,
            "required_before_reconsideration": [
                "human review of every destination candidate",
                "independent physical-device replay",
                "zero unsafe and final automatic actions",
                "privacy review of all retained evidence derivatives",
                "explicit approval separate from this builder",
            ],
            "canonical_write_allowed": False,
            "v16_v20_promotion_allowed": False,
            "v21_status": "research_only_noncanonical",
            "v22_plus_allowed": False,
        },
        "report_app_count": len(report["apps"]),
    }


def _performance_summary(
    metrics: Iterable[Mapping[str, Any]], transitions: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    raw_metric_rows = list(metrics)
    metric_rows, metric_row_policy = _latest_task_summary_rows(raw_metric_rows)
    transition_rows = list(transitions)
    durations = _numeric_values(metric_rows, "exploration_time_ms")
    success_rate, success_basis = _explicit_attempt_rate(
        metric_rows,
        numerator_field="success_count",
        legacy_boolean_field="destination_found_success",
    )
    false_positive_rate, false_positive_basis = _explicit_attempt_rate(
        metric_rows,
        numerator_field="false_positive_count",
        legacy_boolean_field="wrong_terminal_destination",
    )
    count_fields = (
        "click_count",
        "scroll_count",
        "back_count",
        "repeat_screen_visit_count",
        "user_intervention_count",
    )
    counts = {
        field: _distribution(_numeric_values(metric_rows, field), include_total=True)
        for field in count_fields
    }
    decision_modes = Counter()
    fallback_modes = Counter()
    for row in [*metric_rows, *transition_rows]:
        payload = _payload(row)
        decision = _safe_token(payload.get("decision_mode"))
        if decision:
            decision_modes[decision] += 1
        fallback = _safe_token(
            payload.get("fallback_mode")
            or payload.get("fallback_reason")
            or ("used" if payload.get("fallback_used") is True else None)
        )
        if fallback:
            fallback_modes[fallback] += 1
    # Safety is an invariant over every persisted event, not merely the latest
    # summary for a task.  Functional/performance counters use the latest
    # terminal task summary to avoid summing cumulative per-screen metrics.
    unsafe = sum(_numeric_values(raw_metric_rows, "unsafe_auto_click_count"))
    final = sum(_numeric_values(raw_metric_rows, "final_action_auto_click_count"))
    unsafe += sum(
        1
        for row in transition_rows
        if _truthy(row.get("auto_executed")) and _truthy(row.get("unsafe_action"))
    )
    final += sum(
        1
        for row in transition_rows
        if _truthy(row.get("auto_executed")) and _truthy(row.get("is_final_action"))
    )
    return {
        "measurement_count": len(metric_rows),
        "raw_metric_event_count": len(raw_metric_rows),
        "metric_row_policy": metric_row_policy,
        "success_rate": success_rate,
        "success_rate_basis": success_basis,
        "false_positive_rate": false_positive_rate,
        "false_positive_rate_basis": false_positive_basis,
        "exploration_time_ms": _distribution(durations),
        **counts,
        "decision_modes": _counter_list(decision_modes),
        "fallback_modes": _counter_list(fallback_modes),
        "unsafe_auto_click_count": int(unsafe),
        "final_action_auto_click_count": int(final),
    }


def _latest_task_summary_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], str]:
    """Select one authoritative terminal metric per app/goal task.

    Older collectors emitted cumulative policy metrics after every screen.  A
    naive sum turns a 3-click exploration into 1+2+3 clicks.  New collectors
    emit ``metric_dimension=task_summary`` with a stable ``task_id`` and an
    increasing ``attempt_number``.  When such rows exist we ignore all
    intermediate metrics and retain only the latest summary for each task.
    """

    summaries: list[Mapping[str, Any]] = []
    for row in rows:
        payload = _payload(row)
        dimension = _safe_token(
            payload.get("metric_dimension") or row.get("metric_dimension")
        )
        if dimension == "task_summary":
            summaries.append(row)
    if not summaries:
        return list(rows), "legacy_all_metric_events"

    selected: dict[str, tuple[tuple[float, float, str], Mapping[str, Any]]] = {}
    for row in summaries:
        payload = _payload(row)
        task_id = _safe_identifier(
            payload.get("task_id")
            or row.get("task_id")
            or (
                f"{payload.get('app_package') or row.get('app_package')}::"
                f"{payload.get('goal_id') or row.get('goal_id')}"
            ),
            "task",
        )
        attempt = _number(
            payload.get("attempt_number", row.get("attempt_number"))
        )
        sequence = _number(row.get("sequence"))
        recorded = str(
            payload.get("recorded_at") or row.get("recorded_at") or ""
        )
        order = (attempt if attempt is not None else 0.0, sequence or 0.0, recorded)
        previous = selected.get(task_id)
        if previous is None or order > previous[0]:
            selected[task_id] = (order, row)
    return [selected[key][1] for key in sorted(selected)], "latest_task_summary_per_task"


def _boundary_summary(
    screens: Iterable[Mapping[str, Any]], elements: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    boundary_screens: list[dict[str, str]] = []
    for screen in screens:
        payload = _payload(screen)
        tokens = " ".join(
            str(payload.get(key) or screen.get(key) or "")
            for key in ("screen_type", "login_state", "prerequisite")
        ).casefold()
        kind = ""
        if "captcha" in tokens:
            kind = "captcha"
        elif any(token in tokens for token in ("login", "auth", "identity", "verification")):
            kind = "authentication_or_verification"
        if kind:
            boundary_screens.append(
                {
                    "screen_id": _safe_identifier(screen.get("screen_id"), "screen"),
                    "boundary_type": kind,
                }
            )
    final_elements = [
        {
            "element_id": _safe_identifier(row.get("element_id"), "element"),
            "semantic_function_id": _safe_identifier(row.get("semantic_function_id"), "function")
            if row.get("semantic_function_id")
            else None,
            "risk_level": _safe_token(row.get("risk_level")),
        }
        for row in elements
        if _truthy(row.get("is_final_action"))
    ]
    return {
        "authentication_or_verification": boundary_screens,
        "final_action_elements": final_elements,
        "final_action_count": len(final_elements),
    }


def _observed_labels(element: Mapping[str, Any]) -> list[str]:
    values: list[Any] = [element.get("text"), element.get("content_description")]
    synonyms = _decode_json(element.get("synonyms_json"), default=[])
    if isinstance(synonyms, list):
        values.extend(synonyms)
    labels: list[str] = []
    for value in values:
        label = _safe_label(value)
        if label and label not in labels:
            labels.append(label)
    return labels


def _verified_element_label(element: Mapping[str, Any] | None) -> str | None:
    if not element:
        return None
    payload = _payload(element)
    if (
        int(element.get("privacy_verified") or 0) != 1
        or str(element.get("evidence_mode") or "") not in VERIFIED_EVIDENCE_MODES
        or payload.get("privacy_verified") is not True
    ):
        return None
    labels = _observed_labels(element)
    return labels[0] if labels else None


def _catalog_reference_labels(definition: Mapping[str, Any]) -> list[dict[str, str]]:
    labels: list[dict[str, str]] = []
    for locale, key in (("ko", "name_ko"), ("en", "name_en")):
        label = _safe_label(definition.get(key))
        if label:
            labels.append({"locale": locale, "label": label})
    aliases = definition.get("aliases", {})
    if isinstance(aliases, Mapping):
        for locale, values in aliases.items():
            if not isinstance(values, list):
                continue
            for value in values:
                label = _safe_label(value)
                item = {"locale": _safe_token(locale) or "und", "label": label} if label else None
                if item and item not in labels:
                    labels.append(item)
                if len(labels) >= 16:
                    return labels
    return labels


def _artifact_header(artifact_type: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": artifact_type,
        "provenance": PROVENANCE,
        "dataset_role": DATASET_ROLE,
        "review_status": REVIEW_STATUS,
        "review_lifecycle": "candidate",
        "route_lifecycle": ROUTE_LIFECYCLE,
        "canonical_catalog": {
            "version": CANONICAL_CATALOG_VERSION,
            "sha256": CANONICAL_CATALOG_SHA256,
            "equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            "domain_count": CANONICAL_COUNTS["domains"],
            "function_count": CANONICAL_COUNTS["physical_functions"],
            "terminal_function_count": CANONICAL_COUNTS["physical_intents"],
            "intent_count": CANONICAL_COUNTS["physical_intents"],
        },
        "canonical_mutation_allowed": False,
        "serving_allowed": False,
        "human_review_required": True,
    }


def _record_header() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "provenance": PROVENANCE,
        "dataset_role": DATASET_ROLE,
        "review_status": REVIEW_STATUS,
        "review_lifecycle": "candidate",
        "route_lifecycle": ROUTE_LIFECYCLE,
        "canonical_catalog_version": CANONICAL_CATALOG_VERSION,
        "canonical_mutation_allowed": False,
    }


def _table_rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if exists is None:
        raise ArtifactBuildError(f"validated database is missing table: {table}")
    return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]


class _ReadOnlyConnection:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self.connection = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA query_only=ON")
        return self.connection

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.connection is not None:
            self.connection.close()


def _read_only_sqlite(path: Path) -> _ReadOnlyConnection:
    return _ReadOnlyConnection(path)


def _payload(row: Mapping[str, Any]) -> dict[str, Any]:
    value = _decode_json(row.get("payload_json"), default={})
    return value if isinstance(value, dict) else {}


def _decode_json(value: Any, *, default: Any) -> Any:
    if value in (None, ""):
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _normalize_label(value: Any) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _safe_label(value: Any) -> str | None:
    if value is None:
        return None
    label = " ".join(str(value).split()).strip()
    if not label or len(label) > 120 or label.casefold() in {"[redacted]", "redacted"}:
        return None
    if any(pattern.search(label) for pattern in SENSITIVE_PATTERNS):
        return None
    return label


def _safe_note(value: Any) -> str | None:
    label = _safe_label(value)
    return label[:160] if label else None


def _safe_identifier(value: Any, prefix: str) -> str:
    raw = str(value or "").strip()
    if raw and len(raw) <= 160 and re.fullmatch(r"[A-Za-z0-9_.:@-]+", raw):
        return raw
    return f"{prefix}_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]


def _safe_token(value: Any) -> str | None:
    label = _safe_label(value)
    if not label:
        return None
    if len(label) > 80:
        return None
    return label


def _first_safe_label(values: Iterable[Any]) -> str | None:
    for value in values:
        label = _safe_label(value)
        if label:
            return label
    return None


def _safe_counter(values: Iterable[Any]) -> list[dict[str, Any]]:
    counter = Counter(label for value in values if (label := _safe_token(value)))
    return _counter_list(counter)


def _counter_list(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _numeric_values(rows: Iterable[Mapping[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = _number(row.get(key))
        if value is not None:
            values.append(value)
    return values


def _explicit_attempt_rate(
    rows: Iterable[Mapping[str, Any]],
    *,
    numerator_field: str,
    legacy_boolean_field: str,
) -> tuple[float | None, dict[str, Any]]:
    eligible: list[tuple[int, int]] = []
    incomplete_rows = 0
    for row in rows:
        payload = _payload(row)
        numerator = _number(payload.get(numerator_field, row.get(numerator_field)))
        attempts = _number(payload.get("attempt_count", row.get("attempt_count")))
        legacy_boolean = row.get(legacy_boolean_field)
        relevant = numerator is not None or attempts is not None or legacy_boolean is not None
        if not relevant:
            continue
        if numerator is None or attempts is None:
            incomplete_rows += 1
            continue
        if (
            numerator < 0
            or attempts < 0
            or not numerator.is_integer()
            or not attempts.is_integer()
            or numerator > attempts
        ):
            raise ArtifactBuildError(
                f"invalid explicit {numerator_field}/attempt_count metric pair"
            )
        eligible.append((int(numerator), int(attempts)))
    numerator_total = sum(item[0] for item in eligible)
    attempt_total = sum(item[1] for item in eligible)
    available = bool(eligible) and incomplete_rows == 0 and attempt_total > 0
    basis = {
        "availability": "available" if available else "unavailable",
        "numerator_field": numerator_field,
        "numerator_count": numerator_total if available else None,
        "attempt_count": attempt_total if available else None,
        "eligible_row_count": len(eligible),
        "incomplete_relevant_row_count": incomplete_rows,
        "unavailable_reason": None
        if available
        else (
            "explicit_attempt_count_missing"
            if incomplete_rows
            else "no_complete_explicit_count_measurement"
        ),
    }
    return (
        round(numerator_total / attempt_total, 6) if available else None,
        basis,
    )


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return bool(value)


def _mean_or_none(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 6) if values else None


def _distribution(values: list[float], *, include_total: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "sample_count": len(values),
        "median": round(float(statistics.median(values)), 6) if values else None,
        "p95": round(float(_nearest_rank(values, 0.95)), 6) if values else None,
    }
    if include_total:
        result["total"] = round(sum(values), 6) if values else 0
    return result


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _json_list_length(value: Any) -> int:
    decoded = _decode_json(value, default=[])
    return len(decoded) if isinstance(decoded, list) else 0


def _assert_source_privacy_safe(source: Mapping[str, Any]) -> None:
    findings: list[tuple[str, str]] = []

    def inspect(value: Any, structural_path: str, *, semantic_context: bool = True) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                child_path = f"{structural_path}.{_safe_path_key(key)}"
                key_token = str(key).casefold()
                inspect(
                    item,
                    child_path,
                    semantic_context=semantic_context and key_token not in NON_SEMANTIC_NESTED_KEYS,
                )
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                inspect(item, f"{structural_path}[{index}]", semantic_context=semantic_context)
            return
        if not semantic_context or not isinstance(value, str):
            return
        for category, pattern in SENSITIVE_PATTERN_MAP.items():
            if pattern.search(value):
                findings.append((category, structural_path))

    for table, fields in SOURCE_PRIVACY_FIELDS.items():
        for index, row in enumerate(source.get(table, [])):
            if not isinstance(row, Mapping):
                continue
            if (
                table == "screens"
                and _truthy(row.get("contains_personal_data"))
                and (
                    int(row.get("privacy_verified") or 0) == 1
                    or str(row.get("evidence_mode") or "") != "metadata_only"
                )
            ):
                findings.append(
                    ("personal_data_attestation", f"$.{table}[{index}].contains_personal_data")
                )
            for field in fields:
                value = row.get(field)
                if value in (None, ""):
                    continue
                path = f"$.{table}[{index}].{field}"
                if field.endswith("_json") and isinstance(value, str):
                    decoded = _decode_json(value, default=value)
                    inspect(decoded, path)
                else:
                    inspect(value, path)
    if not findings:
        return
    unique_findings = sorted(set(findings), key=lambda item: (item[1], item[0]))
    diagnostic = ", ".join(
        f"{category} at {path}" for category, path in unique_findings[:8]
    )
    if len(unique_findings) > 8:
        diagnostic += f", plus {len(unique_findings) - 8} additional structural finding(s)"
    raise ArtifactBuildError(
        "source corpus rejected by privacy preflight; no artifacts were published: " + diagnostic
    )


def _assert_privacy_safe(value: Any, *, location: str, structural_path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_token = str(key).casefold()
            if key_token in FORBIDDEN_OUTPUT_KEYS:
                raise ArtifactBuildError(
                    f"privacy-forbidden output field at {structural_path}.{_safe_path_key(key)} "
                    f"in {location}"
                )
            # Cryptographic digests are opaque structural evidence.  A digest
            # can coincidentally contain a phone-number-shaped digit run, so
            # validate its exact type/format instead of applying PII regexes.
            # The source hash map is generated locally from this run's fixed
            # artifact allowlist; arbitrary nested values are not accepted.
            if key_token == "source_database_sha256":
                if not isinstance(item, Mapping) or not item:
                    raise ArtifactBuildError(
                        f"invalid source hash map at {structural_path}.{_safe_path_key(key)} "
                        f"in {location}"
                    )
                if any(
                    not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None
                    for digest in item.values()
                ):
                    raise ArtifactBuildError(
                        f"invalid source hash value at {structural_path}.{_safe_path_key(key)} "
                        f"in {location}"
                    )
                continue
            if key_token.endswith("_sha256"):
                if not isinstance(item, str) or SHA256_RE.fullmatch(item) is None:
                    raise ArtifactBuildError(
                        f"invalid sha256 value at {structural_path}.{_safe_path_key(key)} "
                        f"in {location}"
                    )
                continue
            if key_token in NON_SEMANTIC_NESTED_KEYS or key_token.endswith("_id"):
                if item is None:
                    continue
                if (
                    not isinstance(item, str)
                    or len(item) > 512
                    or re.fullmatch(r"[A-Za-z0-9_.:@-]+", item) is None
                    or any(
                        SENSITIVE_PATTERN_MAP[category].search(item)
                        for category in (
                            "friendli_key",
                            "bearer_token",
                            "generic_secret",
                        )
                    )
                ):
                    raise ArtifactBuildError(
                        f"invalid structural identifier at "
                        f"{structural_path}.{_safe_path_key(key)} in {location}"
                    )
                continue
            _assert_privacy_safe(
                item,
                location=location,
                structural_path=f"{structural_path}.{_safe_path_key(key)}",
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_privacy_safe(
                item,
                location=location,
                structural_path=f"{structural_path}[{index}]",
            )
        return
    if isinstance(value, str) and any(pattern.search(value) for pattern in SENSITIVE_PATTERNS):
        raise ArtifactBuildError(
            f"sensitive value rejected at {structural_path} in generated artifact: {location}"
        )


def _safe_path_key(value: Any) -> str:
    text = str(value)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", text):
        return text
    return "key_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write_bytes(path, (_canonical_json(payload) + "\n").encode("utf-8"))


def _atomic_write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    encoded = b"".join((_canonical_json(row) + "\n").encode("utf-8") for row in rows)
    _atomic_write_bytes(path, encoded)


def _validate_staged_artifact_set(staged_paths: Mapping[str, Path]) -> None:
    if set(staged_paths) != set(OUTPUT_FILENAMES):
        raise ArtifactBuildError("staged artifact set is incomplete")
    for name in OUTPUT_FILENAMES:
        path = staged_paths[name]
        if not path.is_file():
            raise ArtifactBuildError(f"staged artifact is missing: {name}")
        if name.endswith(".jsonl"):
            for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ArtifactBuildError(
                        f"invalid staged JSONL record at {name}[{index}]"
                    ) from error
                _assert_privacy_safe(
                    payload,
                    location=name,
                    structural_path=f"$[{index}]",
                )
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ArtifactBuildError(f"invalid staged JSON artifact: {name}") from error
        _assert_privacy_safe(payload, location=name)


def _publish_artifact_set(
    *,
    staged_paths: Mapping[str, Path],
    output_paths: Mapping[str, Path],
    overwrite: bool,
    expected_hashes: Mapping[str, str],
) -> None:
    run_directory = next(iter(output_paths.values())).parent
    backup_directory = run_directory / f".function-graph-artifacts.{uuid.uuid4().hex}.backup"
    backup_directory.mkdir(mode=0o700)
    backed_up: list[str] = []
    published: list[str] = []
    preserve_backup_for_recovery = False
    try:
        for name in OUTPUT_FILENAMES:
            output = output_paths[name]
            if not output.exists():
                continue
            if not overwrite:
                raise ArtifactBuildError(f"refusing to replace existing artifact: {name}")
            os.replace(output, backup_directory / name)
            backed_up.append(name)
        for name in OUTPUT_FILENAMES:
            os.replace(staged_paths[name], output_paths[name])
            published.append(name)
        published_hashes = {
            name: _sha256_file(output_paths[name]) for name in OUTPUT_FILENAMES
        }
        if published_hashes != dict(expected_hashes):
            raise ArtifactBuildError(
                "published artifact set failed post-publication integrity verification"
            )
    except Exception:
        rollback_errors: list[str] = []
        for name in reversed(published):
            output = output_paths[name]
            try:
                if output.exists():
                    output.unlink()
            except OSError:
                rollback_errors.append(name)
        for name in reversed(backed_up):
            backup = backup_directory / name
            try:
                if backup.exists():
                    os.replace(backup, output_paths[name])
            except OSError:
                rollback_errors.append(name)
        if rollback_errors:
            preserve_backup_for_recovery = True
            raise ArtifactBuildError(
                "artifact-set publication failed and rollback was incomplete for: "
                + ", ".join(sorted(set(rollback_errors)))
            )
        raise
    finally:
        if not preserve_backup_for_recovery:
            _remove_flat_temporary_directory(backup_directory)


def _remove_flat_temporary_directory(directory: Path) -> None:
    if not directory.exists():
        return
    for child in directory.iterdir():
        if child.is_file():
            child.unlink()
        else:
            raise ArtifactBuildError(
                f"refusing to recursively remove unexpected temporary entry: {child.name}"
            )
    directory.rmdir()


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    # The observation root is already deep on Windows.  Keep the temporary
    # basename short so atomic staging does not cross the legacy MAX_PATH
    # boundary merely because the destination filename is repeated.
    temporary = path.parent / f".tmp-{uuid.uuid4().hex[:12]}"
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--app-manifest", type=Path, default=DEFAULT_APP_MANIFEST)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = build_artifacts(
            args.run_dir,
            repo_root=args.repo_root,
            app_manifest_path=args.app_manifest,
            overwrite=args.force,
        )
    except (ArtifactBuildError, OSError, sqlite3.Error, ValueError) as error:
        result = {"ok": False, "error": str(error)}
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
