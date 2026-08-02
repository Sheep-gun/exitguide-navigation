from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from app.services.navigation_gold_retrieval import HumanGoldEvidenceIndex


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        database = Path(temporary_directory) / "gold.sqlite"
        _fixture(database)
        index = HumanGoldEvidenceIndex(database)
        assert index.rebuild() == 3
        rows = index.search(
            goal_text="쿠팡 와우 멤버십을 해지하고 싶어",
            target_function="subscription.cancel.entry",
            app_package="com.coupang.mobile",
            app_version="8.1",
            locale="ko-KR",
            screen_text="마이쿠팡",
            candidate_labels=["주문목록", "설정", "고객센터"],
            top_k=3,
        )
        assert rows
        assert rows[0].source_recording_id == "coupang-cancel"
        assert rows[0].chosen_label == "설정"
        assert rows[0].prompt_payload()["never_replay_as_macro"] is True

        leave_one_route_out = index.search(
            goal_text="쿠팡 와우 멤버십을 해지하고 싶어",
            target_function="subscription.cancel.entry",
            app_package="com.coupang.mobile",
            app_version="8.1",
            locale="ko-KR",
            screen_text="마이쿠팡",
            candidate_labels=["설정"],
            exclude_recording_ids=["coupang-cancel"],
            top_k=5,
        )
        assert all(row.source_recording_id != "coupang-cancel" for row in leave_one_route_out)
        leave_one_app_out = index.search(
            goal_text="멤버십 해지",
            target_function="subscription.cancel.entry",
            app_package="com.coupang.mobile",
            app_version="8.1",
            locale="ko-KR",
            screen_text="설정",
            candidate_labels=["멤버십"],
            exclude_app_packages=["com.coupang.mobile"],
            top_k=5,
        )
        assert leave_one_app_out
        assert all(row.app_package != "com.coupang.mobile" for row in leave_one_app_out)
    print("human gold evidence retrieval checks ok")


def _fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE navigation_training_examples (
              example_id TEXT PRIMARY KEY, source_recording_id TEXT, app_package TEXT,
              app_version TEXT, locale TEXT, goal_text TEXT, target_function TEXT,
              screen_fingerprint TEXT, screen_context_json TEXT, candidates_json TEXT,
              correct_candidate_json TEXT, next_screen_fingerprint TEXT,
              provenance TEXT, verification_level TEXT
            );
            """
        )
        rows = [
            (
                "c1", "coupang-cancel", "com.coupang.mobile", "8.1", "ko-KR",
                "쿠팡 와우 멤버십 해지", "subscription.cancel.entry", "screen-c",
                {"title": "마이쿠팡"}, [{"label": "설정"}],
                {"label": "설정", "element_key": "settings"}, "screen-c2",
            ),
            (
                "n1", "netflix-cancel", "com.netflix.mediaclient", "9.0", "ko-KR",
                "넷플릭스 멤버십 해지", "subscription.cancel.entry", "screen-n",
                {"title": "계정"}, [{"label": "멤버십 관리"}],
                {"label": "멤버십 관리", "element_key": "membership"}, "screen-n2",
            ),
            (
                "x1", "x-notification", "com.twitter.android", "12", "ko-KR",
                "X 알림 끄기", "notification.settings", "screen-x",
                {"title": "설정 및 개인정보"}, [{"label": "알림"}],
                {"label": "알림", "element_key": "notifications"}, "screen-x2",
            ),
        ]
        for row in rows:
            connection.execute(
                """
                INSERT INTO navigation_training_examples VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  'real_device_human_gold', 'human_gold'
                )
                """,
                (
                    *row[:8],
                    json.dumps(row[8], ensure_ascii=False),
                    json.dumps(row[9], ensure_ascii=False),
                    json.dumps(row[10], ensure_ascii=False),
                    row[11],
                ),
            )
        connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
