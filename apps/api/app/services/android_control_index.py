from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence
from urllib.parse import quote


TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"\b(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}\b")
SECRET_PATTERN = re.compile(r"\b(?:bearer|token|session|cookie)[=: ]+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE)
SEMANTIC_VECTOR_DIMENSIONS = 64

# AndroidControl instructions are primarily English while ExitGuide accepts
# Korean goals. These aliases are intentionally about generic UI functions,
# never about a particular app or a hard-coded route.
FUNCTION_TERMS: dict[str, tuple[str, ...]] = {
    "account_entry": (
        "account",
        "avatar",
        "my page",
        "profile",
        "profile picture",
        "user",
        "you tab",
        "계정",
        "내 페이지",
        "마이",
        "사용자",
        "프로필",
    ),
    "settings": ("preferences", "settings", "설정", "환경설정"),
    "billing_management": (
        "billing",
        "manage membership",
        "manage subscription",
        "membership",
        "memberships",
        "payment",
        "payments",
        "premium",
        "purchase",
        "purchases",
        "subscription management",
        "결제",
        "구매",
        "구독 관리",
        "멤버십",
        "프리미엄",
    ),
    "active_subscription": (
        "active membership",
        "active subscription",
        "membership plan",
        "premium membership",
        "subscription plan",
        "구독 상품",
        "멤버십",
        "프리미엄",
    ),
    "purchase_history": (
        "billing history",
        "order history",
        "purchase history",
        "결제 내역",
        "구매 내역",
        "주문 내역",
    ),
    "content_subscriptions": (
        "following feed",
        "subscriptions",
        "subscribed channels",
        "subscriptions feed",
        "구독 목록",
        "구독 채널",
        "팔로잉",
    ),
    "cancellation": (
        "cancel",
        "cancellation",
        "deactivate",
        "disable renewal",
        "end membership",
        "turn off auto-renew",
        "unsubscribe",
        "비활성화",
        "자동결제 해제",
        "취소",
        "해지",
    ),
    "notifications": (
        "alert",
        "alerts",
        "marketing notification",
        "notification",
        "notifications",
        "push",
        "광고 알림",
        "마케팅 알림",
        "알림",
        "푸시",
    ),
    "marketing_control": (
        "advertising preferences",
        "marketing consent",
        "marketing information",
        "marketing messages",
        "promotional messages",
        "광고성 정보",
        "마케팅 정보",
        "마케팅 수신",
        "수신 동의",
        "홍보성 알림",
    ),
    "privacy": (
        "data controls",
        "personal data",
        "privacy",
        "개인정보",
        "데이터 관리",
    ),
    "account_deletion": (
        "close account",
        "delete account",
        "remove account",
        "계정 삭제",
        "회원 탈퇴",
        "탈퇴",
    ),
    "refund": ("refund", "return payment", "결제 취소", "환불"),
    "support": ("customer service", "help", "support", "고객센터", "도움말"),
    "back": ("back", "go back", "navigate back", "뒤로", "이전"),
}


@dataclass(frozen=True)
class AndroidControlStepRecord:
    episode_id: str
    goal: str
    step_index: int
    step_instruction: str
    action_type: str
    target_text: str = ""
    screen_text: str = ""
    app_name: str = ""
    source_split: str = ""
    next_screen_text: str = ""
    success: bool = True
    went_back: bool = False
    terminal: bool = False
    risk_level: str = "low"
    screen_function: str = ""
    action_function: str = ""
    failure_reason: str = ""

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> "AndroidControlStepRecord":
        required = ("episode_id", "goal", "step_index", "step_instruction", "action_type")
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"AndroidControl normalized record is missing: {', '.join(missing)}")
        return cls(
            episode_id=_clean(payload["episode_id"]),
            goal=_clean(payload["goal"]),
            step_index=int(payload["step_index"]),
            step_instruction=_clean(payload["step_instruction"]),
            action_type=_clean(payload["action_type"]).lower(),
            target_text=_clean(payload.get("target_text", "")),
            screen_text=_clean(payload.get("screen_text", "")),
            app_name=_clean(payload.get("app_name", "")),
            source_split=_clean(payload.get("source_split", "")),
            next_screen_text=_clean(payload.get("next_screen_text", "")),
            success=bool(payload.get("success", True)),
            went_back=bool(payload.get("went_back", False)),
            terminal=bool(payload.get("terminal", False)),
            risk_level=_risk_level(payload.get("risk_level", "low")),
            screen_function=_clean(payload.get("screen_function", "")),
            action_function=_clean(payload.get("action_function", "")),
            failure_reason=_clean(payload.get("failure_reason", "")),
        )


@dataclass(frozen=True)
class AndroidControlEvidence:
    episode_id: str
    goal: str
    step_index: int
    step_instruction: str
    action_type: str
    target_text: str
    screen_text: str
    app_name: str
    next_screen_text: str
    success: bool
    went_back: bool
    terminal: bool
    risk_level: str
    screen_function: str
    action_function: str
    failure_reason: str
    relevance: float
    current_candidate_alignment: float
    target_present_on_current_screen: bool

    def prompt_payload(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "step_instruction": self.step_instruction,
            "action_type": self.action_type,
            "target_text": self.target_text,
            "screen_context": self.screen_text,
            "screen_function": self.screen_function,
            "expected_next_screen": self.next_screen_text,
            "expected_next_function": self.action_function,
            "success": self.success,
            "went_back": self.went_back,
            "terminal": self.terminal,
            "risk_level": self.risk_level,
            "failure_reason": self.failure_reason,
            "relevance": round(self.relevance, 4),
            "current_candidate_alignment": round(self.current_candidate_alignment, 4),
            "target_present_on_current_screen": self.target_present_on_current_screen,
        }


class AndroidControlIndex:
    """Compact, screenshot-free retrieval index for AndroidControl steps."""

    SCHEMA_VERSION = "3"

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def build(self, records: Iterable[AndroidControlStepRecord], *, replace: bool = True) -> int:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        try:
            _create_schema(connection)
            if replace:
                connection.execute("DELETE FROM android_control_steps")
                connection.execute("DELETE FROM android_control_steps_fts")
            count = 0
            for record in records:
                goal = _redact(record.goal)
                step_instruction = _redact(record.step_instruction)
                target_text = _redact(record.target_text)
                screen_text = _redact(record.screen_text)
                searchable_record = AndroidControlStepRecord(
                    episode_id=record.episode_id,
                    goal=goal,
                    step_index=record.step_index,
                    step_instruction=step_instruction,
                    action_type=record.action_type,
                    target_text=target_text,
                    screen_text=screen_text,
                    app_name=record.app_name,
                    source_split=record.source_split,
                    next_screen_text=_redact(record.next_screen_text),
                    success=record.success,
                    went_back=record.went_back,
                    terminal=record.terminal,
                    risk_level=_risk_level(record.risk_level),
                    screen_function=record.screen_function,
                    action_function=record.action_function,
                    failure_reason=_redact(record.failure_reason),
                )
                search_text = _searchable_record_text(searchable_record)
                semantic_vector = _semantic_vector(search_text)
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO android_control_steps (
                      episode_id, goal, step_index, step_instruction, action_type,
                      target_text, screen_text, app_name, source_split, search_text,
                      semantic_vector, next_screen_text, success, went_back,
                      terminal, risk_level, screen_function, action_function,
                      failure_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.episode_id,
                        goal,
                        record.step_index,
                        step_instruction,
                        record.action_type,
                        target_text,
                        screen_text,
                        record.app_name,
                        record.source_split,
                        search_text,
                        semantic_vector,
                        searchable_record.next_screen_text,
                        int(searchable_record.success),
                        int(searchable_record.went_back),
                        int(searchable_record.terminal),
                        searchable_record.risk_level,
                        searchable_record.screen_function,
                        searchable_record.action_function,
                        searchable_record.failure_reason,
                    ),
                )
                if cursor.rowcount == 0:
                    continue
                connection.execute(
                    "INSERT INTO android_control_steps_fts(rowid, search_text) VALUES (?, ?)",
                    (cursor.lastrowid, search_text),
                )
                count += 1
            _backfill_transition_metadata(connection)
            total_count = int(connection.execute("SELECT COUNT(*) FROM android_control_steps").fetchone()[0])
            connection.execute(
                "INSERT OR REPLACE INTO android_control_metadata(key, value) VALUES ('schema_version', ?)",
                (self.SCHEMA_VERSION,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO android_control_metadata(key, value) VALUES ('record_count', ?)",
                (str(total_count),),
            )
            connection.execute(
                "INSERT OR REPLACE INTO android_control_metadata(key, value) VALUES ('semantic_vector_dimensions', ?)",
                (str(SEMANTIC_VECTOR_DIMENSIONS),),
            )
            connection.commit()
            return total_count
        finally:
            connection.close()

    def count(self) -> int:
        if not self.database_path.is_file():
            return 0
        connection = self._read_connection()
        try:
            return int(connection.execute("SELECT COUNT(*) FROM android_control_steps").fetchone()[0])
        finally:
            connection.close()

    def backfill_semantic_vectors(self, *, batch_size: int = 2_000) -> int:
        if not self.database_path.is_file():
            return 0
        connection = sqlite3.connect(self.database_path)
        try:
            _create_schema(connection)
            updated = 0
            while True:
                rows = connection.execute(
                    """
                    SELECT id, search_text FROM android_control_steps
                    WHERE length(semantic_vector) = 0 ORDER BY id LIMIT ?
                    """,
                    (max(1, batch_size),),
                ).fetchall()
                if not rows:
                    break
                connection.executemany(
                    "UPDATE android_control_steps SET semantic_vector = ? WHERE id = ?",
                    [(_semantic_vector(str(row[1])), int(row[0])) for row in rows],
                )
                updated += len(rows)
                connection.commit()
            _backfill_transition_metadata(connection)
            vector_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM android_control_steps WHERE length(semantic_vector) > 0"
                ).fetchone()[0]
            )
            connection.execute(
                "INSERT OR REPLACE INTO android_control_metadata(key, value) VALUES ('semantic_vector_count', ?)",
                (str(vector_count),),
            )
            connection.execute(
                "INSERT OR REPLACE INTO android_control_metadata(key, value) VALUES ('schema_version', ?)",
                (self.SCHEMA_VERSION,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO android_control_metadata(key, value) VALUES ('semantic_vector_dimensions', ?)",
                (str(SEMANTIC_VECTOR_DIMENSIONS),),
            )
            connection.commit()
            return updated
        finally:
            connection.close()

    def backfill_transition_metadata(self) -> int:
        """Derive successful screen transitions without the raw image shards."""

        if not self.database_path.is_file():
            return 0
        connection = sqlite3.connect(self.database_path)
        try:
            _create_schema(connection)
            updated = _backfill_transition_metadata(connection)
            connection.execute(
                "INSERT OR REPLACE INTO android_control_metadata(key, value) VALUES ('schema_version', ?)",
                (self.SCHEMA_VERSION,),
            )
            connection.commit()
            return updated
        finally:
            connection.close()

    def search(
        self,
        *,
        goal_text: str,
        candidate_labels: Sequence[str] = (),
        screen_text: str = "",
        limit: int = 5,
    ) -> list[AndroidControlEvidence]:
        if limit <= 0 or not self.database_path.is_file():
            return []
        query_text = " ".join((goal_text, *candidate_labels, screen_text))
        terms = search_terms(query_text)
        if not terms:
            return []
        # Every indexed document already contains bilingual aliases for its
        # function tags. Expanding those aliases again in the query generated
        # up to 48 OR branches and dominated runtime on the official corpus.
        # Direct visible tokens plus canonical function tags retrieve the same
        # semantic pool with a much smaller FTS expression.
        fts_terms = _fts_query_terms(query_text)
        fts_query = " OR ".join(f'"{term}"' for term in fts_terms[:24])
        connection = self._read_connection()
        connection.row_factory = sqlite3.Row
        try:
            _validate_search_schema(connection)
            rows = connection.execute(
                """
                SELECT s.*, bm25(android_control_steps_fts) AS fts_rank
                FROM android_control_steps_fts
                JOIN android_control_steps AS s ON s.id = android_control_steps_fts.rowid
                WHERE android_control_steps_fts MATCH ?
                ORDER BY fts_rank
                LIMIT ?
                """,
                (fts_query, max(40, limit * 20)),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            connection.close()

        query_tokens = set(terms)
        goal_tokens = set(search_terms(goal_text))
        candidate_tags = functional_tags(" ".join(candidate_labels))
        goal_tags = functional_tags(goal_text)
        candidate_surface_tokens = [
            set(_direct_tokens(label)) for label in candidate_labels if label.strip()
        ]
        query_vector = _semantic_vector(query_text)
        ranked: list[AndroidControlEvidence] = []
        for row in rows:
            goal = str(row["goal"])
            step_instruction = str(row["step_instruction"])
            target_text = str(row["target_text"])
            next_screen_text = str(row["next_screen_text"])
            screen_function = str(row["screen_function"])
            action_function = str(row["action_function"])
            document_text = " ".join(
                (
                    goal,
                    step_instruction,
                    target_text,
                    next_screen_text,
                    screen_function,
                    action_function,
                )
            )
            document_tokens = set(search_terms(document_text))
            document_tags = functional_tags(document_text)
            lexical = _overlap(query_tokens, document_tokens)
            goal_overlap = _overlap(goal_tokens, set(search_terms(goal)))
            tag_overlap = _overlap(goal_tags, document_tags)
            candidate_overlap = _overlap(candidate_tags, functional_tags(" ".join((step_instruction, target_text))))
            action_surface_tokens = set(_direct_tokens(" ".join((target_text, step_instruction))))
            current_candidate_alignment = max(
                (
                    _overlap(action_surface_tokens, label_tokens)
                    for label_tokens in candidate_surface_tokens
                ),
                default=0.0,
            )
            normalized_target = _normalize_phrase(target_text)
            target_present = bool(
                normalized_target
                and any(
                    normalized_target in _normalize_phrase(label)
                    or _normalize_phrase(label) in normalized_target
                    for label in candidate_labels
                    if _normalize_phrase(label)
                )
            ) or current_candidate_alignment >= 0.34
            raw_rank = abs(float(row["fts_rank"] or 0.0))
            fts_score = 1.0 / (1.0 + math.log1p(raw_rank))
            stored_vector = bytes(row["semantic_vector"] or b"")
            semantic_score = _semantic_similarity(
                query_vector,
                stored_vector or _semantic_vector(str(row["search_text"])),
            )
            relevance = min(
                1.0,
                0.25 * lexical
                + 0.22 * goal_overlap
                + 0.18 * tag_overlap
                + 0.10 * candidate_overlap
                + 0.20 * semantic_score
                + 0.05 * fts_score,
            )
            if not target_present:
                # Keep the episode as a future-function/destination prior, but
                # prevent a historical target absent from the live screen from
                # outranking a genuinely stage-aligned transition.
                relevance *= 0.72
            ranked.append(
                AndroidControlEvidence(
                    episode_id=str(row["episode_id"]),
                    goal=goal,
                    step_index=int(row["step_index"]),
                    step_instruction=step_instruction,
                    action_type=str(row["action_type"]),
                    target_text=target_text,
                    screen_text=str(row["screen_text"]),
                    app_name=str(row["app_name"]),
                    next_screen_text=next_screen_text,
                    success=bool(row["success"]),
                    went_back=bool(row["went_back"]),
                    terminal=bool(row["terminal"]),
                    risk_level=str(row["risk_level"]),
                    screen_function=screen_function,
                    action_function=action_function,
                    failure_reason=str(row["failure_reason"]),
                    relevance=relevance,
                    current_candidate_alignment=current_candidate_alignment,
                    target_present_on_current_screen=target_present,
                )
            )
        ranked.sort(key=lambda item: (-item.relevance, item.episode_id, item.step_index))
        return ranked[:limit]

    def _read_connection(self) -> sqlite3.Connection:
        """Open the runtime index without acquiring a write/schema lock.

        The official index is large and may live on a network filesystem.
        Running ``CREATE TABLE IF NOT EXISTS`` for every query forced metadata
        locks and made a Top-K lookup take seconds or minutes. Build/migration
        methods remain writable; serving queries are strictly read-only.
        """

        resolved = self.database_path.resolve().as_posix()
        uri = f"file:{quote(resolved, safe='/:')}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=3.0)
        connection.execute("PRAGMA query_only=ON")
        return connection


def read_normalized_jsonl(path: str | Path) -> Iterator[AndroidControlStepRecord]:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("record must be a JSON object")
                yield AndroidControlStepRecord.from_mapping(payload)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"Invalid AndroidControl JSONL at {source}:{line_number}: {exc}") from exc


def write_normalized_jsonl(records: Iterable[AndroidControlStepRecord], path: str | Path) -> int:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            redacted = AndroidControlStepRecord(
                episode_id=record.episode_id,
                goal=_redact(record.goal),
                step_index=record.step_index,
                step_instruction=_redact(record.step_instruction),
                action_type=record.action_type,
                target_text=_redact(record.target_text),
                screen_text=_redact(record.screen_text),
                app_name=record.app_name,
                source_split=record.source_split,
                next_screen_text=_redact(record.next_screen_text),
                success=record.success,
                went_back=record.went_back,
                terminal=record.terminal,
                risk_level=_risk_level(record.risk_level),
                screen_function=record.screen_function,
                action_function=record.action_function,
                failure_reason=_redact(record.failure_reason),
            )
            handle.write(json.dumps(asdict(redacted), ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def functional_tags(value: str) -> set[str]:
    normalized = _normalize_phrase(value)
    tags: set[str] = set()
    for tag, aliases in FUNCTION_TERMS.items():
        if any(_normalize_phrase(alias) in normalized for alias in aliases):
            tags.add(tag)
    return tags


def search_terms(value: str) -> list[str]:
    direct = {token.lower() for token in TOKEN_PATTERN.findall(value) if len(token) >= 2 or token.isdigit()}
    tags = functional_tags(value)
    expanded = set(direct)
    for tag in tags:
        expanded.add(tag)
        for alias in FUNCTION_TERMS[tag]:
            expanded.update(token.lower() for token in TOKEN_PATTERN.findall(alias) if len(token) >= 2)
    return sorted(expanded)


def _direct_tokens(value: str) -> list[str]:
    return sorted(
        {
            token.lower()
            for token in TOKEN_PATTERN.findall(value)
            if len(token) >= 2 or token.isdigit()
        }
    )


def _fts_query_terms(value: str) -> list[str]:
    return sorted({*_direct_tokens(value), *functional_tags(value)})


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS android_control_metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS android_control_steps (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          episode_id TEXT NOT NULL,
          goal TEXT NOT NULL,
          step_index INTEGER NOT NULL,
          step_instruction TEXT NOT NULL,
          action_type TEXT NOT NULL,
          target_text TEXT NOT NULL DEFAULT '',
          screen_text TEXT NOT NULL DEFAULT '',
          app_name TEXT NOT NULL DEFAULT '',
          source_split TEXT NOT NULL DEFAULT '',
          search_text TEXT NOT NULL,
          semantic_vector BLOB NOT NULL DEFAULT X'',
          next_screen_text TEXT NOT NULL DEFAULT '',
          success INTEGER NOT NULL DEFAULT 1,
          went_back INTEGER NOT NULL DEFAULT 0,
          terminal INTEGER NOT NULL DEFAULT 0,
          risk_level TEXT NOT NULL DEFAULT 'low',
          screen_function TEXT NOT NULL DEFAULT '',
          action_function TEXT NOT NULL DEFAULT '',
          failure_reason TEXT NOT NULL DEFAULT '',
          UNIQUE(episode_id, step_index)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS android_control_steps_fts
        USING fts5(search_text, tokenize='unicode61 remove_diacritics 2');
        CREATE INDEX IF NOT EXISTS idx_android_control_episode
        ON android_control_steps(episode_id, step_index);
        """
    )
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(android_control_steps)").fetchall()
    }
    if "semantic_vector" not in columns:
        connection.execute(
            "ALTER TABLE android_control_steps ADD COLUMN semantic_vector BLOB NOT NULL DEFAULT X''"
        )
    migrations = {
        "next_screen_text": "TEXT NOT NULL DEFAULT ''",
        "success": "INTEGER NOT NULL DEFAULT 1",
        "went_back": "INTEGER NOT NULL DEFAULT 0",
        "terminal": "INTEGER NOT NULL DEFAULT 0",
        "risk_level": "TEXT NOT NULL DEFAULT 'low'",
        "screen_function": "TEXT NOT NULL DEFAULT ''",
        "action_function": "TEXT NOT NULL DEFAULT ''",
        "failure_reason": "TEXT NOT NULL DEFAULT ''",
    }
    for column, declaration in migrations.items():
        if column not in columns:
            connection.execute(
                f"ALTER TABLE android_control_steps ADD COLUMN {column} {declaration}"
            )


def _validate_search_schema(connection: sqlite3.Connection) -> None:
    """Fail closed when a configured artifact is not a searchable v3 index."""

    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
    }
    required_tables = {
        "android_control_metadata",
        "android_control_steps",
        "android_control_steps_fts",
    }
    if not required_tables.issubset(tables):
        raise sqlite3.OperationalError("AndroidControl search index schema is incomplete")
    version = connection.execute(
        "SELECT value FROM android_control_metadata WHERE key = 'schema_version'"
    ).fetchone()
    if version is None or str(version[0]) != AndroidControlIndex.SCHEMA_VERSION:
        raise sqlite3.OperationalError("AndroidControl search index is not schema v3")


def _backfill_transition_metadata(connection: sqlite3.Connection) -> int:
    rows = connection.execute(
        """
        SELECT id, episode_id, goal, step_index, step_instruction, action_type,
               target_text, screen_text, app_name, source_split,
               next_screen_text, success, went_back, terminal, risk_level,
               screen_function, action_function, failure_reason
        FROM android_control_steps
        ORDER BY episode_id, step_index, id
        """
    ).fetchall()
    updates: list[tuple[object, ...]] = []
    for index, row in enumerate(rows):
        (
            row_id,
            episode_id,
            goal,
            _step_index,
            step_instruction,
            action_type,
            target_text,
            screen_text,
            app_name,
            source_split,
            stored_next_screen,
            stored_success,
            stored_went_back,
            stored_terminal,
            stored_risk,
            stored_screen_function,
            stored_action_function,
            failure_reason,
        ) = row
        next_row = rows[index + 1] if index + 1 < len(rows) else None
        same_episode_next = next_row is not None and str(next_row[1]) == str(episode_id)
        next_screen_text = _redact(
            stored_next_screen or (next_row[7] if same_episode_next else "")
        )
        terminal = bool(stored_terminal) or not same_episode_next
        went_back = bool(stored_went_back) or _normalize_phrase(action_type) in {
            "back",
            "go back",
            "navigate back",
        }
        success = bool(stored_success) and not bool(_clean(failure_reason))
        screen_function = _clean(stored_screen_function) or "|".join(
            sorted(functional_tags(str(screen_text)))
        )
        action_function = _clean(stored_action_function) or "|".join(
            sorted(
                functional_tags(
                    " ".join((str(goal), str(step_instruction), str(target_text), next_screen_text))
                )
            )
        )
        derived_risk = _derive_risk_level(
            " ".join((str(goal), str(step_instruction), str(target_text)))
        )
        risk_level = _higher_risk(_risk_level(stored_risk), derived_risk)
        normalized = AndroidControlStepRecord(
            episode_id=str(episode_id),
            goal=str(goal),
            step_index=int(_step_index),
            step_instruction=str(step_instruction),
            action_type=str(action_type),
            target_text=str(target_text),
            screen_text=str(screen_text),
            app_name=str(app_name),
            source_split=str(source_split),
            next_screen_text=next_screen_text,
            success=success,
            went_back=went_back,
            terminal=terminal,
            risk_level=risk_level,
            screen_function=screen_function,
            action_function=action_function,
            failure_reason=_redact(failure_reason),
        )
        search_text = _searchable_record_text(normalized)
        updates.append(
            (
                next_screen_text,
                int(success),
                int(went_back),
                int(terminal),
                risk_level,
                screen_function,
                action_function,
                normalized.failure_reason,
                search_text,
                _semantic_vector(search_text),
                int(row_id),
            )
        )
    if updates:
        connection.executemany(
            """
            UPDATE android_control_steps
            SET next_screen_text = ?, success = ?, went_back = ?, terminal = ?,
                risk_level = ?, screen_function = ?, action_function = ?,
                failure_reason = ?, search_text = ?, semantic_vector = ?
            WHERE id = ?
            """,
            updates,
        )
        connection.execute("DELETE FROM android_control_steps_fts")
        connection.execute(
            """
            INSERT INTO android_control_steps_fts(rowid, search_text)
            SELECT id, search_text FROM android_control_steps ORDER BY id
            """
        )
    connection.execute(
        "INSERT OR REPLACE INTO android_control_metadata(key, value) VALUES ('transition_metadata_count', ?)",
        (str(len(updates)),),
    )
    connection.execute(
        "INSERT OR REPLACE INTO android_control_metadata(key, value) VALUES ('terminal_step_count', ?)",
        (str(sum(bool(row[3]) for row in updates)),),
    )
    connection.execute(
        "INSERT OR REPLACE INTO android_control_metadata(key, value) VALUES ('failure_step_count', ?)",
        (str(sum(not bool(row[1]) for row in updates)),),
    )
    return len(updates)


def _searchable_record_text(record: AndroidControlStepRecord) -> str:
    source = " ".join(
        (
            record.goal,
            record.step_instruction,
            record.target_text,
            record.screen_text,
            record.app_name,
            record.action_type,
            record.next_screen_text,
            record.screen_function,
            record.action_function,
            record.risk_level,
        )
    )
    tags = functional_tags(source)
    aliases = [alias for tag in tags for alias in FUNCTION_TERMS[tag]]
    return _clean(" ".join((source, *sorted(tags), *aliases)))


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / math.sqrt(len(left) * len(right))


def _semantic_vector(value: str) -> bytes:
    """Build a compact portable semantic vector from bilingual function cues."""

    normalized = _normalize_phrase(value)
    features = list(search_terms(value))
    features.extend(f"tag:{tag}" for tag in sorted(functional_tags(value)))
    compact = normalized.replace(" ", "")
    features.extend(
        f"tri:{compact[index:index + 3]}"
        for index in range(max(0, len(compact) - 2))
    )
    vector = [0.0] * SEMANTIC_VECTOR_DIMENSIONS
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % SEMANTIC_VECTOR_DIMENSIONS
        vector[index] += -1.0 if digest[4] & 1 else 1.0
    norm = math.sqrt(sum(item * item for item in vector))
    if norm:
        vector = [item / norm for item in vector]
    return struct.pack(f"<{SEMANTIC_VECTOR_DIMENSIONS}f", *vector)


def _semantic_similarity(left: bytes, right: bytes) -> float:
    expected_size = SEMANTIC_VECTOR_DIMENSIONS * 4
    if len(left) != expected_size or len(right) != expected_size:
        return 0.0
    left_values = struct.unpack(f"<{SEMANTIC_VECTOR_DIMENSIONS}f", left)
    right_values = struct.unpack(f"<{SEMANTIC_VECTOR_DIMENSIONS}f", right)
    cosine = sum(a * b for a, b in zip(left_values, right_values))
    return max(0.0, min(1.0, cosine))


def _normalize_phrase(value: object) -> str:
    return " ".join(TOKEN_PATTERN.findall(_clean(value).lower()))


def _risk_level(value: object) -> str:
    normalized = _clean(value).casefold()
    return normalized if normalized in {"low", "medium", "high", "blocked"} else "low"


def _higher_risk(left: str, right: str) -> str:
    levels = {"low": 0, "medium": 1, "high": 2, "blocked": 3}
    return left if levels[_risk_level(left)] >= levels[_risk_level(right)] else right


def _derive_risk_level(value: object) -> str:
    normalized = _normalize_phrase(value)
    blocked_markers = (
        "confirm purchase",
        "pay now",
        "submit payment",
        "구매 확정",
        "결제 확정",
        "지금 결제",
    )
    high_markers = (
        "cancel subscription",
        "close account",
        "deactivate",
        "delete account",
        "end membership",
        "remove account",
        "submit refund",
        "구독 해지",
        "멤버십 해지",
        "회원 탈퇴",
        "계정 삭제",
        "환불 제출",
    )
    medium_markers = (
        "check box",
        "checkbox",
        "input text",
        "radio button",
        "switch",
        "toggle",
        "동의",
        "입력",
        "체크",
        "토글",
    )
    if any(marker in normalized for marker in blocked_markers):
        return "blocked"
    if any(marker in normalized for marker in high_markers):
        return "high"
    if any(marker in normalized for marker in medium_markers):
        return "medium"
    return "low"


def _clean(value: object) -> str:
    return " ".join(str(value if value is not None else "").split())


def _redact(value: object) -> str:
    text = _clean(value)
    text = EMAIL_PATTERN.sub("[email]", text)
    text = PHONE_PATTERN.sub("[phone]", text)
    text = SECRET_PATTERN.sub("[secret]", text)
    return text
