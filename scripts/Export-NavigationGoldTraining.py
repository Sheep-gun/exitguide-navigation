#!/usr/bin/env python3
"""Export reviewed Gold choices as candidate-ranking JSONL."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status", choices=("human_gold", "review_pending"), default="human_gold")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    connection = sqlite3.connect(args.database.resolve())
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT recording.recording_id, recording.app_package,
          recording.app_version, recording.locale, recording.goal_text,
          recording.target_function, recording.destination_screen_fingerprint,
          recording.reviewer, step.ordinal, step.screen_fingerprint,
          step.screen_context_json, step.candidates_json,
          step.selected_element_id, step.selected_element_key,
          step.selected_label, step.selected_action,
          step.selected_risk_level, step.outcome, step.next_screen_fingerprint
        FROM navigation_gold_recordings recording
        JOIN navigation_gold_steps step ON step.recording_id = recording.recording_id
        WHERE recording.status = ? AND step.selected_action IS NOT NULL
        ORDER BY recording.recording_id, step.ordinal
        """,
        (args.status,),
    ).fetchall()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    exported = 0
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        for row in rows:
            candidates = json.loads(str(row["candidates_json"] or "[]"))
            selected_id = str(row["selected_element_id"] or "")
            selected = next(
                (
                    candidate
                    for candidate in candidates
                    if isinstance(candidate, dict)
                    and str(candidate.get("element_id", "")) == selected_id
                ),
                {
                    "element_id": selected_id,
                    "element_key": str(row["selected_element_key"] or ""),
                    "label": str(row["selected_label"] or ""),
                    "risk_level": str(row["selected_risk_level"] or "low"),
                },
            )
            record = {
                "schema_version": 1,
                "provenance": "real_device_human_gold",
                "recording_id": row["recording_id"],
                "step_ordinal": int(row["ordinal"]),
                "app": {
                    "package": row["app_package"],
                    "version": row["app_version"],
                    "locale": row["locale"],
                },
                "goal": {
                    "text": row["goal_text"],
                    "target_function": row["target_function"],
                },
                "screen": {
                    "fingerprint": row["screen_fingerprint"],
                    "context": json.loads(str(row["screen_context_json"] or "{}")),
                },
                "candidates": candidates,
                "correct_candidate": selected,
                "incorrect_candidate_ids": [
                    candidate.get("element_id")
                    for candidate in candidates
                    if isinstance(candidate, dict)
                    and str(candidate.get("element_id", "")) != selected_id
                ],
                "action": row["selected_action"],
                "outcome": row["outcome"],
                "next_screen_fingerprint": row["next_screen_fingerprint"],
                "destination_screen_fingerprint": row["destination_screen_fingerprint"],
                "reviewer": row["reviewer"],
            }
            output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            exported += 1
    connection.close()
    print(f"exported={exported} output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
