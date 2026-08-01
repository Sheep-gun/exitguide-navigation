from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence


TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"\b(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}\b")
SECRET_PATTERN = re.compile(r"\b(?:bearer|token|session|cookie)[=: ]+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE)

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
    relevance: float

    def prompt_payload(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "step_instruction": self.step_instruction,
            "action_type": self.action_type,
            "target_text": self.target_text,
            "screen_context": self.screen_text,
            "relevance": round(self.relevance, 4),
        }


class AndroidControlIndex:
    """Compact, screenshot-free retrieval index for AndroidControl steps."""

    SCHEMA_VERSION = "1"

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
                )
                search_text = _searchable_record_text(searchable_record)
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO android_control_steps (
                      episode_id, goal, step_index, step_instruction, action_type,
                      target_text, screen_text, app_name, source_split, search_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    ),
                )
                if cursor.rowcount == 0:
                    continue
                connection.execute(
                    "INSERT INTO android_control_steps_fts(rowid, search_text) VALUES (?, ?)",
                    (cursor.lastrowid, search_text),
                )
                count += 1
            total_count = int(connection.execute("SELECT COUNT(*) FROM android_control_steps").fetchone()[0])
            connection.execute(
                "INSERT OR REPLACE INTO android_control_metadata(key, value) VALUES ('schema_version', ?)",
                (self.SCHEMA_VERSION,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO android_control_metadata(key, value) VALUES ('record_count', ?)",
                (str(total_count),),
            )
            connection.commit()
            return total_count
        finally:
            connection.close()

    def count(self) -> int:
        if not self.database_path.is_file():
            return 0
        connection = sqlite3.connect(self.database_path)
        try:
            return int(connection.execute("SELECT COUNT(*) FROM android_control_steps").fetchone()[0])
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
        fts_query = " OR ".join(f'"{term}"' for term in terms[:48])
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
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
        ranked: list[AndroidControlEvidence] = []
        for row in rows:
            goal = str(row["goal"])
            step_instruction = str(row["step_instruction"])
            target_text = str(row["target_text"])
            document_tokens = set(search_terms(" ".join((goal, step_instruction, target_text))))
            document_tags = functional_tags(" ".join((goal, step_instruction, target_text)))
            lexical = _overlap(query_tokens, document_tokens)
            goal_overlap = _overlap(goal_tokens, set(search_terms(goal)))
            tag_overlap = _overlap(goal_tags, document_tags)
            candidate_overlap = _overlap(candidate_tags, functional_tags(" ".join((step_instruction, target_text))))
            raw_rank = abs(float(row["fts_rank"] or 0.0))
            fts_score = 1.0 / (1.0 + math.log1p(raw_rank))
            relevance = min(
                1.0,
                0.34 * lexical
                + 0.28 * goal_overlap
                + 0.20 * tag_overlap
                + 0.13 * candidate_overlap
                + 0.05 * fts_score,
            )
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
                    relevance=relevance,
                )
            )
        ranked.sort(key=lambda item: (-item.relevance, item.episode_id, item.step_index))
        return ranked[:limit]


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
          UNIQUE(episode_id, step_index)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS android_control_steps_fts
        USING fts5(search_text, tokenize='unicode61 remove_diacritics 2');
        CREATE INDEX IF NOT EXISTS idx_android_control_episode
        ON android_control_steps(episode_id, step_index);
        """
    )


def _searchable_record_text(record: AndroidControlStepRecord) -> str:
    source = " ".join(
        (
            record.goal,
            record.step_instruction,
            record.target_text,
            record.screen_text,
            record.app_name,
            record.action_type,
        )
    )
    tags = functional_tags(source)
    aliases = [alias for tag in tags for alias in FUNCTION_TERMS[tag]]
    return _clean(" ".join((source, *sorted(tags), *aliases)))


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / math.sqrt(len(left) * len(right))


def _normalize_phrase(value: object) -> str:
    return " ".join(TOKEN_PATTERN.findall(_clean(value).lower()))


def _clean(value: object) -> str:
    return " ".join(str(value if value is not None else "").split())


def _redact(value: object) -> str:
    text = _clean(value)
    text = EMAIL_PATTERN.sub("[email]", text)
    text = PHONE_PATTERN.sub("[phone]", text)
    text = SECRET_PATTERN.sub("[secret]", text)
    return text
