from __future__ import annotations

"""Privacy-safe semantic fixtures derived from selected navigation sessions.

The exporter is deliberately narrower than a database dump.  Callers must
select concrete ``navigation_sessions.rowid`` values, the source SQLite file is
opened read-only with ``query_only`` enabled, and only controlled semantic
codes are retained.  Raw accessibility structures, source identifiers,
timestamps, paths, free-form labels, and device metadata never enter the
fixture.

Real-device evidence remains a shadow candidate.  A completed runtime session
is not positive evidence by itself; positive promotion additionally requires an
explicit independent destination annotation supplied by the caller.
"""

import hashlib
import json
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from app.services.real_device_privacy import REDACTED, redact_if_sensitive


SCHEMA_VERSION = 1
ARTIFACT_DIRECTORY_NAME = "navigation-semantic-fixtures"
PHYSICAL_MEASUREMENT_SOURCES = frozenset({"real_device", "real_device_gold"})
TRUSTED_VERIFICATION_METHODS = frozenset(
    {"human_on_device", "independent_device_replay", "independent_test_harness"}
)
ALLOWED_DESTINATION_SEMANTICS = frozenset({"notification_preferences"})
TARGET_DESTINATION_SEMANTICS = {
    "notification.settings": "notification_preferences",
}

# This is an objective-specific, fail-closed correction to the current live
# evidence.  Row 41 ended on the ExitGuide surface and must never be interpreted
# as a successful destination merely because its runtime counters say so.
OBJECTIVE_KNOWN_FALSE_POSITIVE_ROWIDS = frozenset({41})

_REQUIRED_TABLES = frozenset(
    {
        "navigation_sessions",
        "navigation_stage_timings",
        "universal_screens",
        "universal_actions",
        "universal_transitions",
    }
)
_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,159}$")
_SAFE_RISKS = frozenset({"none", "low", "medium", "high", "critical"})
_SAFE_STATUSES = frozenset({"active", "completed", "failed", "stopped", "cancelled"})
_SAFE_DECISION_MODES = frozenset(
    {
        "route_cache",
        "graph_cache",
        "function_graph_exploration",
        "deterministic_fallback",
        "exaone",
    }
)
_SAFE_PHASES = frozenset(
    {
        "observe",
        "explore",
        "recover",
        "destination_reached",
        "safe_stop",
        "loading",
    }
)
_SAFE_OUTCOMES = frozenset(
    {
        "success",
        "failed",
        "no_change",
        "pending",
        "skipped",
        "unknown",
    }
)

_SEMANTIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "notification_preferences",
        (
            "알림설정",
            "알림관리",
            "알림수신설정",
            "푸시설정",
            "notification settings",
            "notification preferences",
            "push settings",
        ),
    ),
    (
        "marketing_notifications",
        ("마케팅알림", "광고성알림", "혜택알림", "marketing notifications"),
    ),
    (
        "settings",
        (
            "환경설정",
            "환경 설정",
            "설정",
            "settings",
            "preferences",
            "setting",
            "gear",
            "cog",
        ),
    ),
    (
        "account_hub",
        (
            "마이배민",
            "마이페이지",
            "내정보",
            "계정관리",
            "프로필",
            "my page",
            "account",
            "profile",
        ),
    ),
    (
        "close_control",
        ("닫기", "팝업닫기", "close", "dismiss", "cancel"),
    ),
    (
        "back_control",
        ("뒤로", "이전", "back", "navigate up"),
    ),
    (
        "experience_survey",
        ("음식주문경험", "주문경험", "어떠셨나요", "survey", "feedback"),
    ),
    (
        "promotion",
        ("프로모션", "이벤트", "할인", "쿠폰", "promotion", "event", "coupon"),
    ),
    (
        "customer_support",
        ("고객센터", "문의하기", "도움말", "customer service", "support", "help"),
    ),
    (
        "subscription_management",
        ("구독관리", "멤버십관리", "구독해지", "subscription", "membership"),
    ),
    (
        "privacy_controls",
        ("개인정보", "정보보호", "privacy"),
    ),
    (
        "loading_indicator",
        ("로딩", "불러오는중", "loading", "progress"),
    ),
    (
        "toggle_control",
        ("스위치", "토글", "switch", "toggle", "checkbox"),
    ),
)


class SemanticFixtureExportError(RuntimeError):
    """Fail-closed error whose message contains no source UI values."""


@dataclass(frozen=True)
class IndependentDestinationAnnotation:
    """Explicit, out-of-band confirmation of one selected session destination."""

    source_session_rowid: int
    target_function: str
    destination_semantic: str
    verification_method: str


@dataclass(frozen=True)
class SemanticFixtureExportResult:
    fixture: dict[str, object]
    output_path: Path
    source_sha256_before: str
    source_sha256_after: str

    @property
    def source_hash_unchanged(self) -> bool:
        return self.source_sha256_before == self.source_sha256_after


@dataclass
class _ProjectionStats:
    values_examined: int = 0
    sensitive_values_dropped: int = 0
    unknown_values_dropped: int = 0
    raw_nodes_examined: int = 0
    projected_nodes: int = 0
    raw_actions_examined: int = 0
    projected_actions: int = 0


def export_navigation_semantic_fixture(
    database_path: Path,
    *,
    session_rowids: Sequence[int],
    output_path: Path,
    false_positive_session_rowids: Sequence[int] = (),
    independent_destination_annotations: Sequence[
        IndependentDestinationAnnotation
    ] = (),
) -> SemanticFixtureExportResult:
    """Build and atomically write one privacy-safe semantic fixture.

    ``session_rowids`` are source query selectors only.  They are intentionally
    absent from the persisted fixture.
    """

    source_path = Path(database_path).expanduser().resolve()
    destination_path = _validated_output_path(output_path)
    selected_rowids = _validated_rowids(session_rowids, label="session")
    declared_false_positives = set(
        _validated_rowids(false_positive_session_rowids, label="false-positive")
    )
    declared_false_positives.update(
        OBJECTIVE_KNOWN_FALSE_POSITIVE_ROWIDS.intersection(selected_rowids)
    )
    if not declared_false_positives.issubset(set(selected_rowids)):
        raise SemanticFixtureExportError(
            "False-positive selectors must be included in the selected sessions"
        )

    source_sha256_before = _sha256_file(source_path)
    with _readonly_connection(source_path) as connection:
        fixture = _build_fixture(
            connection,
            selected_rowids=selected_rowids,
            false_positive_rowids=declared_false_positives,
            annotations=tuple(independent_destination_annotations),
        )
    source_sha256_after = _sha256_file(source_path)
    if source_sha256_before != source_sha256_after:
        raise SemanticFixtureExportError(
            "Source database changed during export; no artifact was written"
        )

    _assert_privacy_contract(fixture)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_name(f".{destination_path.name}.tmp")
    temporary_path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(destination_path)
    return SemanticFixtureExportResult(
        fixture=fixture,
        output_path=destination_path,
        source_sha256_before=source_sha256_before,
        source_sha256_after=source_sha256_after,
    )


def _build_fixture(
    connection: sqlite3.Connection,
    *,
    selected_rowids: tuple[int, ...],
    false_positive_rowids: set[int],
    annotations: tuple[IndependentDestinationAnnotation, ...],
) -> dict[str, object]:
    _require_tables(connection, _REQUIRED_TABLES)
    sessions = _select_sessions(connection, selected_rowids)
    app_keys = {str(row["app_key"]) for row in sessions}
    targets = {str(row["target_function"]) for row in sessions}
    goal_keys = {str(row["goal_key"]) for row in sessions}
    if len(app_keys) != 1 or len(targets) != 1 or len(goal_keys) != 1:
        raise SemanticFixtureExportError(
            "Selected sessions must describe one app and one normalized goal"
        )
    target_function = _validated_target_function(next(iter(targets)))
    target_app_key = next(iter(app_keys))
    destination_semantic = TARGET_DESTINATION_SEMANTICS[target_function]
    annotation_by_rowid = _validated_annotations(
        annotations,
        sessions=sessions,
        false_positive_rowids=false_positive_rowids,
        target_function=target_function,
        destination_semantic=destination_semantic,
    )

    stages_by_rowid = _select_stages(connection, sessions)
    source_screen_order: list[str] = []
    for session in sessions:
        rowid = int(session["source_rowid"])
        for stage in stages_by_rowid[rowid]:
            _append_unique(source_screen_order, str(stage["screen_fingerprint"]))
        _append_unique(source_screen_order, str(session["start_screen_fingerprint"] or ""))
        _append_unique(
            source_screen_order,
            str(session["destination_screen_fingerprint"] or ""),
        )
    source_screen_order = [value for value in source_screen_order if value]
    screen_rows = _select_screens(connection, source_screen_order)
    screen_refs = {
        fingerprint: f"screen-{index:03d}"
        for index, fingerprint in enumerate(source_screen_order, start=1)
    }

    selected_element_counts: dict[tuple[str, str], int] = {}
    for stage_rows in stages_by_rowid.values():
        for stage in stage_rows:
            key = (
                str(stage["screen_fingerprint"]),
                str(stage["selected_element_key"] or ""),
            )
            if key[1]:
                selected_element_counts[key] = selected_element_counts.get(key, 0) + 1

    stats = _ProjectionStats()
    action_rows = _select_actions(connection, source_screen_order)
    transition_action_ids = _select_internal_transition_action_ids(
        connection,
        source_screen_order,
    )
    projected_actions, action_refs, element_action_refs = _project_actions(
        action_rows,
        screen_refs=screen_refs,
        selected_element_counts=selected_element_counts,
        retained_source_action_ids=transition_action_ids,
        stats=stats,
    )
    _attach_attempt_summaries(connection, action_refs, projected_actions)
    projected_screens = _project_screens(
        screen_rows,
        screen_refs=screen_refs,
        target_app_key=target_app_key,
        stats=stats,
    )
    transitions = _project_transitions(
        connection,
        screen_refs=screen_refs,
        action_refs=action_refs,
    )

    session_fixtures: list[dict[str, object]] = []
    for ordinal, session in enumerate(sessions, start=1):
        source_rowid = int(session["source_rowid"])
        if source_rowid in false_positive_rowids:
            destination_assessment = "false_positive_unverified"
        elif source_rowid in annotation_by_rowid:
            destination_assessment = "independently_verified"
        elif bool(session["destination_correct"]):
            destination_assessment = "runtime_claim_unverified"
        else:
            destination_assessment = "not_reached_or_unverified"
        stages: list[dict[str, object]] = []
        for stage in stages_by_rowid[source_rowid]:
            source_screen = str(stage["screen_fingerprint"])
            selected_key = str(stage["selected_element_key"] or "")
            action_ref = element_action_refs.get((source_screen, selected_key))
            stages.append(
                {
                    "ordinal": len(stages) + 1,
                    "screen_ref": screen_refs.get(source_screen),
                    "decision_mode": _safe_controlled_value(
                        stage["decision_mode"], _SAFE_DECISION_MODES
                    ),
                    "phase": _safe_controlled_value(stage["phase"], _SAFE_PHASES),
                    "automation_action": _safe_command(stage["automation_action"]),
                    "selected_action_ref": action_ref,
                }
            )
        session_fixtures.append(
            {
                "session_ref": f"session-{ordinal:03d}",
                "lifecycle": "shadow_candidate",
                "runtime_status": _safe_controlled_value(
                    session["status"], _SAFE_STATUSES
                ),
                "destination_assessment": destination_assessment,
                "eligible_as_positive_evidence": (
                    destination_assessment == "independently_verified"
                ),
                "known_false_positive": source_rowid in false_positive_rowids,
                "stored_verification_claim": _safe_verification_claim(
                    session["verification_level"]
                ),
                "start_screen_ref": screen_refs.get(
                    str(session["start_screen_fingerprint"] or "")
                ),
                "destination_screen_ref": screen_refs.get(
                    str(session["destination_screen_fingerprint"] or "")
                ),
                "action_counts": {
                    "click": _non_negative_count(session["click_count"]),
                    "scroll": _non_negative_count(session["scroll_count"]),
                    "back": _non_negative_count(session["back_count"]),
                    "unsafe": _non_negative_count(session["unsafe_click_count"]),
                    "wrong": _non_negative_count(session["wrong_click_count"]),
                    "revisit": _non_negative_count(session["revisit_count"]),
                },
                "stages": stages,
            }
        )

    annotation_payload = [
        {
            "session_ref": session_fixtures[
                next(
                    index
                    for index, source_session in enumerate(sessions)
                    if int(source_session["source_rowid"]) == rowid
                )
            ]["session_ref"],
            "verification_method": annotation.verification_method,
            "destination_semantic": annotation.destination_semantic,
            "final_action_policy": "user_only",
        }
        for rowid, annotation in sorted(annotation_by_rowid.items())
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_kind": "real_device_semantic_shadow_candidate",
        "privacy": {
            "sanitized": True,
            "source_opened_read_only": True,
            "sqlite_query_only": True,
            "source_hash_verified_unchanged_before_write": True,
            "source_binary_or_xml_artifacts_copied": False,
            "accessibility_structure_persisted": False,
            "free_form_labels_persisted": False,
            "source_identifiers_persisted": False,
            "device_metadata_persisted": False,
            "exact_timestamps_persisted": False,
            "coordinates_persisted": False,
            "projection_counts": {
                "values_examined": stats.values_examined,
                "sensitive_values_dropped": stats.sensitive_values_dropped,
                "unknown_values_dropped": stats.unknown_values_dropped,
                "source_nodes_examined": stats.raw_nodes_examined,
                "projected_nodes": stats.projected_nodes,
                "source_actions_examined": stats.raw_actions_examined,
                "projected_actions": stats.projected_actions,
            },
        },
        "provenance": {
            "source_type": "real_device_runtime_evidence",
            "source_session_count": len(sessions),
            "known_false_positive_count": len(false_positive_rowids),
            "selection_method": "explicit_source_rowids_not_persisted",
            "lifecycle": "shadow_candidate",
        },
        "goal_contract": {
            "target_function": target_function,
            "destination_semantic": destination_semantic,
            "final_action_policy": "user_only",
        },
        "promotion_gate": {
            "explicit_independent_annotation_required": True,
            "positive_promotion_eligible": bool(annotation_payload),
            "annotations": annotation_payload,
        },
        "screens": projected_screens,
        "actions": projected_actions,
        "transitions": transitions,
        "sessions": session_fixtures,
    }


@contextmanager
def _readonly_connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    if not database_path.is_file():
        raise SemanticFixtureExportError("Navigation database does not exist")
    try:
        connection = sqlite3.connect(
            f"{database_path.as_uri()}?mode=ro",
            uri=True,
            timeout=10.0,
        )
    except sqlite3.Error as exc:
        raise SemanticFixtureExportError(
            "Unable to open navigation database read-only"
        ) from exc
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        query_only = connection.execute("PRAGMA query_only").fetchone()
        if query_only is None or int(query_only[0]) != 1:
            raise SemanticFixtureExportError("SQLite query-only mode was not enabled")
        connection.execute("BEGIN")
        yield connection
    except sqlite3.Error as exc:
        raise SemanticFixtureExportError("Unable to read navigation evidence") from exc
    finally:
        connection.close()


def _select_sessions(
    connection: sqlite3.Connection,
    selected_rowids: tuple[int, ...],
) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in selected_rowids)
    rows = connection.execute(
        f"""
        SELECT rowid AS source_rowid, session_id, app_key, goal_key,
               target_function, measurement_source, status,
               start_screen_fingerprint, destination_screen_fingerprint,
               destination_correct, unsafe_click_count, wrong_click_count,
               click_count, scroll_count, back_count, revisit_count,
               verification_level
        FROM navigation_sessions
        WHERE rowid IN ({placeholders})
        ORDER BY rowid
        """,
        selected_rowids,
    ).fetchall()
    returned = {int(row["source_rowid"]) for row in rows}
    if returned != set(selected_rowids):
        raise SemanticFixtureExportError("One or more selected sessions do not exist")
    if any(
        str(row["measurement_source"]) not in PHYSICAL_MEASUREMENT_SOURCES
        for row in rows
    ):
        raise SemanticFixtureExportError(
            "Selected sessions must be physical-device observations"
        )
    return rows


def _select_stages(
    connection: sqlite3.Connection,
    sessions: Sequence[sqlite3.Row],
) -> dict[int, list[sqlite3.Row]]:
    output: dict[int, list[sqlite3.Row]] = {}
    for session in sessions:
        output[int(session["source_rowid"])] = connection.execute(
            """
            SELECT ordinal, screen_fingerprint, decision_mode, phase,
                   automation_action, selected_element_key
            FROM navigation_stage_timings
            WHERE session_id = ?
            ORDER BY ordinal
            """,
            (session["session_id"],),
        ).fetchall()
    return output


def _select_screens(
    connection: sqlite3.Connection,
    source_screen_order: Sequence[str],
) -> dict[str, sqlite3.Row]:
    if not source_screen_order:
        return {}
    placeholders = ",".join("?" for _ in source_screen_order)
    rows = connection.execute(
        f"""
        SELECT screen_fingerprint, app_key, activity_name, title, structure_json
        FROM universal_screens
        WHERE screen_fingerprint IN ({placeholders})
        """,
        tuple(source_screen_order),
    ).fetchall()
    return {str(row["screen_fingerprint"]): row for row in rows}


def _select_actions(
    connection: sqlite3.Connection,
    source_screen_order: Sequence[str],
) -> list[sqlite3.Row]:
    if not source_screen_order:
        return []
    placeholders = ",".join("?" for _ in source_screen_order)
    return connection.execute(
        f"""
        SELECT action_id, screen_fingerprint, element_key, last_element_id,
               label, role, risk_level, seen_count
        FROM universal_actions
        WHERE screen_fingerprint IN ({placeholders})
        ORDER BY screen_fingerprint, seen_count DESC, action_id
        """,
        tuple(source_screen_order),
    ).fetchall()


def _project_screens(
    screen_rows: Mapping[str, sqlite3.Row],
    *,
    screen_refs: Mapping[str, str],
    target_app_key: str,
    stats: _ProjectionStats,
) -> list[dict[str, object]]:
    projected: list[dict[str, object]] = []
    for source_fingerprint, screen_ref in screen_refs.items():
        row = screen_rows.get(source_fingerprint)
        if row is None:
            projected.append(
                {
                    "screen_ref": screen_ref,
                    "app_scope": "unknown",
                    "surface": "unresolved_surface",
                    "semantics": [],
                    "nodes": [],
                    "dropped_node_count": 0,
                }
            )
            continue
        raw_nodes = _parse_structure(row["structure_json"])
        nodes: list[dict[str, object]] = []
        all_semantics: set[str] = set()
        dropped_node_count = 0
        for raw_node in raw_nodes:
            stats.raw_nodes_examined += 1
            semantics, signal_sources = _semantics_from_sources(
                (
                    (raw_node.get("label"), "label"),
                    (raw_node.get("view_id"), "view_id"),
                ),
                stats=stats,
            )
            clickable = bool(raw_node.get("clickable"))
            scrollable = bool(raw_node.get("scrollable"))
            role = _safe_role(raw_node.get("role"))
            if not semantics:
                if scrollable:
                    semantics = ["scroll_container"]
                elif clickable:
                    semantics = ["unresolved_clickable_control"]
                else:
                    dropped_node_count += 1
                    continue
            all_semantics.update(semantics)
            node: dict[str, object] = {
                "node_ref": f"{screen_ref}-node-{len(nodes) + 1:03d}",
                "semantics": semantics,
                "role": role,
                "clickable": clickable,
                "scrollable": scrollable,
            }
            if signal_sources:
                node["semantic_signal_sources"] = signal_sources
            nodes.append(node)
            stats.projected_nodes += 1

        title_semantics, _ = _semantics_from_sources(
            ((row["title"], "title"), (row["activity_name"], "activity_name")),
            stats=stats,
        )
        all_semantics.update(title_semantics)
        app_scope = "target_app" if str(row["app_key"]) == target_app_key else "foreign_app"
        projected.append(
            {
                "screen_ref": screen_ref,
                "app_scope": app_scope,
                "surface": _surface_semantic(all_semantics, app_scope=app_scope),
                "semantics": sorted(all_semantics),
                "nodes": nodes,
                "dropped_node_count": dropped_node_count,
            }
        )
    return projected


def _project_actions(
    action_rows: Sequence[sqlite3.Row],
    *,
    screen_refs: Mapping[str, str],
    selected_element_counts: Mapping[tuple[str, str], int],
    retained_source_action_ids: set[str],
    stats: _ProjectionStats,
) -> tuple[
    list[dict[str, object]],
    dict[str, str],
    dict[tuple[str, str], str],
]:
    projected: list[dict[str, object]] = []
    action_refs: dict[str, str] = {}
    element_action_refs: dict[tuple[str, str], str] = {}
    for row in action_rows:
        stats.raw_actions_examined += 1
        source_screen = str(row["screen_fingerprint"])
        screen_ref = screen_refs.get(source_screen)
        if screen_ref is None:
            continue
        semantics, signal_sources = _semantics_from_sources(
            (
                (row["label"], "label"),
                (row["element_key"], "element_key"),
                (row["last_element_id"], "last_element_id"),
            ),
            stats=stats,
        )
        source_element_key = str(row["element_key"] or "")
        selected_count = selected_element_counts.get(
            (source_screen, source_element_key), 0
        )
        source_action_id = str(row["action_id"])
        if (
            not semantics
            and selected_count == 0
            and source_action_id not in retained_source_action_ids
        ):
            continue
        if not semantics:
            semantics = ["unresolved_clickable_control"]
        action_ref = f"action-{len(projected) + 1:03d}"
        action_refs[source_action_id] = action_ref
        if source_element_key:
            element_action_refs[(source_screen, source_element_key)] = action_ref
        projected.append(
            {
                "action_ref": action_ref,
                "screen_ref": screen_ref,
                "semantics": semantics,
                "role": _safe_role(row["role"]),
                "risk": _safe_risk(row["risk_level"]),
                "observed_count": _non_negative_count(row["seen_count"]),
                "selected_in_session_stage_count": selected_count,
                "semantic_signal_sources": signal_sources,
                "attempt_summary": {
                    "total": 0,
                    "commands": {},
                    "outcomes": {},
                },
            }
        )
        stats.projected_actions += 1
    return projected, action_refs, element_action_refs


def _select_internal_transition_action_ids(
    connection: sqlite3.Connection,
    source_screen_order: Sequence[str],
) -> set[str]:
    """Keep graph edges between selected screens even when their label is absent."""

    if not source_screen_order:
        return set()
    fingerprints = tuple(source_screen_order)
    placeholders = ",".join("?" for _ in fingerprints)
    return {
        str(row[0])
        for row in connection.execute(
            f"""
            SELECT DISTINCT action_id
            FROM universal_transitions
            WHERE from_screen_fingerprint IN ({placeholders})
              AND to_screen_fingerprint IN ({placeholders})
            """,
            fingerprints + fingerprints,
        ).fetchall()
    }


def _attach_attempt_summaries(
    connection: sqlite3.Connection,
    action_refs: Mapping[str, str],
    projected_actions: list[dict[str, object]],
) -> None:
    if not action_refs or not _table_exists(connection, "universal_exploration_attempts"):
        return
    placeholders = ",".join("?" for _ in action_refs)
    rows = connection.execute(
        f"""
        SELECT action_id, command, outcome, SUM(attempt_count) AS total
        FROM universal_exploration_attempts
        WHERE action_id IN ({placeholders})
        GROUP BY action_id, command, outcome
        """,
        tuple(action_refs),
    ).fetchall()
    by_ref = {str(action["action_ref"]): action for action in projected_actions}
    for row in rows:
        action_ref = action_refs.get(str(row["action_id"]))
        if action_ref is None:
            continue
        summary = by_ref[action_ref]["attempt_summary"]
        assert isinstance(summary, dict)
        count = _non_negative_count(row["total"])
        command = _safe_command(row["command"])
        outcome = _safe_controlled_value(row["outcome"], _SAFE_OUTCOMES)
        summary["total"] = int(summary["total"]) + count
        commands = summary["commands"]
        outcomes = summary["outcomes"]
        assert isinstance(commands, dict) and isinstance(outcomes, dict)
        commands[command] = int(commands.get(command, 0)) + count
        outcomes[outcome] = int(outcomes.get(outcome, 0)) + count


def _project_transitions(
    connection: sqlite3.Connection,
    *,
    screen_refs: Mapping[str, str],
    action_refs: Mapping[str, str],
) -> list[dict[str, object]]:
    if not screen_refs:
        return []
    fingerprints = tuple(screen_refs)
    placeholders = ",".join("?" for _ in fingerprints)
    rows = connection.execute(
        f"""
        SELECT from_screen_fingerprint, action_id, to_screen_fingerprint,
               success_count, failure_count
        FROM universal_transitions
        WHERE from_screen_fingerprint IN ({placeholders})
          AND to_screen_fingerprint IN ({placeholders})
        ORDER BY from_screen_fingerprint, action_id, to_screen_fingerprint
        """,
        fingerprints + fingerprints,
    ).fetchall()
    output: list[dict[str, object]] = []
    for row in rows:
        action_ref = action_refs.get(str(row["action_id"]))
        if action_ref is None:
            continue
        output.append(
            {
                "transition_ref": f"transition-{len(output) + 1:03d}",
                "from_screen_ref": screen_refs[str(row["from_screen_fingerprint"])],
                "action_ref": action_ref,
                "to_screen_ref": screen_refs[str(row["to_screen_fingerprint"])],
                "success_count": _non_negative_count(row["success_count"]),
                "failure_count": _non_negative_count(row["failure_count"]),
                "lifecycle": "shadow_candidate",
            }
        )
    return output


def _validated_annotations(
    annotations: Sequence[IndependentDestinationAnnotation],
    *,
    sessions: Sequence[sqlite3.Row],
    false_positive_rowids: set[int],
    target_function: str,
    destination_semantic: str,
) -> dict[int, IndependentDestinationAnnotation]:
    sessions_by_rowid = {int(row["source_rowid"]): row for row in sessions}
    output: dict[int, IndependentDestinationAnnotation] = {}
    for annotation in annotations:
        rowid = _validated_single_rowid(
            annotation.source_session_rowid,
            label="annotation session",
        )
        session = sessions_by_rowid.get(rowid)
        if session is None:
            raise SemanticFixtureExportError(
                "Destination annotation must reference a selected session"
            )
        if rowid in false_positive_rowids:
            raise SemanticFixtureExportError(
                "A known false-positive session cannot receive destination promotion"
            )
        if rowid in output:
            raise SemanticFixtureExportError("Duplicate destination annotation")
        if annotation.target_function != target_function:
            raise SemanticFixtureExportError("Destination annotation target mismatch")
        if annotation.destination_semantic != destination_semantic:
            raise SemanticFixtureExportError("Destination annotation semantic mismatch")
        if annotation.verification_method not in TRUSTED_VERIFICATION_METHODS:
            raise SemanticFixtureExportError(
                "Destination annotation verification method is not independent"
            )
        if str(session["status"]) != "completed" or not bool(
            session["destination_correct"]
        ):
            raise SemanticFixtureExportError(
                "Destination annotation requires a completed destination candidate"
            )
        output[rowid] = annotation
    return output


def _semantics_from_sources(
    sources: Sequence[tuple[object, str]],
    *,
    stats: _ProjectionStats,
) -> tuple[list[str], list[str]]:
    semantics: set[str] = set()
    signal_sources: set[str] = set()
    for value, field_name in sources:
        semantic = _project_semantic(value, field_name=field_name, stats=stats)
        if semantic:
            semantics.add(semantic)
            signal_sources.add(_safe_signal_source(field_name))
    return sorted(semantics), sorted(signal_sources)


def _project_semantic(
    value: object,
    *,
    field_name: str,
    stats: _ProjectionStats,
) -> str | None:
    if value is None or not str(value).strip():
        return None
    stats.values_examined += 1
    sanitized = redact_if_sensitive(value, field_name=field_name, path=field_name)
    if sanitized == REDACTED:
        stats.sensitive_values_dropped += 1
        return None
    normalized = _normalized_match_text(sanitized)
    compact = normalized.replace(" ", "")
    for semantic, aliases in _SEMANTIC_RULES:
        for alias in aliases:
            normalized_alias = _normalized_match_text(alias)
            if normalized_alias in normalized or normalized_alias.replace(" ", "") in compact:
                return semantic
    stats.unknown_values_dropped += 1
    return None


def _normalized_match_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = re.sub(r"[^0-9a-z가-힣]+", " ", text)
    return " ".join(text.split())


def _parse_structure(value: object) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, Mapping)]


def _surface_semantic(semantics: set[str], *, app_scope: str) -> str:
    if app_scope == "foreign_app":
        return "foreign_app_surface"
    if "notification_preferences" in semantics:
        return "notification_preferences_candidate"
    if "close_control" in semantics and ("promotion" in semantics or "experience_survey" in semantics):
        return "blocking_modal_candidate"
    if "experience_survey" in semantics and "settings" in semantics:
        return "account_hub_with_static_card"
    if "account_hub" in semantics:
        return "account_hub_candidate"
    if "loading_indicator" in semantics:
        return "loading_surface"
    return "navigation_surface"


def _safe_role(value: object) -> str:
    normalized = _normalized_match_text(value).replace(" ", "")
    if "switch" in normalized or "checkbox" in normalized or "toggle" in normalized:
        return "toggle"
    if "imagebutton" in normalized or normalized in {"image", "icon"}:
        return "icon"
    if "button" in normalized:
        return "button"
    if "tab" in normalized:
        return "tab"
    if "edittext" in normalized or "input" in normalized:
        return "input"
    if "scroll" in normalized or "list" in normalized or "recycler" in normalized:
        return "scroll_container"
    if "text" in normalized or "label" in normalized:
        return "label"
    return "generic_control"


def _safe_risk(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    return normalized if normalized in _SAFE_RISKS else "unknown"


def _safe_command(value: object) -> str:
    normalized = _normalized_match_text(value).replace(" ", "_")
    if normalized in {"click", "tap", "press"}:
        return "click"
    if normalized.startswith("scroll") or normalized in {"swipe", "page_down", "page_up"}:
        return "scroll"
    if normalized in {"back", "system_back", "navigate_up"}:
        return "back"
    if normalized in {"wait", "observe", "loading"}:
        return "wait"
    if normalized in {"stop", "safe_stop", "finish"}:
        return "stop"
    return "other"


def _safe_signal_source(field_name: str) -> str:
    if field_name in {"view_id", "element_key", "last_element_id"}:
        return "structural_identifier"
    if field_name == "activity_name":
        return "activity_classification"
    if field_name == "title":
        return "screen_title"
    return "human_facing_semantic"


def _safe_controlled_value(value: object, allowed: frozenset[str]) -> str:
    normalized = str(value or "").strip().casefold()
    return normalized if normalized in allowed else "other"


def _safe_verification_claim(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized in {"runtime_inferred", "benchmark_gold", "human_gold", "device_gold"}:
        return normalized
    return "unknown"


def _non_negative_count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _validated_target_function(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized not in TARGET_DESTINATION_SEMANTICS or not _SAFE_CODE.fullmatch(normalized):
        raise SemanticFixtureExportError(
            "Target function is outside the semantic fixture allowlist"
        )
    return normalized


def _validated_rowids(values: Sequence[int], *, label: str) -> tuple[int, ...]:
    if not values:
        if label == "session":
            raise SemanticFixtureExportError("At least one explicit session row selector is required")
        return ()
    output = tuple(_validated_single_rowid(value, label=label) for value in values)
    if len(set(output)) != len(output):
        raise SemanticFixtureExportError(f"Duplicate {label} row selector")
    return tuple(sorted(output))


def _validated_single_rowid(value: object, *, label: str) -> int:
    if isinstance(value, bool):
        raise SemanticFixtureExportError(f"{label.capitalize()} row selector must be positive")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SemanticFixtureExportError(
            f"{label.capitalize()} row selector must be positive"
        ) from exc
    if parsed <= 0:
        raise SemanticFixtureExportError(f"{label.capitalize()} row selector must be positive")
    return parsed


def _validated_output_path(output_path: Path) -> Path:
    path = Path(output_path).expanduser().resolve()
    if path.suffix.casefold() != ".json":
        raise SemanticFixtureExportError("Semantic fixture output must be JSON")
    parts = [part.casefold() for part in path.parts]
    try:
        artifact_index = parts.index(".artifacts")
        fixture_index = parts.index(ARTIFACT_DIRECTORY_NAME.casefold())
    except ValueError as exc:
        raise SemanticFixtureExportError(
            "Semantic fixtures must stay under the ignored artifact directory"
        ) from exc
    if fixture_index != artifact_index + 1:
        raise SemanticFixtureExportError(
            "Semantic fixtures must stay under the ignored artifact directory"
        )
    return path


def _require_tables(
    connection: sqlite3.Connection,
    required: set[str] | frozenset[str],
) -> None:
    available = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if not required.issubset(available):
        raise SemanticFixtureExportError("Navigation database schema is incomplete")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise SemanticFixtureExportError("Navigation database does not exist")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_privacy_contract(fixture: Mapping[str, Any]) -> None:
    forbidden_keys = {
        "session_id",
        "source_session_rowid",
        "screen_fingerprint",
        "element_key",
        "action_id",
        "resource_id",
        "view_id",
        "device_serial",
        "started_at",
        "updated_at",
        "created_at",
        "screenshot_path",
        "accessibility_tree_path",
        "structure_json",
        "label",
        "text",
        "title",
    }

    def walk(value: object, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                normalized_key = str(key).strip().casefold()
                if normalized_key in forbidden_keys or normalized_key.startswith("raw_"):
                    raise SemanticFixtureExportError(
                        "Semantic fixture contains a forbidden source field"
                    )
                walk(child, f"{path}.{normalized_key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
        elif isinstance(value, str):
            finding = redact_if_sensitive(value, field_name=path.rsplit(".", 1)[-1], path=path)
            if finding == REDACTED:
                raise SemanticFixtureExportError(
                    "Semantic fixture failed its post-export privacy scan"
                )

    walk(fixture, "fixture")
