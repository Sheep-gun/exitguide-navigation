from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "db" / "contracts"
PROFILE_ID = "exitguide.navigation-experience.v1"
LANGUAGE_TAG_PATTERN = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)")
RAW_ELEMENT_PATTERN = re.compile(r"\b(?:an|ocr)_[a-f0-9]{12,}\b", re.IGNORECASE)

CORE_TABLES = {
    "navigation_db_metadata", "goals", "goal_phrases", "goal_relations",
    "destination_signatures", "semantic_screens", "screen_observations",
    "affordances", "decision_cases", "transition_outcomes", "recovery_memories",
    "evidence_records", "evaluation_app_splits",
}
PROFILE_TABLES = {
    "navigation_standard_profiles", "standard_term_mappings", "goal_concept_schemes",
    "goal_standard_concepts", "goal_label_mappings", "goal_relation_mappings",
    "observation_contracts", "experience_episodes", "experience_steps",
    "provenance_agents", "provenance_activities", "evidence_provenance",
}
LEGACY_ROUTE_TABLES = {
    "app_route_examples", "gold_routes", "navigation_routes", "route_rankings",
    "route_performance", "universal_app_function_routes",
}
REWARD_BY_PROGRESS = {
    "reached": 1.0,
    "advanced": 0.5,
    "unchanged": 0.0,
    "regressed": -0.5,
    "unknown": None,
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_contract(name: str) -> dict[str, object]:
    payload = json.loads((CONTRACT_ROOT / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(payload)
    return payload


def _visible_observation_texts(value: str) -> Iterable[str]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return ()
    result: list[str] = []

    def visit(item: object, key: str = "") -> None:
        if isinstance(item, dict):
            for child_key, child_value in item.items():
                visit(child_value, str(child_key))
        elif isinstance(item, list):
            for child in item:
                visit(child, key)
        elif isinstance(item, str) and key in {
            "label", "labels", "window_title", "summary", "text", "content_description"
        }:
            result.append(item)

    visit(payload)
    return result


def _contains_coordinate_key(value: str) -> bool:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return False

    def visit(item: object) -> bool:
        if isinstance(item, dict):
            coordinate_keys = {"bounds", "x", "y", "left", "top", "right", "bottom"}
            if any(str(key).casefold() in coordinate_keys for key in item):
                return True
            return any(visit(child) for child in item.values())
        if isinstance(item, list):
            return any(visit(child) for child in item)
        return False

    return visit(payload)


def _valid_rfc3339(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return "T" in value and (value.endswith("Z") or bool(re.search(r"[+-]\d\d:\d\d$", value)))


def _contract_error_counts(connection: sqlite3.Connection) -> dict[str, int]:
    schemas = {
        "accessibility": _load_contract("android_accessibility_observation.v1.schema.json"),
        "ocr": _load_contract("ocr_observation.v1.schema.json"),
        "vlm": _load_contract("vlm_observation.v1.schema.json"),
    }
    _load_contract("navigation_experience_profile.v1.schema.json")
    validators = {key: Draft202012Validator(value) for key, value in schemas.items()}
    errors = {"accessibility": 0, "ocr": 0, "vlm": 0, "invalid_json": 0}
    rows = connection.execute(
        """
        SELECT so.accessibility_json,so.ocr_json,so.vlm_json,oc.accessibility_profile
        FROM screen_observations AS so
        JOIN observation_contracts AS oc ON oc.observation_id=so.observation_id
        """
    ).fetchall()
    for row in rows:
        for key, column in (
            ("accessibility", "accessibility_json"),
            ("ocr", "ocr_json"),
            ("vlm", "vlm_json"),
        ):
            try:
                payload = json.loads(str(row[column] or "{}"))
            except json.JSONDecodeError:
                errors["invalid_json"] += 1
                continue
            if key == "accessibility" and row["accessibility_profile"] == "not_available":
                continue
            errors[key] += sum(1 for _ in validators[key].iter_errors(payload))
    return errors


def validate(
    database: Path,
    *,
    expected_source_sha256: str,
    expected_human_gold_records: int,
) -> dict[str, object]:
    database = database.resolve()
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    metadata = dict(connection.execute("SELECT key,value FROM navigation_db_metadata"))
    table_names = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    missing_tables = sorted((CORE_TABLES | PROFILE_TABLES) - table_names)
    foreign_key_violations = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    contract_errors = _contract_error_counts(connection) if not missing_tables else {
        "accessibility": -1, "ocr": -1, "vlm": -1, "invalid_json": -1
    }

    bad_language_tags = [
        str(row[0])
        for row in connection.execute(
            """
            SELECT language_tag FROM goal_label_mappings
            UNION SELECT language_tag FROM experience_episodes
            """
        )
        if not LANGUAGE_TAG_PATTERN.fullmatch(str(row[0]))
    ] if not missing_tables else []

    skos_pref_label_violations = int(connection.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT p.goal_id,l.language_tag,
                   SUM(CASE WHEN l.skos_property_uri=
                       'http://www.w3.org/2004/02/skos/core#prefLabel' THEN 1 ELSE 0 END) AS preferred
            FROM goal_phrases AS p
            JOIN goal_label_mappings AS l ON l.phrase_id=p.phrase_id
            WHERE p.phrase_kind IN ('canonical','synonym')
            GROUP BY p.goal_id,l.language_tag
            HAVING preferred <> 1
        )
        """
    ).fetchone()[0])
    unmapped_goal_relations = int(connection.execute(
        """
        SELECT COUNT(*) FROM goal_relations AS r
        LEFT JOIN goal_relation_mappings AS m
          ON m.source_goal_id=r.source_goal_id
         AND m.target_goal_id=r.target_goal_id
         AND m.relation_type=r.relation_type
        WHERE m.source_goal_id IS NULL
        """
    ).fetchone()[0])
    missing_destination_signatures = int(connection.execute(
        """
        SELECT COUNT(*) FROM goals AS g
        LEFT JOIN destination_signatures AS d ON d.goal_id=g.goal_id
        WHERE g.active=1 AND d.signature_id IS NULL
        """
    ).fetchone()[0])

    episode_boundary_violations = int(connection.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT episode_id,SUM(is_first) AS first_count,SUM(is_last) AS last_count
            FROM experience_steps GROUP BY episode_id
            HAVING first_count <> 1 OR last_count <> 1
        )
        """
    ).fetchone()[0])
    episode_link_violations = int(connection.execute(
        """
        SELECT COUNT(*) FROM experience_steps AS x
        JOIN decision_cases AS c ON c.case_id=x.case_id
        JOIN experience_episodes AS e ON e.episode_id=x.episode_id
        WHERE x.step_index<>c.source_step_ordinal
           OR e.source_type<>c.source_type
           OR e.source_record_id<>c.source_record_id
           OR e.goal_id<>c.goal_id
           OR e.source_app_package<>c.source_app_package
        """
    ).fetchone()[0])
    terminal_violations = int(connection.execute(
        """
        SELECT COUNT(*) FROM experience_steps AS x
        JOIN experience_episodes AS e ON e.episode_id=x.episode_id
        WHERE x.is_terminal=1 AND (x.is_last<>1 OR e.end_reason<>'destination_reached')
        """
    ).fetchone()[0])
    reward_violations = 0
    for row in connection.execute(
        """
        SELECT x.reward,o.progress_label FROM experience_steps AS x
        LEFT JOIN transition_outcomes AS o ON o.case_id=x.case_id
        """
    ):
        expected = REWARD_BY_PROGRESS.get(str(row["progress_label"] or "unknown"))
        actual = row["reward"]
        if (expected is None) != (actual is None):
            reward_violations += 1
        elif expected is not None and abs(float(actual) - expected) > 1e-9:
            reward_violations += 1

    duplicate_split_apps = int(connection.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT app_package FROM evaluation_app_splits
            WHERE split_version='app-disjoint-v1'
            GROUP BY app_package HAVING COUNT(DISTINCT split)>1
        )
        """
    ).fetchone()[0])
    cases_without_split = int(connection.execute(
        """
        SELECT COUNT(*) FROM decision_cases AS c
        LEFT JOIN evaluation_app_splits AS s
          ON s.app_package=c.source_app_package AND s.split_version='app-disjoint-v1'
        WHERE s.app_package IS NULL
        """
    ).fetchone()[0])
    candidate_screen_mismatches = int(connection.execute(
        """
        SELECT COUNT(*) FROM decision_cases AS c
        JOIN affordances AS a ON a.affordance_id=c.chosen_affordance_id
        WHERE a.screen_id<>c.screen_id
        """
    ).fetchone()[0])
    dangerous_final_clicks = int(connection.execute(
        """
        SELECT COUNT(*) FROM decision_cases AS c
        JOIN affordances AS a ON a.affordance_id=c.chosen_affordance_id
        WHERE c.chosen_action='click' AND a.dangerous_final=1
        """
    ).fetchone()[0])
    invalid_connectivity = int(connection.execute(
        """
        SELECT COUNT(*) FROM transition_outcomes
        WHERE connectivity_status<>'observed'
          AND (next_screen_id IS NOT NULL OR state_changed IS NOT NULL OR progress_label<>'unknown')
        """
    ).fetchone()[0])

    evidence_without_provenance = int(connection.execute(
        """
        SELECT COUNT(*) FROM evidence_records AS e
        LEFT JOIN evidence_provenance AS p ON p.evidence_id=e.evidence_id
        WHERE p.evidence_id IS NULL
        """
    ).fetchone()[0])
    invalid_provenance_times = sum(
        not _valid_rfc3339(str(row[0]))
        for row in connection.execute("SELECT generated_at FROM evidence_provenance")
    )
    invalid_episode_times = sum(
        not _valid_rfc3339(str(value))
        for row in connection.execute("SELECT started_at,ended_at FROM experience_episodes")
        for value in row
    )

    visible_texts: list[str] = []
    for table, column in (
        ("semantic_screens", "title_normalized"),
        ("affordances", "label"),
        ("affordances", "parent_semantics"),
        ("affordances", "nearby_text"),
        ("decision_cases", "goal_text_normalized"),
    ):
        visible_texts.extend(
            str(row[0] or "") for row in connection.execute(f'SELECT "{column}" FROM "{table}"')
        )
    observation_values = [
        str(value or "")
        for row in connection.execute(
            "SELECT accessibility_json,ocr_json,vlm_json FROM screen_observations"
        )
        for value in row
    ]
    for value in observation_values:
        visible_texts.extend(_visible_observation_texts(value))
    unredacted_email_hits = sum(bool(EMAIL_PATTERN.search(value)) for value in visible_texts)
    unredacted_phone_hits = sum(bool(PHONE_PATTERN.search(value)) for value in visible_texts)
    raw_element_id_hits = sum(bool(RAW_ELEMENT_PATTERN.search(value)) for value in visible_texts)
    raw_coordinate_documents = sum(_contains_coordinate_key(value) for value in observation_values)

    required_standard_names = {"W3C SKOS", "Google RLDS", "Android SDK", "W3C PROV-O", "JSON Schema", "ExitGuide"}
    present_standard_names = {
        str(row[0]) for row in connection.execute("SELECT DISTINCT standard_name FROM standard_term_mappings")
    }
    checks = {
        "sqlite_quick_check": connection.execute("PRAGMA quick_check").fetchone()[0] == "ok",
        "required_tables_present": not missing_tables,
        "foreign_key_violations_zero": foreign_key_violations == 0,
        "schema_version_is_2": int(connection.execute("PRAGMA user_version").fetchone()[0]) == 2 and metadata.get("schema_version") == "2",
        "profile_id_is_v1": metadata.get("standards_profile") == PROFILE_ID,
        "source_sha256_matches": metadata.get("profile_source_sha256") == expected_source_sha256,
        "legacy_route_tables_absent": not (LEGACY_ROUTE_TABLES & table_names),
        "standard_mapping_set_complete": required_standard_names <= present_standard_names,
        "language_tags_valid": not bad_language_tags,
        "skos_concepts_cover_goals": connection.execute("SELECT COUNT(*) FROM goals").fetchone()[0] == connection.execute("SELECT COUNT(*) FROM goal_standard_concepts").fetchone()[0],
        "skos_labels_cover_phrases": connection.execute("SELECT COUNT(*) FROM goal_phrases").fetchone()[0] == connection.execute("SELECT COUNT(*) FROM goal_label_mappings").fetchone()[0],
        "skos_one_pref_label_per_goal_language": skos_pref_label_violations == 0,
        "goal_relations_mapped": unmapped_goal_relations == 0,
        "active_goals_have_destination_signature": missing_destination_signatures == 0,
        "observation_contracts_cover_observations": connection.execute("SELECT COUNT(*) FROM screen_observations").fetchone()[0] == connection.execute("SELECT COUNT(*) FROM observation_contracts").fetchone()[0],
        "observation_payloads_match_json_schema": sum(contract_errors.values()) == 0,
        "rlds_steps_cover_decision_cases": connection.execute("SELECT COUNT(*) FROM decision_cases").fetchone()[0] == connection.execute("SELECT COUNT(*) FROM experience_steps").fetchone()[0],
        "rlds_episode_boundaries_valid": episode_boundary_violations == 0,
        "rlds_episode_links_valid": episode_link_violations == 0,
        "rlds_terminal_semantics_valid": terminal_violations == 0,
        "rlds_rewards_match_progress": reward_violations == 0,
        "app_split_has_no_leak": duplicate_split_apps == 0 and cases_without_split == 0,
        "chosen_candidates_belong_to_current_screen": candidate_screen_mismatches == 0,
        "connectivity_not_conflated_with_navigation": invalid_connectivity == 0,
        "dangerous_final_clicks_zero": dangerous_final_clicks == 0,
        "prov_covers_all_evidence": evidence_without_provenance == 0,
        "profile_timestamps_are_rfc3339": invalid_provenance_times == 0 and invalid_episode_times == 0,
        "unredacted_email_hits_zero": unredacted_email_hits == 0,
        "unredacted_phone_hits_zero": unredacted_phone_hits == 0,
        "raw_element_ids_absent_from_visible_text": raw_element_id_hits == 0,
        "raw_coordinates_absent": raw_coordinate_documents == 0,
    }

    count_tables = (
        "goals", "goal_phrases", "goal_relations", "destination_signatures",
        "semantic_screens", "screen_observations", "affordances", "decision_cases",
        "transition_outcomes", "recovery_memories", "evidence_records",
        "evaluation_app_splits", "experience_episodes", "experience_steps",
        "provenance_agents", "provenance_activities", "evidence_provenance",
    )
    counts = {
        table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        for table in count_tables
    }
    source_counts = {
        str(row[0]): {"episodes": int(row[1]), "steps": int(row[2])}
        for row in connection.execute(
            """
            SELECT e.source_type,COUNT(DISTINCT e.episode_id),COUNT(x.case_id)
            FROM experience_episodes AS e
            LEFT JOIN experience_steps AS x ON x.episode_id=e.episode_id
            GROUP BY e.source_type ORDER BY e.source_type
            """
        )
    }
    goal_coverage = {
        str(row[0]): {"episodes": int(row[1]), "steps": int(row[2]), "distinct_apps": int(row[3])}
        for row in connection.execute(
            """
            SELECT e.goal_id,COUNT(DISTINCT e.episode_id),COUNT(x.case_id),
                   COUNT(DISTINCT e.source_app_package)
            FROM experience_episodes AS e
            LEFT JOIN experience_steps AS x ON x.episode_id=e.episode_id
            GROUP BY e.goal_id ORDER BY e.goal_id
            """
        )
    }
    human_gold_records = int(source_counts.get("human_gold", {}).get("episodes", 0))
    vlm_observations = int(connection.execute(
        "SELECT COUNT(*) FROM screen_observations WHERE vlm_json NOT IN ('{}','null','')"
    ).fetchone()[0])
    warnings: list[str] = []
    if human_gold_records != expected_human_gold_records:
        warnings.append(
            f"expected Human Gold inventory is {expected_human_gold_records}, but the current decision DB contains "
            f"{human_gold_records} in-scope Human Gold episodes; verify that the remainder is explicitly out of scope"
        )
    for goal_id in sorted(set(row[0] for row in connection.execute("SELECT goal_id FROM goals WHERE active=1"))):
        coverage = goal_coverage.get(str(goal_id), {"episodes": 0, "steps": 0, "distinct_apps": 0})
        if int(coverage["episodes"]) == 0:
            warnings.append(f"{goal_id} has no verified decision episode")
        elif int(coverage["distinct_apps"]) < 2:
            warnings.append(f"{goal_id} has fewer than two source apps and is not generalization-ready")
    if vlm_observations == 0:
        warnings.append("current migrated screens have no VLM observations; Accessibility/OCR only")

    connection.close()
    return {
        "profile_id": PROFILE_ID,
        "schema_version": 2,
        "validation_scope": "standards-profile-structure-migration-and-data-quality",
        "database": {"path": str(database), "bytes": database.stat().st_size, "sha256": file_sha256(database)},
        "checks": checks,
        "passed": all(checks.values()),
        "counts": counts,
        "source_coverage": source_counts,
        "goal_coverage": goal_coverage,
        "contract_errors": contract_errors,
        "human_gold_inventory": {"expected": expected_human_gold_records, "usable_in_scope": human_gold_records},
        "warnings": warnings,
        "readiness_conclusion": (
            "schema_ready_data_not_generalization_ready"
            if all(checks.values()) and warnings else
            "schema_ready_for_offline_retrieval" if all(checks.values()) else
            "schema_or_data_integrity_failed"
        ),
        "not_evaluated": [
            "first_action_accuracy", "next_action_accuracy", "destination_arrival_rate",
            "recovery_success_rate", "unseen-app success rate", "planner-model quality",
        ],
        "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def render_markdown(report: dict[str, object]) -> str:
    counts = report["counts"]
    assert isinstance(counts, dict)
    goal_coverage = report["goal_coverage"]
    assert isinstance(goal_coverage, dict)
    inventory = report["human_gold_inventory"]
    assert isinstance(inventory, dict)
    warnings = report["warnings"]
    assert isinstance(warnings, list)
    check_lines = [
        f"- {'PASS' if passed else 'FAIL'}: `{name}`"
        for name, passed in dict(report["checks"]).items()
    ]
    goal_lines = [
        f"| `{goal_id}` | {value['episodes']} | {value['steps']} | {value['distinct_apps']} |"
        for goal_id, value in goal_coverage.items()
    ]
    warning_lines = [f"- {warning}" for warning in warnings] or ["- 없음"]
    return "\n".join([
        "# Navigation DB 표준화·품질 보고서",
        "",
        f"- 검증 시각: `{report['validated_at']}`",
        f"- 결론: **{report['readiness_conclusion']}**",
        f"- 구조 검증: **{'통과' if report['passed'] else '실패'}**",
        f"- DB 크기: {report['database']['bytes']:,} bytes",
        "",
        "## 핵심 수량",
        "",
        f"- 목표: {counts['goals']}",
        f"- 화면 / 후보: {counts['semantic_screens']} / {counts['affordances']}",
        f"- Episode / Step: {counts['experience_episodes']} / {counts['experience_steps']}",
        f"- 전이 / 복구: {counts['transition_outcomes']} / {counts['recovery_memories']}",
        f"- Evidence / PROV 매핑: {counts['evidence_records']} / {counts['evidence_provenance']}",
        f"- Human Gold: 보유 주장 {inventory['expected']}개 중 현재 범위에서 사용 가능한 episode {inventory['usable_in_scope']}개",
        "",
        "## 목표별 범위",
        "",
        "| goal_id | episodes | steps | apps |",
        "|---|---:|---:|---:|",
        *goal_lines,
        "",
        "## 자동 검증",
        "",
        *check_lines,
        "",
        "## 경고",
        "",
        *warning_lines,
        "",
        "## 냉정한 결론",
        "",
        "표준화 구조와 무손실 변환 여부는 검증했지만 Navigation 성공률은 아직 검증하지 않았다. "
        "현재 데이터만으로 범용 성능이 충분하다고 결론 내릴 수 없으며, 정적 데이터를 추가하기 전에 "
        "앱 완전 분리 오프라인 A/B를 수행해야 한다.",
        "",
    ])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate ExitGuide Navigation Experience Profile v1")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--expected-human-gold-records", type=int, default=21)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not re.fullmatch(r"[a-f0-9]{64}", args.expected_source_sha256):
        raise ValueError("--expected-source-sha256 must be a lowercase SHA-256")
    report = validate(
        args.database,
        expected_source_sha256=args.expected_source_sha256,
        expected_human_gold_records=args.expected_human_gold_records,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
