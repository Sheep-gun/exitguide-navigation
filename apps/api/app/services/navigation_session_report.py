from __future__ import annotations

"""Privacy-safe, read-only reporting for one real-device EG session.

The report deliberately exposes only counters, timings, lifecycle categories,
and opaque hashes.  It never returns goal text, screen fingerprints, element
keys, labels, raw accessibility data, or route steps.
"""

import hashlib
import math
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


REPORT_VERSION = 1
PHYSICAL_MEASUREMENT_SOURCES = frozenset({"real_device", "real_device_gold"})
TRUSTED_VERIFICATION_LEVELS = frozenset(
    {"benchmark_gold", "human_gold", "device_gold"}
)
KNOWN_DECISION_MODES = (
    "route_cache",
    "graph_cache",
    "function_graph_exploration",
    "deterministic_fallback",
    "exaone",
    "other",
)
REQUIRED_TABLES = frozenset(
    {
        "app_version_signatures",
        "navigation_sessions",
        "navigation_stage_timings",
        "universal_apps",
        "universal_routes",
    }
)
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
SAFE_CODE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,159}$")
SAFE_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+()-]{0,79}$")
SAFE_LOCALE_RE = re.compile(r"^[A-Za-z]{2,8}(?:[-_][A-Za-z0-9]{2,8}){0,2}$")


class NavigationSessionReportError(RuntimeError):
    """A caller-correctable error with a privacy-safe message."""


def capture_navigation_session_baseline(database_path: Path) -> int:
    """Return the latest ``navigation_sessions.rowid`` without writing.

    Capture this immediately before starting an EG test.  A later report uses
    it to exclude every session that existed before the test began.
    """

    with _readonly_connection(database_path) as connection:
        _require_tables(connection, {"navigation_sessions"})
        return int(
            connection.execute(
                "SELECT COALESCE(MAX(rowid), 0) FROM navigation_sessions"
            ).fetchone()[0]
        )


def build_navigation_session_report(
    database_path: Path,
    *,
    baseline_rowid: int,
    app_package: str,
    session_id: str | None = None,
) -> dict[str, object]:
    """Build a sanitized report for exactly one post-baseline physical run.

    When more than one matching session exists, ``session_id`` is required so
    measurements from separate tests cannot be silently combined.
    """

    baseline_rowid = _validated_baseline(baseline_rowid)
    app_package = _validated_package(app_package)
    session_id = _validated_session_id(session_id)

    with _readonly_connection(database_path) as connection:
        _require_tables(connection, REQUIRED_TABLES)
        session = _select_session(
            connection,
            baseline_rowid=baseline_rowid,
            app_package=app_package,
            session_id=session_id,
        )
        stages = connection.execute(
            """
            SELECT ordinal, screen_fingerprint, decision_mode, phase,
                   automation_action, server_total_ms, external_wait_ms,
                   stage_total_ms
            FROM navigation_stage_timings
            WHERE session_id = ?
            ORDER BY ordinal
            """,
            (session["session_id"],),
        ).fetchall()
        step_outcomes = _session_step_outcomes(connection, str(session["session_id"]))
        new_route_summary = _new_shadow_route_summary(
            connection,
            app_package=app_package,
            session=session,
        )

    mode_counts = _decision_mode_counts(stages)
    destination_correct = bool(session["destination_correct"])
    verification_level = _safe_verification(session["verification_level"])
    loop_proxies = _loop_proxies(
        stages,
        step_outcomes,
        destination_independently_verified=(
            destination_correct and verification_level in TRUSTED_VERIFICATION_LEVELS
        ),
    )
    stage_total_ms = sum(_duration(row["stage_total_ms"]) for row in stages)
    external_wait_ms = sum(_duration(row["external_wait_ms"]) for row in stages)
    server_total_ms = sum(_duration(row["server_total_ms"]) for row in stages)
    stored_total = _optional_duration(session["time_to_destination_ms"])
    stored_controllable = _optional_duration(session["controllable_time_ms"])
    total_ms = stage_total_ms if stored_total is None else stored_total
    controllable_ms = (
        max(0.0, stage_total_ms - external_wait_ms)
        if stored_controllable is None
        else stored_controllable
    )

    status = _safe_status(session["status"])
    destination_reached = bool(
        destination_correct
        or session["destination_confirmed_at"]
        or session["destination_screen_fingerprint"]
        or any(str(row["phase"]) == "destination_reached" for row in stages)
    )
    failure_or_stop_reason = _failure_or_stop_reason(session, stages)
    wrong_guidance_count = _count(session["wrong_guidance_count"])
    wrong_click_count = _count(session["wrong_click_count"])
    unsafe_action_count = _count(session["unsafe_click_count"])
    session_safety_passed = bool(
        session["safe_stop"]
        and unsafe_action_count == 0
        and wrong_click_count == 0
        and wrong_guidance_count == 0
    )

    route_cache_used = mode_counts["route_cache"] > 0
    graph_cache_used = mode_counts["graph_cache"] > 0
    exploration_used = mode_counts["function_graph_exploration"] > 0
    deterministic_fallback_used = mode_counts["deterministic_fallback"] > 0
    model_fallback_used = mode_counts["exaone"] > 0
    existing_graph_used = route_cache_used or graph_cache_used
    dynamic_fallback_used = (
        exploration_used or deterministic_fallback_used or model_fallback_used
    )

    return {
        "report_version": REPORT_VERSION,
        "privacy": {
            "sanitized": True,
            "raw_ui_included": False,
            "goal_text_included": False,
            "screen_fingerprints_included": False,
        },
        "selection": {
            "baseline_navigation_session_rowid": baseline_rowid,
            "selected_navigation_session_rowid": int(session["session_rowid"]),
            "session_ref": _opaque_ref("session", str(session["session_id"])),
            "app_package": app_package,
            "app_version": _safe_version(session["app_version"]),
            "locale": _safe_locale(session["locale"]),
            "physical_measurement_source": str(session["measurement_source"]),
        },
        "goal": {
            "target_function": _safe_code(session["target_function"]),
        },
        "outcome": {
            "status": status,
            "success": status == "completed" and destination_correct,
            "destination_reached": destination_reached,
            "destination_correct": destination_correct,
            "destination_verification_level": verification_level,
            "destination_independently_verified": (
                verification_level in TRUSTED_VERIFICATION_LEVELS
            ),
            "safe_stop": bool(session["safe_stop"]),
            "session_safety_passed": session_safety_passed,
            "failure_or_stop_reason": failure_or_stop_reason,
        },
        "timing_ms": {
            "total": round(total_ms, 3),
            "total_source": (
                "session_finalized_elapsed" if stored_total is not None else "stage_sum"
            ),
            "controllable": round(controllable_ms, 3),
            "external_wait": round(external_wait_ms, 3),
            "server_total": round(server_total_ms, 3),
            "stage_sum": round(stage_total_ms, 3),
        },
        "actions": {
            "stage_count": len(stages),
            "click_count": _count(session["click_count"]),
            "scroll_count": _count(session["scroll_count"]),
            "back_count": _count(session["back_count"]),
            "revisit_count": _count(session["revisit_count"]),
            "recovery_count": _count(session["recovery_count"]),
            "wrong_guidance_count": wrong_guidance_count,
            "unsafe_action_count": unsafe_action_count,
        },
        "graph_usage": {
            "decision_mode_counts": mode_counts,
            "existing_approved_route_reused": bool(session["route_reused"])
            or route_cache_used,
            "graph_cache_used": graph_cache_used,
            "function_graph_exploration_used": exploration_used,
            "deterministic_fallback_used": deterministic_fallback_used,
            "model_fallback_used": model_fallback_used,
            "dynamic_fallback_used": dynamic_fallback_used,
            "mixed_existing_graph_and_dynamic_fallback": (
                existing_graph_used and dynamic_fallback_used
            ),
        },
        "repeat_no_change_proxies": loop_proxies,
        "candidate_route": new_route_summary,
    }


@contextmanager
def _readonly_connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise NavigationSessionReportError("Navigation database does not exist")
    try:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro",
            uri=True,
            timeout=10.0,
        )
    except sqlite3.Error as exc:
        raise NavigationSessionReportError("Unable to open navigation database read-only") from exc
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("BEGIN")
        yield connection
    except sqlite3.Error as exc:
        raise NavigationSessionReportError("Unable to read navigation report data") from exc
    finally:
        connection.close()


def _require_tables(connection: sqlite3.Connection, required: set[str] | frozenset[str]) -> None:
    available = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if not required.issubset(available):
        raise NavigationSessionReportError("Navigation database schema is incomplete")


def _select_session(
    connection: sqlite3.Connection,
    *,
    baseline_rowid: int,
    app_package: str,
    session_id: str | None,
) -> sqlite3.Row:
    filters = [
        "session.rowid > ?",
        "signature.app_package = ?",
        "session.measurement_source IN ('real_device', 'real_device_gold')",
    ]
    parameters: list[object] = [baseline_rowid, app_package]
    if session_id is not None:
        filters.append("session.session_id = ?")
        parameters.append(session_id)
    rows = connection.execute(
        f"""
        SELECT session.rowid AS session_rowid, session.*,
               signature.app_package, signature.app_version, signature.locale
        FROM navigation_sessions AS session
        JOIN app_version_signatures AS signature
          ON signature.version_signature = session.version_signature
        WHERE {' AND '.join(filters)}
        ORDER BY session.rowid
        """,
        parameters,
    ).fetchall()
    if not rows:
        raise NavigationSessionReportError(
            "No matching post-baseline physical navigation session was found"
        )
    if len(rows) > 1:
        raise NavigationSessionReportError(
            "Multiple matching sessions were found; provide an exact session id"
        )
    return rows[0]


def _session_step_outcomes(
    connection: sqlite3.Connection,
    session_id: str,
) -> list[str]:
    table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'universal_session_steps'"
    ).fetchone()
    if table_exists is None:
        return []
    return [
        str(row[0])
        for row in connection.execute(
            "SELECT outcome FROM universal_session_steps WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    ]


def _new_shadow_route_summary(
    connection: sqlite3.Connection,
    *,
    app_package: str,
    session: Mapping[str, Any],
) -> dict[str, object]:
    rows = connection.execute(
        """
        SELECT route.route_id, route.status, route.provisional
        FROM universal_routes AS route
        JOIN universal_apps AS app ON app.app_key = route.app_key
        WHERE app.app_package = ?
          AND route.app_key = ?
          AND route.goal_key = ?
          AND route.target_function = ?
          AND route.first_seen_at >= ?
          AND route.first_seen_at <= ?
        ORDER BY route.first_seen_at, route.rowid
        """,
        (
            app_package,
            session["app_key"],
            session["goal_key"],
            session["target_function"],
            session["started_at"],
            session["updated_at"],
        ),
    ).fetchall()
    candidate_rows = [
        row
        for row in rows
        if str(row["status"]) == "shadow" and bool(row["provisional"])
    ]
    session_route_id = str(session["route_id"] or "")
    session_route_candidate = any(
        str(row["route_id"]) == session_route_id for row in candidate_rows
    )
    return {
        "new_route_count": len(rows),
        "new_shadow_candidate_appeared": bool(candidate_rows),
        "new_shadow_candidate_count": len(candidate_rows),
        "unexpected_non_candidate_route_count": len(rows) - len(candidate_rows),
        "session_route_is_new_shadow_candidate": session_route_candidate,
        "candidate_only_not_auto_promoted": (
            None if not rows else len(candidate_rows) == len(rows)
        ),
    }


def _decision_mode_counts(stages: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {mode: 0 for mode in KNOWN_DECISION_MODES}
    for row in stages:
        mode = str(row["decision_mode"])
        counts[mode if mode in counts and mode != "other" else "other"] += 1
    return counts


def _loop_proxies(
    stages: Sequence[Mapping[str, Any]],
    step_outcomes: Sequence[str],
    *,
    destination_independently_verified: bool,
) -> dict[str, object]:
    seen_screens: set[str] = set()
    repeated_screen_stage_count = 0
    consecutive_no_change_count = 0
    scroll_no_change_count = 0
    longest_scroll_run = 0
    current_scroll_run = 0
    scroll_repeated_screen_count = 0

    for index, stage in enumerate(stages):
        fingerprint = str(stage["screen_fingerprint"])
        fingerprint_repeated = fingerprint in seen_screens
        if fingerprint_repeated:
            repeated_screen_stage_count += 1
        seen_screens.add(fingerprint)

        action = str(stage["automation_action"])
        if action == "scroll_forward":
            current_scroll_run += 1
            longest_scroll_run = max(longest_scroll_run, current_scroll_run)
        else:
            current_scroll_run = 0

        if index == 0:
            continue
        previous = stages[index - 1]
        previous_action = str(previous["automation_action"])
        if previous_action == "scroll_forward" and fingerprint_repeated:
            scroll_repeated_screen_count += 1
        if (
            previous_action in {"click", "scroll_forward", "back"}
            and str(previous["screen_fingerprint"]) == fingerprint
        ):
            consecutive_no_change_count += 1
            if previous_action == "scroll_forward":
                scroll_no_change_count += 1

    recorded_no_change_count = sum(outcome == "no_change" for outcome in step_outcomes)
    recorded_failed_transition_count = sum(outcome == "failed" for outcome in step_outcomes)
    repeat_or_no_change = any(
        (
            repeated_screen_stage_count,
            consecutive_no_change_count,
            recorded_no_change_count,
            recorded_failed_transition_count,
        )
    )
    verified_destination_after_scroll = bool(
        destination_independently_verified
        and len(stages) >= 2
        and str(stages[-1]["phase"]) == "destination_reached"
        and str(stages[-2]["automation_action"]) == "scroll_forward"
    )
    progressing_scroll_run_reached_destination = bool(
        verified_destination_after_scroll
        and scroll_no_change_count == 0
        and scroll_repeated_screen_count == 0
    )
    return {
        "repeated_screen_stage_count": repeated_screen_stage_count,
        "consecutive_no_change_proxy_count": consecutive_no_change_count,
        "recorded_no_change_transition_count": recorded_no_change_count,
        "recorded_failed_transition_count": recorded_failed_transition_count,
        "scroll_no_change_proxy_count": scroll_no_change_count,
        "longest_consecutive_scroll_run": longest_scroll_run,
        "repeat_or_no_change_detected": repeat_or_no_change,
        "possible_infinite_scroll": (
            longest_scroll_run >= 3
            and not progressing_scroll_run_reached_destination
        ),
    }


def _failure_or_stop_reason(
    session: Mapping[str, Any],
    stages: Sequence[Mapping[str, Any]],
) -> str | None:
    failure = str(session["failure_type"] or "").strip().lower()
    if failure:
        return _safe_code(failure)
    status = _safe_status(session["status"])
    if status == "active":
        return "in_progress"
    if status == "failed":
        return "unspecified_failure"
    if status == "completed":
        return None
    if bool(session["safe_stop"]):
        return "safe_stop"
    if stages and (
        str(stages[-1]["phase"]) == "stopped"
        or str(stages[-1]["automation_action"]) == "stop"
    ):
        return "stopped"
    return None


def _validated_baseline(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise NavigationSessionReportError("Baseline rowid must be a non-negative integer")
    return value


def _validated_package(value: str) -> str:
    value = str(value).strip()
    if len(value) > 240 or not PACKAGE_RE.fullmatch(value):
        raise NavigationSessionReportError("App package is invalid")
    return value


def _validated_session_id(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value or len(value) > 120 or "\x00" in value:
        raise NavigationSessionReportError("Session id is invalid")
    return value


def _safe_code(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if SAFE_CODE_RE.fullmatch(candidate) else "redacted"


def _safe_status(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in {"active", "completed", "failed"} else "unknown"


def _safe_verification(value: Any) -> str:
    candidate = str(value or "runtime_inferred").strip().lower()
    allowed = TRUSTED_VERIFICATION_LEVELS | {"runtime_inferred"}
    return candidate if candidate in allowed else "unrecognized"


def _safe_version(value: Any) -> str:
    candidate = str(value or "").strip()
    return candidate if SAFE_VERSION_RE.fullmatch(candidate) else "redacted"


def _safe_locale(value: Any) -> str:
    candidate = str(value or "").strip()
    return candidate if SAFE_LOCALE_RE.fullmatch(candidate) else "redacted"


def _opaque_ref(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _duration(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, number)


def _optional_duration(value: Any) -> float | None:
    if value is None:
        return None
    return _duration(value)
