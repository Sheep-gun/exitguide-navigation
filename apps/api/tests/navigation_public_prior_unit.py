from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_decision_memory import (  # noqa: E402
    NormalizedGoal,
    SemanticScreenState,
)
from app.services.navigation_public_prior import NavigationPublicPrior  # noqa: E402


TRANSITION_TABLE = """
CREATE TABLE transition (
    transition_id INTEGER PRIMARY KEY,
    transition_key TEXT NOT NULL UNIQUE,
    dataset TEXT NOT NULL,
    knowledge_role TEXT NOT NULL,
    retrieval_weight REAL NOT NULL,
    app_package TEXT NOT NULL,
    goal TEXT NOT NULL,
    before_text TEXT NOT NULL,
    candidate_text TEXT NOT NULL,
    selected_target TEXT NOT NULL,
    selected_action TEXT NOT NULL,
    after_text TEXT NOT NULL,
    outcome_type TEXT NOT NULL,
    progress_label TEXT NOT NULL,
    risk_class TEXT NOT NULL,
    dangerous_final INTEGER NOT NULL
);
"""


def _create_transition_db(path: Path, *, failure: bool = False) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE episode (episode_id TEXT PRIMARY KEY);
        """
        + TRANSITION_TABLE
        + """
        CREATE VIRTUAL TABLE transition_fts USING fts5(
            goal, app_package, before_text, candidate_text, selected_target, after_text,
            content='transition', content_rowid='transition_id'
        );
        """
    )
    connection.executemany(
        "INSERT INTO metadata VALUES (?,?)",
        (
            ("schema_version", "public-navigation-prior.v3"),
            ("includes_simulated_experience", "false"),
        ),
    )
    connection.execute("INSERT INTO episode VALUES ('episode-1')")
    role = "failure_analysis" if failure else "curated_service_experience"
    connection.execute(
        "INSERT INTO transition VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            1,
            "relevant-cancel",
            "fixture",
            role,
            0.95,
            "com.example",
            "Open subscription settings and cancel the premium membership",
            "Account settings with membership management",
            "Manage subscription Cancel membership",
            "Manage subscription",
            "click",
            "Subscription management page",
            "no_change" if failure else "navigated",
            "unchanged" if failure else "advanced",
            "low",
            0,
        ),
    )
    connection.execute(
        "INSERT INTO transition VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            2,
            "dangerous-cancel",
            "fixture",
            role,
            0.95,
            "com.example",
            "Cancel the subscription",
            "Final confirmation",
            "Confirm cancellation",
            "Confirm cancellation",
            "click",
            "Membership cancelled",
            "destination_reached",
            "reached",
            "high",
            1,
        ),
    )
    connection.execute("INSERT INTO transition_fts(transition_fts) VALUES ('rebuild')")
    connection.commit()
    connection.close()


def _create_task_db(
    path: Path,
    *,
    goal: str = "Find subscription billing settings and review cancellation options",
) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE task (
            task_id TEXT PRIMARY KEY,
            source_dataset TEXT NOT NULL,
            source_name TEXT NOT NULL,
            goal TEXT NOT NULL,
            service_categories TEXT NOT NULL,
            role TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE task_fts USING fts5(
            task_id, goal, service_categories, source_name,
            content='task', content_rowid='rowid'
        );
        INSERT INTO metadata VALUES ('schema_version','navigation-task-knowledge-index.v1');
        INSERT INTO task VALUES (
            'task-1','fixture','fixture-source',
            'Find subscription billing settings and review cancellation options',
            'subscription_billing','task_knowledge'
        );
        INSERT INTO task_fts(task_fts) VALUES ('rebuild');
        """
    )
    connection.execute("UPDATE task SET goal=? WHERE task_id='task-1'", (goal,))
    connection.execute("INSERT INTO task_fts(task_fts) VALUES ('rebuild')")
    connection.commit()
    connection.close()


def test_public_prior_is_bounded_advisory_context() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        service = root / "service.sqlite"
        failure = root / "failure.sqlite"
        task = root / "task.sqlite"
        _create_transition_db(service)
        _create_transition_db(failure, failure=True)
        _create_task_db(task)
        prior = NavigationPublicPrior(
            service,
            failure_db_path=failure,
            task_db_path=task,
            max_results=3,
        )
        goal = NormalizedGoal(
            goal_id="membership.cancel",
            family="membership",
            operation="cancel",
            confidence=1.0,
            matched_phrase="멤버십 해지",
            terminal_action_policy="require_user_confirmation",
        )
        screen = SemanticScreenState(
            semantic_fingerprint="screen-1",
            title="계정 설정",
            auth_state="authenticated",
            surface_type="settings",
            navigation_depth=2,
            tokens=("계정", "설정", "멤버십"),
            candidate_payloads=(
                {
                    "candidate_id": "membership",
                    "label": "멤버십 관리",
                    "icon_semantics": "settings",
                    "nearby_text": "구독",
                    "parent_semantics": "계정",
                },
            ),
        )
        evidence = prior.search(
            goal_text="멤버십을 해지하고 싶어",
            normalized_goal=goal,
            screen=screen,
            app_package="com.target",
        )
        assert evidence
        assert any(item.evidence_kind == "service" for item in evidence)
        assert any(item.evidence_kind == "failure" for item in evidence)
        assert any(item.evidence_kind == "task" for item in evidence)
        assert all(item.selected_target != "Confirm cancellation" for item in evidence)
        assert len([item for item in evidence if item.evidence_kind == "service"]) <= 3
        for item in evidence:
            payload = item.prompt_payload()
            assert payload["evidence_class"] == "unverified_public_prior"
            assert payload["runtime_execution_allowed"] is False
            assert payload["canonical_knowledge"] is False

        status = prior.status()
        assert status["service_transitions"] == 2
        assert status["failure_transitions"] == 2
        assert status["task_records"] == 1
        assert status["mode"] == "planner_advisory_only"


def test_public_prior_refuses_simulated_runtime_source() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "simulated.sqlite"
        _create_transition_db(path)
        connection = sqlite3.connect(path)
        connection.execute(
            "UPDATE metadata SET value='true' WHERE key='includes_simulated_experience'"
        )
        connection.commit()
        connection.close()
        try:
            NavigationPublicPrior(path)
        except ValueError as error:
            assert "simulated experience" in str(error)
        else:
            raise AssertionError("simulated public prior must be rejected")


def test_task_category_alone_cannot_inject_irrelevant_context() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        service = root / "service.sqlite"
        task = root / "task.sqlite"
        _create_transition_db(service)
        _create_task_db(
            task,
            goal="Browse personal apartment listings under a monthly price limit",
        )
        prior = NavigationPublicPrior(service, task_db_path=task)
        goal = NormalizedGoal(
            goal_id="membership.cancel",
            family="membership",
            operation="cancel",
            confidence=1.0,
            matched_phrase="cancel membership",
            terminal_action_policy="require_user_confirmation",
        )
        screen = SemanticScreenState(
            semantic_fingerprint="screen-category-gate",
            title="Account settings",
            auth_state="authenticated",
            surface_type="settings",
            navigation_depth=2,
            tokens=("account", "settings"),
            candidate_payloads=(),
        )
        evidence = prior.search(
            goal_text="cancel my membership",
            normalized_goal=goal,
            screen=screen,
        )
        assert all(item.evidence_kind != "task" for item in evidence)


if __name__ == "__main__":
    test_public_prior_is_bounded_advisory_context()
    test_public_prior_refuses_simulated_runtime_source()
    test_task_category_alone_cannot_inject_irrelevant_context()
    print("navigation public prior unit checks passed")
