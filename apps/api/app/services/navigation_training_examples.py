from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence


SCHEMA_VERSION = "2"
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"\b(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}\b")
SECRET_PATTERN = re.compile(
    r"\b(?:bearer|token|session|cookie|api[_ -]?key)[=: ]+[A-Za-z0-9._~+/=-]{8,}\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NavigationTrainingExample:
    example_id: str
    source_recording_id: str
    step_ordinal: int
    split: str
    provenance: str
    verification_level: str
    app_package: str
    app_version: str
    locale: str
    goal_text: str
    target_function: str
    screen_fingerprint: str
    screen_context: dict[str, object]
    candidates: tuple[dict[str, object], ...]
    history: tuple[dict[str, object], ...]
    correct_action: dict[str, object]
    correct_candidate: dict[str, object] | None
    incorrect_candidates: tuple[dict[str, object], ...]
    outcome: str
    next_screen_fingerprint: str
    destination_screen_fingerprint: str
    reviewer: str

    def model_input(self) -> dict[str, object]:
        return {
            "goal": {
                "text": self.goal_text,
                "target_function": self.target_function,
            },
            "app": {
                "package": self.app_package,
                "version": self.app_version,
                "locale": self.locale,
            },
            "screen": {
                "fingerprint": self.screen_fingerprint,
                "context": self.screen_context,
            },
            "history": list(self.history),
            "candidates": list(self.candidates),
            "retrieval_policy": {
                "gold_is_evidence_not_macro": True,
                "must_choose_current_candidate": True,
            },
        }

    def sft_payload(self) -> dict[str, object]:
        return {
            "schema_version": int(SCHEMA_VERSION),
            "example_id": self.example_id,
            "split": self.split,
            "provenance": self.provenance,
            "verification_level": self.verification_level,
            "input": self.model_input(),
            "output": {
                "tool_call": self.correct_action,
                "expected_next_screen": self.next_screen_fingerprint,
                "destination_screen": self.destination_screen_fingerprint,
                "outcome": self.outcome,
            },
        }

    def preference_payloads(self) -> Iterator[dict[str, object]]:
        chosen = self.correct_action
        for rejected in self.incorrect_candidates:
            candidate_id = _clean(rejected.get("element_id", ""))
            if not candidate_id:
                continue
            yield {
                "schema_version": int(SCHEMA_VERSION),
                "example_id": self.example_id,
                "split": self.split,
                "provenance": self.provenance,
                "verification_level": self.verification_level,
                "input": self.model_input(),
                "chosen": {"tool_call": chosen},
                "rejected": {
                    "tool_call": {
                        "name": "click_element",
                        "arguments": {"candidate_id": candidate_id},
                    },
                    "candidate": rejected,
                },
            }


def initialize_training_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS navigation_training_examples (
          example_id TEXT PRIMARY KEY,
          source_recording_id TEXT NOT NULL,
          step_ordinal INTEGER NOT NULL,
          split TEXT NOT NULL,
          provenance TEXT NOT NULL,
          verification_level TEXT NOT NULL,
          app_package TEXT NOT NULL,
          app_version TEXT NOT NULL,
          locale TEXT NOT NULL,
          goal_text TEXT NOT NULL,
          target_function TEXT NOT NULL,
          screen_fingerprint TEXT NOT NULL,
          screen_context_json TEXT NOT NULL,
          candidates_json TEXT NOT NULL,
          history_json TEXT NOT NULL,
          correct_action_json TEXT NOT NULL,
          correct_candidate_json TEXT NOT NULL,
          incorrect_candidates_json TEXT NOT NULL,
          outcome TEXT NOT NULL,
          next_screen_fingerprint TEXT NOT NULL,
          destination_screen_fingerprint TEXT NOT NULL,
          reviewer TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(source_recording_id, step_ordinal)
        );
        CREATE INDEX IF NOT EXISTS idx_navigation_training_split
        ON navigation_training_examples(split, verification_level, target_function);
        CREATE INDEX IF NOT EXISTS idx_navigation_training_app
        ON navigation_training_examples(app_package, split);
        CREATE TABLE IF NOT EXISTS navigation_training_metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """
    )


def materialize_human_gold_examples(
    database_path: str | Path,
    *,
    replace: bool = True,
    split_overrides: Mapping[str, str] | None = None,
) -> list[NavigationTrainingExample]:
    path = Path(database_path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        initialize_training_schema(connection)
        recordings = connection.execute(
            """
            SELECT recording_id, app_package, app_version, locale, goal_text,
                   target_function, destination_screen_fingerprint, reviewer
            FROM navigation_gold_recordings
            WHERE status = 'human_gold'
            ORDER BY recording_id
            """
        ).fetchall()
        split_map = _app_split_map(
            [str(row["app_package"]) for row in recordings],
            overrides=split_overrides,
        )
        examples: list[NavigationTrainingExample] = []
        for recording in recordings:
            examples.extend(_recording_examples(connection, recording, split_map))

        if replace:
            connection.execute(
                "DELETE FROM navigation_training_examples WHERE provenance = 'real_device_human_gold'"
            )
        for example in examples:
            _insert_example(connection, example)
        connection.execute(
            "INSERT OR REPLACE INTO navigation_training_metadata(key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        connection.execute(
            "INSERT OR REPLACE INTO navigation_training_metadata(key, value) VALUES ('human_gold_example_count', ?)",
            (str(len(examples)),),
        )
        connection.execute(
            "INSERT OR REPLACE INTO navigation_training_metadata(key, value) VALUES ('split_policy', ?)",
            ("app_disjoint_hash_v1",),
        )
        connection.commit()
        return examples
    finally:
        connection.close()


def read_materialized_examples(
    database_path: str | Path,
    *,
    splits: Sequence[str] = (),
) -> Iterator[NavigationTrainingExample]:
    connection = sqlite3.connect(Path(database_path))
    connection.row_factory = sqlite3.Row
    try:
        initialize_training_schema(connection)
        where = ""
        params: list[object] = []
        if splits:
            placeholders = ",".join("?" for _ in splits)
            where = f"WHERE split IN ({placeholders})"
            params.extend(splits)
        rows = connection.execute(
            f"SELECT * FROM navigation_training_examples {where} ORDER BY split, example_id",
            params,
        ).fetchall()
        for row in rows:
            yield _example_from_row(row)
    finally:
        connection.close()


def write_training_artifacts(
    examples: Iterable[NavigationTrainingExample],
    output_directory: str | Path,
) -> dict[str, object]:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[NavigationTrainingExample]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    for example in examples:
        grouped.setdefault(example.split, []).append(example)

    artifacts: dict[str, object] = {}
    total_preferences = 0
    for split, rows in grouped.items():
        sft_path = output / f"navigation-sft-{split}.jsonl"
        preference_path = output / f"navigation-preference-{split}.jsonl"
        with sft_path.open("w", encoding="utf-8", newline="\n") as sft_handle, preference_path.open(
            "w", encoding="utf-8", newline="\n"
        ) as preference_handle:
            preference_count = 0
            for example in rows:
                sft_handle.write(
                    json.dumps(example.sft_payload(), ensure_ascii=False, separators=(",", ":")) + "\n"
                )
                for payload in example.preference_payloads():
                    preference_handle.write(
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
                    )
                    preference_count += 1
        total_preferences += preference_count
        artifacts[split] = {
            "sft": sft_path.name,
            "sft_examples": len(rows),
            "preference": preference_path.name,
            "preference_examples": preference_count,
            "apps": sorted({example.app_package for example in rows}),
        }

    manifest = {
        "schema_version": int(SCHEMA_VERSION),
        "split_policy": "app_disjoint_hash_v1",
        "gold_is_evidence_not_macro": True,
        "total_sft_examples": sum(len(rows) for rows in grouped.values()),
        "total_preference_examples": total_preferences,
        "artifacts": artifacts,
    }
    manifest_path = output / "navigation-training-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _recording_examples(
    connection: sqlite3.Connection,
    recording: sqlite3.Row,
    split_map: Mapping[str, str],
) -> list[NavigationTrainingExample]:
    rows = connection.execute(
        """
        SELECT ordinal, screen_fingerprint, screen_context_json, candidates_json,
               selected_element_id, selected_element_key, selected_label,
               selected_action, selected_risk_level, outcome,
               next_screen_fingerprint
        FROM navigation_gold_steps
        WHERE recording_id = ?
        ORDER BY ordinal
        """,
        (recording["recording_id"],),
    ).fetchall()
    history: list[dict[str, object]] = []
    examples: list[NavigationTrainingExample] = []
    for index, row in enumerate(rows):
        candidates = tuple(_candidate_payloads(row["candidates_json"]))
        action_name = _clean(row["selected_action"])
        is_destination = (
            index == len(rows) - 1
            and _clean(row["screen_fingerprint"])
            == _clean(recording["destination_screen_fingerprint"])
        )
        if not action_name and not is_destination:
            continue

        selected_id = _clean(row["selected_element_id"])
        selected_candidate = next(
            (candidate for candidate in candidates if _clean(candidate.get("element_id", "")) == selected_id),
            None,
        )
        if action_name and selected_candidate is None:
            selected_candidate = {
                "element_id": selected_id,
                "element_key": _clean(row["selected_element_key"]),
                "label": _redact(row["selected_label"]),
                "role": "button",
                "risk_level": _clean(row["selected_risk_level"]) or "low",
                "risk_reason": None,
            }
        correct_action = _tool_call(action_name, selected_id, is_destination=is_destination)
        incorrect = tuple(
            candidate
            for candidate in candidates
            if selected_candidate is None
            or _clean(candidate.get("element_id", ""))
            != _clean(selected_candidate.get("element_id", ""))
        )
        example_id = "nte_" + hashlib.sha256(
            f"{recording['recording_id']}|{row['ordinal']}|{SCHEMA_VERSION}".encode("utf-8")
        ).hexdigest()[:20]
        examples.append(
            NavigationTrainingExample(
                example_id=example_id,
                source_recording_id=_clean(recording["recording_id"]),
                step_ordinal=int(row["ordinal"]),
                split=split_map[_clean(recording["app_package"])],
                provenance="real_device_human_gold",
                verification_level="human_gold",
                app_package=_clean(recording["app_package"]),
                app_version=_clean(recording["app_version"]),
                locale=_clean(recording["locale"]),
                goal_text=_redact(recording["goal_text"]),
                target_function=_clean(recording["target_function"]),
                screen_fingerprint=_clean(row["screen_fingerprint"]),
                screen_context=_json_object(row["screen_context_json"]),
                candidates=candidates,
                history=tuple(history),
                correct_action=correct_action,
                correct_candidate=selected_candidate,
                incorrect_candidates=incorrect,
                outcome=_clean(row["outcome"]) or ("destination" if is_destination else "unknown"),
                next_screen_fingerprint=_clean(row["next_screen_fingerprint"]),
                destination_screen_fingerprint=_clean(recording["destination_screen_fingerprint"]),
                reviewer=_clean(recording["reviewer"]),
            )
        )
        history.append(
            {
                "screen_fingerprint": _clean(row["screen_fingerprint"]),
                "screen_title": _redact(
                    _json_object(row["screen_context_json"]).get("title")
                    or _json_object(row["screen_context_json"]).get("window_title")
                    or ""
                ),
                "tool_call": correct_action,
                "selected_element_key": (
                    _clean(selected_candidate.get("element_key", ""))
                    if selected_candidate is not None
                    else _clean(row["selected_element_key"])
                ),
                "selected_label": (
                    _redact(selected_candidate.get("label", ""))
                    if selected_candidate is not None
                    else _redact(row["selected_label"])
                ),
                "selected_role": (
                    _clean(selected_candidate.get("role", ""))
                    if selected_candidate is not None
                    else ""
                ),
                "target_function": _clean(recording["target_function"]),
                "outcome": _clean(row["outcome"]) or ("destination" if is_destination else "unknown"),
                "next_screen_fingerprint": _clean(row["next_screen_fingerprint"]),
            }
        )
    return examples


def _insert_example(connection: sqlite3.Connection, example: NavigationTrainingExample) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO navigation_training_examples (
          example_id, source_recording_id, step_ordinal, split, provenance,
          verification_level, app_package, app_version, locale, goal_text,
          target_function, screen_fingerprint, screen_context_json,
          candidates_json, history_json, correct_action_json,
          correct_candidate_json, incorrect_candidates_json, outcome,
          next_screen_fingerprint, destination_screen_fingerprint, reviewer
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            example.example_id,
            example.source_recording_id,
            example.step_ordinal,
            example.split,
            example.provenance,
            example.verification_level,
            example.app_package,
            example.app_version,
            example.locale,
            example.goal_text,
            example.target_function,
            example.screen_fingerprint,
            json.dumps(example.screen_context, ensure_ascii=False, separators=(",", ":")),
            json.dumps(example.candidates, ensure_ascii=False, separators=(",", ":")),
            json.dumps(example.history, ensure_ascii=False, separators=(",", ":")),
            json.dumps(example.correct_action, ensure_ascii=False, separators=(",", ":")),
            json.dumps(example.correct_candidate or {}, ensure_ascii=False, separators=(",", ":")),
            json.dumps(example.incorrect_candidates, ensure_ascii=False, separators=(",", ":")),
            example.outcome,
            example.next_screen_fingerprint,
            example.destination_screen_fingerprint,
            example.reviewer,
        ),
    )


def _example_from_row(row: sqlite3.Row) -> NavigationTrainingExample:
    return NavigationTrainingExample(
        example_id=str(row["example_id"]),
        source_recording_id=str(row["source_recording_id"]),
        step_ordinal=int(row["step_ordinal"]),
        split=str(row["split"]),
        provenance=str(row["provenance"]),
        verification_level=str(row["verification_level"]),
        app_package=str(row["app_package"]),
        app_version=str(row["app_version"]),
        locale=str(row["locale"]),
        goal_text=str(row["goal_text"]),
        target_function=str(row["target_function"]),
        screen_fingerprint=str(row["screen_fingerprint"]),
        screen_context=_json_object(row["screen_context_json"]),
        candidates=tuple(_json_list(row["candidates_json"])),
        history=tuple(_json_list(row["history_json"])),
        correct_action=_json_object(row["correct_action_json"]),
        correct_candidate=_empty_to_none(_json_object(row["correct_candidate_json"])),
        incorrect_candidates=tuple(_json_list(row["incorrect_candidates_json"])),
        outcome=str(row["outcome"]),
        next_screen_fingerprint=str(row["next_screen_fingerprint"]),
        destination_screen_fingerprint=str(row["destination_screen_fingerprint"]),
        reviewer=str(row["reviewer"]),
    )


def _app_split_map(
    app_packages: Iterable[str],
    *,
    overrides: Mapping[str, str] | None,
) -> dict[str, str]:
    apps = sorted({_clean(value) for value in app_packages if _clean(value)})
    valid = {"train", "validation", "test"}
    result: dict[str, str] = {}
    if overrides:
        for package, split in overrides.items():
            if split not in valid:
                raise ValueError(f"invalid split override for {package}: {split}")
            result[_clean(package)] = split
    remaining = [app for app in apps if app not in result]
    remaining.sort(key=lambda app: hashlib.sha256(app.encode("utf-8")).hexdigest())
    if len(apps) >= 3:
        desired_validation = max(1, round(len(apps) * 0.15))
        desired_test = max(1, round(len(apps) * 0.15))
    else:
        desired_validation = 0
        desired_test = 0
    current_validation = sum(split == "validation" for split in result.values())
    current_test = sum(split == "test" for split in result.values())
    for app in remaining:
        if current_validation < desired_validation:
            result[app] = "validation"
            current_validation += 1
        elif current_test < desired_test:
            result[app] = "test"
            current_test += 1
        else:
            result[app] = "train"
    return result


def _tool_call(action_name: str, candidate_id: str, *, is_destination: bool) -> dict[str, object]:
    if is_destination and not action_name:
        return {"name": "mark_destination", "arguments": {"reason": "human_gold_destination"}}
    normalized = action_name.casefold()
    if normalized == "click":
        return {"name": "click_element", "arguments": {"candidate_id": candidate_id}}
    if normalized in {"scroll_forward", "scroll_backward", "back", "wait_and_observe"}:
        return {"name": normalized, "arguments": {}}
    return {"name": normalized or "stop_for_user", "arguments": {}}


def _candidate_payloads(value: object) -> list[dict[str, object]]:
    rows = _json_list(value)
    result: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        result.append(
            {
                "element_id": _clean(row.get("element_id", "")),
                "element_key": _clean(row.get("element_key", "")),
                "label": _redact(row.get("label", "")),
                "role": _clean(row.get("role", "")),
                "risk_level": _clean(row.get("risk_level", "")) or "low",
                "risk_reason": _redact(row.get("risk_reason", "")) or None,
            }
        )
    return result


def _json_object(value: object) -> dict[str, object]:
    try:
        payload = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return _redact_nested(payload) if isinstance(payload, dict) else {}


def _json_list(value: object) -> list[object]:
    try:
        payload = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return _redact_nested(payload) if isinstance(payload, list) else []


def _redact_nested(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _redact_nested(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_nested(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_nested(item) for item in value]
    if isinstance(value, str):
        return _redact(value)
    return value


def _empty_to_none(value: dict[str, object]) -> dict[str, object] | None:
    return value or None


def _clean(value: object) -> str:
    return " ".join(str(value if value is not None else "").split())


def _redact(value: object) -> str:
    text = _clean(value)
    text = EMAIL_PATTERN.sub("[email]", text)
    text = PHONE_PATTERN.sub("[phone]", text)
    text = SECRET_PATTERN.sub("[secret]", text)
    return text
