from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣_]{2,}")


@dataclass(frozen=True)
class HumanGoldEvidence:
    example_id: str
    source_recording_id: str
    app_package: str
    app_version: str
    locale: str
    goal_text: str
    target_function: str
    screen_fingerprint: str
    chosen_label: str
    chosen_element_key: str
    expected_next_screen: str
    destination_example: bool
    score: float

    def prompt_payload(self) -> dict[str, object]:
        return {
            "source": "human_gold",
            "evidence_only": True,
            "never_replay_as_macro": True,
            "example_id": self.example_id,
            "source_recording_id": self.source_recording_id,
            "app_package": self.app_package,
            "app_version": self.app_version,
            "locale": self.locale,
            "goal_text": self.goal_text,
            "target_function": self.target_function,
            "screen_fingerprint": self.screen_fingerprint,
            "historically_chosen_label": self.chosen_label,
            "historically_chosen_element_key": self.chosen_element_key,
            "expected_next_screen": self.expected_next_screen,
            "destination_example": self.destination_example,
            "retrieval_score": round(self.score, 6),
        }


class HumanGoldEvidenceIndex:
    """FTS-backed Human Gold retrieval over screen-level training examples.

    The index returns model evidence only. It deliberately exposes no API for
    executing an ordered recording or resolving an absolute coordinate.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def rebuild(self) -> int:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            _ensure_schema(connection)
            if not _table_exists(connection, "navigation_training_examples"):
                return 0
            rows = connection.execute(
                """
                SELECT example_id, source_recording_id, app_package, app_version,
                       locale, goal_text, target_function, screen_fingerprint,
                       screen_context_json, candidates_json, correct_candidate_json,
                       next_screen_fingerprint
                FROM navigation_training_examples
                WHERE provenance = 'real_device_human_gold'
                  AND verification_level = 'human_gold'
                ORDER BY example_id
                """
            ).fetchall()
            connection.execute("DELETE FROM navigation_gold_search_documents")
            connection.execute("DELETE FROM navigation_gold_search_fts")
            for row in rows:
                chosen = _json_object(row["correct_candidate_json"])
                screen_text = _flatten_text(_json_value(row["screen_context_json"]))
                candidate_text = _flatten_text(_json_value(row["candidates_json"]))
                chosen_label = str(chosen.get("label", ""))
                chosen_key = str(chosen.get("element_key", ""))
                values = (
                    str(row["example_id"]),
                    str(row["source_recording_id"]),
                    str(row["app_package"]),
                    str(row["app_version"]),
                    str(row["locale"]),
                    str(row["goal_text"]),
                    str(row["target_function"]),
                    str(row["screen_fingerprint"]),
                    screen_text,
                    candidate_text,
                    chosen_label,
                    chosen_key,
                    str(row["next_screen_fingerprint"]),
                )
                connection.execute(
                    """
                    INSERT INTO navigation_gold_search_documents (
                      example_id, source_recording_id, app_package, app_version,
                      locale, goal_text, target_function, screen_fingerprint,
                      screen_text, candidate_text, chosen_label, chosen_element_key,
                      expected_next_screen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                connection.execute(
                    """
                    INSERT INTO navigation_gold_search_fts (
                      example_id, app_package, goal_text, target_function,
                      screen_text, candidate_text, chosen_label
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        values[0], values[2], values[5], values[6],
                        values[8], values[9], values[10],
                    ),
                )
            connection.execute(
                "INSERT OR REPLACE INTO navigation_gold_search_metadata(key, value) VALUES ('document_count', ?)",
                (str(len(rows)),),
            )
            connection.execute(
                "INSERT OR REPLACE INTO navigation_gold_search_metadata(key, value) VALUES ('source_policy', ?) ",
                ("human_gold_screen_examples;evidence_only;no_macro_replay",),
            )
            training_schema_row = connection.execute(
                "SELECT value FROM navigation_training_metadata WHERE key = 'schema_version'"
            ).fetchone() if _table_exists(connection, "navigation_training_metadata") else None
            connection.execute(
                "INSERT OR REPLACE INTO navigation_gold_search_metadata(key, value) VALUES ('training_schema_version', ?)",
                (str(training_schema_row[0]) if training_schema_row is not None else "unknown",),
            )
            connection.commit()
            return len(rows)
        finally:
            connection.close()

    def search(
        self,
        *,
        goal_text: str,
        target_function: str,
        app_package: str,
        app_version: str,
        locale: str,
        screen_text: str,
        candidate_labels: Iterable[str],
        top_k: int = 5,
        exclude_recording_ids: Iterable[str] = (),
        exclude_app_packages: Iterable[str] = (),
    ) -> list[HumanGoldEvidence]:
        if top_k <= 0 or not self.database_path.is_file():
            return []
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            _ensure_schema(connection)
            if self._index_is_stale(connection):
                connection.close()
                self.rebuild()
                connection = sqlite3.connect(self.database_path)
                connection.row_factory = sqlite3.Row
            current_candidate_labels = [str(item) for item in candidate_labels if str(item).strip()]
            query_text = " ".join(
                [goal_text, target_function, screen_text, *current_candidate_labels]
            )
            fts_query = _fts_query(query_text)
            rows: dict[str, tuple[sqlite3.Row, float]] = {}
            if fts_query:
                for row in connection.execute(
                    """
                    SELECT document.*, bm25(navigation_gold_search_fts) AS lexical_rank
                    FROM navigation_gold_search_fts
                    JOIN navigation_gold_search_documents AS document
                      ON document.example_id = navigation_gold_search_fts.example_id
                    WHERE navigation_gold_search_fts MATCH ?
                    ORDER BY lexical_rank LIMIT 80
                    """,
                    (fts_query,),
                ).fetchall():
                    rows[str(row["example_id"])] = (row, float(row["lexical_rank"] or 0.0))
            for row in connection.execute(
                """
                SELECT document.*, 0.0 AS lexical_rank
                FROM navigation_gold_search_documents AS document
                WHERE app_package = ? OR target_function = ?
                ORDER BY CASE WHEN app_package = ? THEN 0 ELSE 1 END,
                         CASE WHEN target_function = ? THEN 0 ELSE 1 END,
                         example_id LIMIT 120
                """,
                (app_package, target_function, app_package, target_function),
            ).fetchall():
                rows.setdefault(str(row["example_id"]), (row, 0.0))

            excluded_recordings = {str(item) for item in exclude_recording_ids}
            excluded_apps = {str(item) for item in exclude_app_packages}
            query_tokens = set(_tokens(query_text))
            current_stage_tokens = set(
                _tokens(" ".join([screen_text, *current_candidate_labels]))
            )
            terminal_surface_score = _terminal_surface_score(
                target_function,
                " ".join([screen_text, *current_candidate_labels]),
            )
            ranked: list[HumanGoldEvidence] = []
            for row, lexical_rank in rows.values():
                if str(row["source_recording_id"]) in excluded_recordings:
                    continue
                if str(row["app_package"]) in excluded_apps:
                    continue
                document_tokens = set(
                    _tokens(
                        " ".join(
                            str(row[key] or "")
                            for key in (
                                "goal_text", "target_function", "screen_text",
                                "candidate_text", "chosen_label",
                            )
                        )
                    )
                )
                overlap = len(query_tokens & document_tokens) / max(1, len(query_tokens))
                document_stage_tokens = set(
                    _tokens(
                        " ".join(
                            (str(row["screen_text"] or ""), str(row["candidate_text"] or ""))
                        )
                    )
                )
                stage_overlap = _set_overlap(current_stage_tokens, document_stage_tokens)
                chosen_label = str(row["chosen_label"] or "")
                chosen_alignment = max(
                    (_label_similarity(chosen_label, label) for label in current_candidate_labels),
                    default=0.0,
                )
                destination_example = not chosen_label and not str(row["expected_next_screen"] or "")
                score = overlap * 1.0
                score += 5.0 if str(row["app_package"]) == app_package else 0.0
                score += 2.0 if str(row["target_function"]) == target_function else 0.0
                score += 0.5 if str(row["locale"]) == locale else 0.0
                score += 0.35 if app_version and str(row["app_version"]) == app_version else 0.0
                score += 3.0 * chosen_alignment
                score += 2.0 * stage_overlap
                if destination_example:
                    score += 5.0 * terminal_surface_score
                    score -= 1.5 * (1.0 - terminal_surface_score)
                score += 1.0 / (1.0 + max(0.0, lexical_rank))
                ranked.append(
                    HumanGoldEvidence(
                        example_id=str(row["example_id"]),
                        source_recording_id=str(row["source_recording_id"]),
                        app_package=str(row["app_package"]),
                        app_version=str(row["app_version"]),
                        locale=str(row["locale"]),
                        goal_text=str(row["goal_text"]),
                        target_function=str(row["target_function"]),
                        screen_fingerprint=str(row["screen_fingerprint"]),
                        chosen_label=chosen_label,
                        chosen_element_key=str(row["chosen_element_key"]),
                        expected_next_screen=str(row["expected_next_screen"]),
                        destination_example=destination_example,
                        score=score,
                    )
                )
            ranked.sort(key=lambda item: (-item.score, item.example_id))
            return ranked[:top_k]
        finally:
            connection.close()

    def _index_is_stale(self, connection: sqlite3.Connection) -> bool:
        if not _table_exists(connection, "navigation_training_examples"):
            return False
        source_count = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM navigation_training_examples
                WHERE provenance = 'real_device_human_gold'
                  AND verification_level = 'human_gold'
                """
            ).fetchone()[0]
        )
        indexed_count = int(
            connection.execute("SELECT COUNT(*) FROM navigation_gold_search_documents").fetchone()[0]
        )
        if source_count != indexed_count:
            return True
        if not _table_exists(connection, "navigation_training_metadata"):
            return False
        source_schema = connection.execute(
            "SELECT value FROM navigation_training_metadata WHERE key = 'schema_version'"
        ).fetchone()
        indexed_schema = connection.execute(
            "SELECT value FROM navigation_gold_search_metadata WHERE key = 'training_schema_version'"
        ).fetchone()
        return (
            source_schema is not None
            and (indexed_schema is None or str(indexed_schema[0]) != str(source_schema[0]))
        )


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS navigation_gold_search_documents (
          example_id TEXT PRIMARY KEY,
          source_recording_id TEXT NOT NULL,
          app_package TEXT NOT NULL,
          app_version TEXT NOT NULL,
          locale TEXT NOT NULL,
          goal_text TEXT NOT NULL,
          target_function TEXT NOT NULL,
          screen_fingerprint TEXT NOT NULL,
          screen_text TEXT NOT NULL,
          candidate_text TEXT NOT NULL,
          chosen_label TEXT NOT NULL,
          chosen_element_key TEXT NOT NULL,
          expected_next_screen TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gold_search_scope
          ON navigation_gold_search_documents(app_package, target_function, locale);
        CREATE TABLE IF NOT EXISTS navigation_gold_search_metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS navigation_gold_search_fts USING fts5(
          example_id UNINDEXED,
          app_package,
          goal_text,
          target_function,
          screen_text,
          candidate_text,
          chosen_label,
          tokenize = 'unicode61 remove_diacritics 2'
        );
        """
    )


def _set_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def _label_similarity(left: str, right: str) -> float:
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    token_score = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    left_compact = "".join(left_tokens)
    right_compact = "".join(right_tokens)
    return max(token_score, SequenceMatcher(None, left_compact, right_compact).ratio())


def _terminal_surface_score(target_function: str, value: str) -> float:
    normalized = " ".join(value.casefold().split())
    if target_function.startswith("notification."):
        hits = sum(
            marker in normalized
            for marker in ("알림", "푸시", "notification", "notifications", "alert")
        )
        return min(1.0, hits / 2.0)
    markers = {
        "subscription.cancel.entry": ("해지", "cancel subscription", "end membership"),
        "account.delete.entry": ("회원 탈퇴", "계정 삭제", "delete account"),
        "account.signup": ("회원가입", "계정 만들기", "sign up", "create account"),
    }.get(target_function, ())
    return 1.0 if any(marker in normalized for marker in markers) else 0.0


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone() is not None


def _json_value(value: object) -> object:
    try:
        return json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}


def _json_object(value: object) -> dict[str, object]:
    parsed = _json_value(value)
    return parsed if isinstance(parsed, dict) else {}


def _flatten_text(value: object) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            parts.append(_flatten_text(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            parts.append(_flatten_text(item))
    elif value is not None:
        parts.append(str(value))
    return " ".join(part for part in parts if part).strip()


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.group(0).casefold() for match in TOKEN_PATTERN.finditer(value)))


def _fts_query(value: str) -> str:
    tokens = _tokens(value)[:32]
    return " OR ".join(f'"{token}"' for token in tokens)
