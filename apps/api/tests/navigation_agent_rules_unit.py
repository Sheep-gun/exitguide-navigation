from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.navigation_contracts import NavigationAction  # noqa: E402
from app.services.navigation_agent_rules import (  # noqa: E402
    NavigationAgentRuleStore,
    write_rule_index,
)
from app.services.navigation_runtime import _build_shadow_safety_context  # noqa: E402


def main() -> None:
    rules_dir = ROOT / "docs" / "agent_rules"
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        index_path = root / "INDEX.json"
        fts_path = root / "rules.sqlite"
        payload = write_rule_index(rules_dir, index_path, fts_path=fts_path)
        assert len(payload["rules"]) == 2
        store = NavigationAgentRuleStore(index_path)
        account_rules = store.consult("account.delete", screen_terms=("계정", "탈퇴하기"))
        assert [rule.rule_id for rule in account_rules] == [
            "safety.account_delete.v1",
            "safety.common.v1",
        ]
        membership_rules = store.consult("membership.cancel")
        assert [rule.rule_id for rule in membership_rules] == ["safety.common.v1"]
        connection = sqlite3.connect(fts_path)
        try:
            hits = connection.execute(
                "SELECT rule_id FROM rule_search WHERE rule_search MATCH '탈퇴'"
            ).fetchall()
        finally:
            connection.close()
        assert hits == [("safety.account_delete.v1",)]
    context = _build_shadow_safety_context(
        action=NavigationAction(name="stop_for_user"),
        plan_stage="review_before_commit",
        planner_provider="python_terminal_boundary",
        confidence=0.94,
        consulted_rule_ids=("safety.account_delete.v1",),
    )
    assert context.boundary is True
    assert context.confirmation_required is True
    assert context.shadow_mode is True
    assert context.consulted_rule_ids == ["safety.account_delete.v1"]
    print("navigation_agent_rules_unit: ok")


if __name__ == "__main__":
    main()
