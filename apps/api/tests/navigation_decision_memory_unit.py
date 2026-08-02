from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_decision_memory import (  # noqa: E402
    ALLOWED_ACTIONS,
    NavigationDecisionMemory,
    canonical_json,
    redact_text,
    stable_id,
)


def _load_migration_module():
    path = ROOT / "scripts" / "Migrate-NavigationDecisionDb.py"
    spec = importlib.util.spec_from_file_location("navigation_decision_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_case(
    connection: sqlite3.Connection,
    memory: NavigationDecisionMemory,
    *,
    app_package: str,
    goal_text: str,
    screen_title: str,
    selected_label: str,
    case_suffix: str,
) -> tuple[str, str]:
    candidates = [
        {"element_id": "profile", "label": selected_label, "role": "button", "risk_level": "low"},
        {"element_id": "search", "label": "검색", "role": "button", "risk_level": "low"},
    ]
    state = memory.semantic_screen_state(
        window_title=screen_title,
        activity_name="android.view.View",
        candidates=candidates,
    )
    screen_id = stable_id("screen_", state.semantic_fingerprint)
    connection.execute(
        """
        INSERT OR IGNORE INTO semantic_screens VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            screen_id, state.semantic_fingerprint, state.title, "{}", 0, state.auth_state,
            state.surface_type, canonical_json(state.tokens), case_suffix * 64, "2026-08-02", "2026-08-02",
        ),
    )
    selected_affordance = ""
    for candidate in candidates:
        roles = memory.infer_affordance_roles(candidate["label"])
        affordance_id = stable_id("aff_", screen_id, candidate["element_id"])
        connection.execute(
            """
            INSERT OR IGNORE INTO affordances VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                affordance_id, screen_id, candidate["element_id"], candidate["label"],
                candidate["label"], "", candidate["role"], "", "", "unknown", "low", 0,
                canonical_json(roles), "",
            ),
        )
        if candidate["element_id"] == "profile":
            selected_affordance = affordance_id
    case_id = stable_id("case_", app_package, case_suffix)
    connection.execute(
        """
        INSERT INTO decision_cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            case_id, "account.delete", screen_id, goal_text, "{}", "click", selected_affordance,
            None, "ds_account_delete_v1", app_package, case_suffix, 0, "human_gold", .98,
            "2026-08-02",
        ),
    )
    connection.execute(
        "INSERT INTO transition_outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            stable_id("out_", case_id), case_id, None, "navigated", "observed", 1, 0.0,
            None, None, None, "semantic_signature_only", "advanced", "", "", "2026-08-02",
        ),
    )
    return case_id, selected_affordance


def main() -> None:
    assert ALLOWED_ACTIONS == (
        "click", "scroll", "back", "wait_and_observe", "stop_for_user"
    )
    assert redact_text("me@example.com 010-1234-5678 123456789") == "[email] [phone] [number]"
    migration = _load_migration_module()
    with tempfile.TemporaryDirectory() as temporary:
        database = Path(temporary) / "decision.sqlite"
        connection = sqlite3.connect(database)
        connection.executescript((ROOT / "db" / "navigation_decision_v1.sql").read_text(encoding="utf-8"))
        migration.seed_database(connection, "a" * 64)
        connection.commit()
        writable = NavigationDecisionMemory(database, read_only=False)
        case_a, _ = _seed_case(
            connection, writable, app_package="app.alpha", goal_text="회원 탈퇴",
            screen_title="홈", selected_label="마이페이지", case_suffix="a",
        )
        case_b, selected_b = _seed_case(
            connection, writable, app_package="app.beta", goal_text="계정 삭제",
            screen_title="시작", selected_label="내 계정", case_suffix="b",
        )
        connection.commit()

        memory = NavigationDecisionMemory(database)
        assert memory.normalize_goal("이 앱에서 회원가입하고 싶어").goal_id == "account.signup"
        assert memory.normalize_goal("멤버쉽을 해지해 줘").goal_id == "membership.cancel"
        assert memory.normalize_goal("요금제를 변경하고 싶어").goal_id == "membership.change"

        current_candidates = [
            {"element_id": "current-account", "label": "내 계정", "role": "button", "risk_level": "low"},
            {"element_id": "current-search", "label": "검색", "role": "button", "risk_level": "low"},
        ]
        query = memory.retrieve(
            goal_text="회원 탈퇴",
            window_title="첫 화면",
            activity_name="android.view.View",
            candidates=current_candidates,
            exclude_app_package="app.alpha",
            top_k=5,
        )
        assert query.goal is not None and query.goal.goal_id == "account.delete"
        assert query.evidence and all(item.case_id != case_a for item in query.evidence)
        assert any(item.case_id == case_b for item in query.evidence)
        action, candidate_id, direction, confidence = memory.recommend_action(query)
        assert (action, candidate_id, direction) == ("click", "current-account", None)
        assert confidence > 0.2

        destination = memory.retrieve(
            goal_text="구독 해지",
            window_title="Premium 구독 해지",
            activity_name="android.webkit.WebView",
            candidates=[
                {"element_id": "confirm", "label": "구독 취소 확인", "role": "button", "risk_level": "high"}
            ],
            exclude_app_package="app.unknown",
        )
        assert destination.destination_match >= 0.7
        assert memory.recommend_action(destination)[0] == "stop_for_user"

        # Transport failures must remain separate from an observed navigation
        # outcome. The schema rejects a fabricated next-screen transition.
        try:
            connection.execute(
                "INSERT INTO transition_outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "bad_transport", "missing_case", selected_b, "no_change", "transport_error",
                    0, None, None, None, None, "not_measured", "unknown", "", "", "2026-08-02",
                ),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("invalid transport/navigation conflation was accepted")
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        connection.close()
    print("navigation_decision_memory_unit: ok")


if __name__ == "__main__":
    main()
