from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from app.services.navigation_decision_memory import NormalizedGoal, SemanticScreenState


TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "app",
        "for",
        "in",
        "of",
        "on",
        "the",
        "to",
        "화면",
        "현재",
    }
)
GOAL_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "account.signup": (
        "account",
        "signup",
        "register",
        "registration",
        "create",
        "join",
    ),
    "account.delete": (
        "account",
        "delete",
        "close",
        "deactivate",
        "remove",
        "privacy",
        "settings",
    ),
    "membership.join": (
        "membership",
        "subscription",
        "subscribe",
        "premium",
        "plan",
        "join",
    ),
    "membership.manage": (
        "membership",
        "subscription",
        "billing",
        "manage",
        "premium",
        "plan",
        "settings",
    ),
    "membership.change": (
        "membership",
        "subscription",
        "billing",
        "change",
        "switch",
        "upgrade",
        "downgrade",
        "plan",
    ),
    "membership.cancel": (
        "membership",
        "subscription",
        "billing",
        "cancel",
        "unsubscribe",
        "renewal",
        "premium",
    ),
}
GOAL_DOMAIN_TOKENS: dict[str, frozenset[str]] = {
    "account.signup": frozenset({"account", "signup", "register", "registration"}),
    "account.delete": frozenset({"account", "delete", "deactivate"}),
    "membership.join": frozenset({"membership", "subscription", "subscribe", "premium"}),
    "membership.manage": frozenset({"membership", "subscription", "billing", "premium"}),
    "membership.change": frozenset({"membership", "subscription", "billing", "plan"}),
    "membership.cancel": frozenset(
        {"membership", "subscription", "billing", "unsubscribe", "renewal"}
    ),
}


@dataclass(frozen=True)
class PublicPriorEvidence:
    evidence_id: str
    evidence_kind: str
    dataset: str
    source_role: str
    relevance: float
    goal: str
    before_text: str
    selected_target: str
    selected_action: str
    after_text: str
    outcome_type: str
    progress_label: str

    def prompt_payload(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_class": "unverified_public_prior",
            "evidence_kind": self.evidence_kind,
            "dataset": self.dataset,
            "source_role": self.source_role,
            "relevance": round(self.relevance, 4),
            "goal": self.goal,
            "screen_before": self.before_text,
            "selected_target": self.selected_target or None,
            "selected_action": self.selected_action or None,
            "screen_after": self.after_text,
            "observed_outcome": self.outcome_type,
            "progress": self.progress_label,
            "runtime_execution_allowed": False,
            "canonical_knowledge": False,
            "usage": (
                "avoid_pattern"
                if self.evidence_kind == "failure"
                else "planning_context_only"
                if self.evidence_kind == "task"
                else "advisory_cross_app_pattern"
            ),
        }


class NavigationPublicPrior:
    """Read-only FTS adapter for curated public Android-navigation evidence.

    Public evidence is never converted into an executable candidate ID. It is
    exposed only as bounded planner context when canonical decision memory does
    not qualify for the strict fast path.
    """

    def __init__(
        self,
        service_db_path: str | Path,
        *,
        failure_db_path: str | Path | None = None,
        task_db_path: str | Path | None = None,
        max_results: int = 3,
    ) -> None:
        self.service_db_path = self._required_path(service_db_path, "service prior")
        self.failure_db_path = self._optional_path(failure_db_path, "failure prior")
        self.task_db_path = self._optional_path(task_db_path, "task prior")
        self.max_results = max(1, min(int(max_results), 5))
        self._validate_transition_db(self.service_db_path)
        if self.failure_db_path is not None:
            self._validate_transition_db(self.failure_db_path)
        if self.task_db_path is not None:
            self._validate_task_db(self.task_db_path)

    @staticmethod
    def _required_path(path: str | Path, label: str) -> Path:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"navigation {label} DB does not exist: {resolved}")
        return resolved

    @classmethod
    def _optional_path(cls, path: str | Path | None, label: str) -> Path | None:
        if path in (None, ""):
            return None
        return cls._required_path(path, label)

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @classmethod
    def _table_names(cls, path: Path) -> set[str]:
        with closing(cls._connect(path)) as connection:
            return {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }

    @classmethod
    def _validate_transition_db(cls, path: Path) -> None:
        required = {"metadata", "transition", "transition_fts"}
        missing = required - cls._table_names(path)
        if missing:
            raise ValueError(f"navigation public prior DB is missing tables: {sorted(missing)}")
        with closing(cls._connect(path)) as connection:
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if metadata.get("includes_simulated_experience", "false") != "false":
            raise ValueError("simulated experience cannot be enabled in the runtime public prior")

    @classmethod
    def _validate_task_db(cls, path: Path) -> None:
        required = {"metadata", "task", "task_fts"}
        missing = required - cls._table_names(path)
        if missing:
            raise ValueError(f"navigation task prior DB is missing tables: {sorted(missing)}")

    def status(self) -> dict[str, object]:
        with closing(self._connect(self.service_db_path)) as connection:
            service_episodes = int(connection.execute("SELECT count(*) FROM episode").fetchone()[0])
            service_transitions = int(
                connection.execute("SELECT count(*) FROM transition").fetchone()[0]
            )
            core_transitions = int(
                connection.execute(
                    "SELECT count(*) FROM transition "
                    "WHERE knowledge_role='curated_service_experience'"
                ).fetchone()[0]
            )
        failure_transitions = self._count(self.failure_db_path, "transition")
        task_records = self._count(self.task_db_path, "task")
        return {
            "enabled": True,
            "mode": "planner_advisory_only",
            "search_backend": "sqlite_fts5",
            "service_episodes": service_episodes,
            "service_transitions": service_transitions,
            "core_service_transitions": core_transitions,
            "failure_transitions": failure_transitions,
            "task_records": task_records,
            "max_service_results": self.max_results,
            "runtime_execution_allowed": False,
            "canonical_promotion_allowed": False,
        }

    @classmethod
    def _count(cls, path: Path | None, table: str) -> int:
        if path is None:
            return 0
        with closing(cls._connect(path)) as connection:
            return int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])

    def search(
        self,
        *,
        goal_text: str,
        normalized_goal: NormalizedGoal | None,
        screen: SemanticScreenState,
        app_package: str = "",
    ) -> tuple[PublicPriorEvidence, ...]:
        if normalized_goal is None:
            return ()
        goal_tokens = _goal_tokens(goal_text, normalized_goal)
        domain_tokens = GOAL_DOMAIN_TOKENS.get(
            normalized_goal.goal_id,
            frozenset({normalized_goal.family.casefold()}),
        )
        screen_tokens, candidate_token_sets = _screen_tokens(screen)
        query_tokens = _unique_tokens((*goal_tokens, *screen_tokens), limit=24)
        if not query_tokens:
            return ()
        fts_query = " OR ".join(f'"{token}"' for token in query_tokens)
        service = self._search_transitions(
            self.service_db_path,
            fts_query=fts_query,
            evidence_kind="service",
            goal_tokens=set(goal_tokens),
            domain_tokens=domain_tokens,
            screen_tokens=set(screen_tokens),
            candidate_token_sets=candidate_token_sets,
            app_package=app_package,
            limit=self.max_results,
        )
        failure = (
            self._search_transitions(
                self.failure_db_path,
                fts_query=fts_query,
                evidence_kind="failure",
                goal_tokens=set(goal_tokens),
                domain_tokens=domain_tokens,
                screen_tokens=set(screen_tokens),
                candidate_token_sets=candidate_token_sets,
                app_package=app_package,
                limit=1,
            )
            if self.failure_db_path is not None
            else ()
        )
        task = (
            self._search_tasks(
                fts_query=fts_query,
                goal_tokens=set(goal_tokens),
                domain_tokens=domain_tokens,
                limit=1,
            )
            if self.task_db_path is not None
            else ()
        )
        return tuple((*service, *failure, *task))

    def _search_transitions(
        self,
        path: Path,
        *,
        fts_query: str,
        evidence_kind: str,
        goal_tokens: set[str],
        domain_tokens: frozenset[str],
        screen_tokens: set[str],
        candidate_token_sets: Sequence[set[str]],
        app_package: str,
        limit: int,
    ) -> tuple[PublicPriorEvidence, ...]:
        with closing(self._connect(path)) as connection:
            rows = connection.execute(
                """
                SELECT t.transition_id,t.transition_key,t.dataset,t.knowledge_role,
                       t.retrieval_weight,t.app_package,t.goal,t.before_text,
                       t.candidate_text,t.selected_target,t.selected_action,t.after_text,
                       t.outcome_type,t.progress_label,t.risk_class,t.dangerous_final,
                       bm25(transition_fts,6.0,1.0,2.0,3.0,5.0,1.5) AS fts_rank
                FROM transition_fts
                JOIN transition AS t ON t.transition_id=transition_fts.rowid
                WHERE transition_fts MATCH ?
                  AND t.dangerous_final=0
                  AND t.risk_class IN ('low','medium')
                ORDER BY fts_rank
                LIMIT 160
                """,
                (fts_query,),
            ).fetchall()
        scored: list[tuple[float, sqlite3.Row]] = []
        for rank, row in enumerate(rows):
            row_goal_tokens = set(_tokens(str(row["goal"])))
            before_tokens = set(_tokens(str(row["before_text"])))
            target_tokens = set(
                _tokens(f'{row["candidate_text"]} {row["selected_target"]}')
            )
            if domain_tokens and not domain_tokens.intersection(row_goal_tokens | target_tokens):
                continue
            goal_overlap = _bounded_overlap(goal_tokens, row_goal_tokens | target_tokens, 6)
            screen_overlap = _bounded_overlap(screen_tokens, before_tokens | target_tokens, 10)
            candidate_overlap = max(
                (_jaccard(tokens, target_tokens) for tokens in candidate_token_sets),
                default=0.0,
            )
            role_bonus = 1.0 if row["knowledge_role"] == "curated_service_experience" else 0.0
            app_bonus = 1.0 if app_package and row["app_package"] == app_package else 0.0
            rank_quality = max(0.0, 1.0 - rank / max(1, len(rows)))
            relevance = min(
                1.0,
                0.34 * goal_overlap
                + 0.25 * candidate_overlap
                + 0.14 * screen_overlap
                + 0.12 * float(row["retrieval_weight"])
                + 0.08 * role_bonus
                + 0.04 * app_bonus
                + 0.03 * rank_quality,
            )
            if relevance >= 0.16:
                scored.append((relevance, row))
        scored.sort(key=lambda item: (-item[0], str(item[1]["transition_key"])))
        selected: list[PublicPriorEvidence] = []
        seen: set[tuple[str, str, str]] = set()
        for relevance, row in scored:
            key = (
                str(row["dataset"]),
                _compact(str(row["selected_target"]), 180).casefold(),
                str(row["selected_action"]),
            )
            if key in seen:
                continue
            seen.add(key)
            selected.append(
                PublicPriorEvidence(
                    evidence_id=f'{evidence_kind}:{row["dataset"]}:{row["transition_key"]}',
                    evidence_kind=evidence_kind,
                    dataset=str(row["dataset"]),
                    source_role=str(row["knowledge_role"]),
                    relevance=relevance,
                    goal=_compact(str(row["goal"]), 320),
                    before_text=_compact(str(row["before_text"]), 420),
                    selected_target=_compact(str(row["selected_target"]), 280),
                    selected_action=_compact(str(row["selected_action"]), 80),
                    after_text=_compact(str(row["after_text"]), 420),
                    outcome_type=str(row["outcome_type"]),
                    progress_label=str(row["progress_label"]),
                )
            )
            if len(selected) >= limit:
                break
        return tuple(selected)

    def _search_tasks(
        self,
        *,
        fts_query: str,
        goal_tokens: set[str],
        domain_tokens: frozenset[str],
        limit: int,
    ) -> tuple[PublicPriorEvidence, ...]:
        assert self.task_db_path is not None
        with closing(self._connect(self.task_db_path)) as connection:
            rows = connection.execute(
                """
                SELECT t.task_id,t.source_dataset,t.source_name,t.goal,
                       t.service_categories,t.role,bm25(task_fts,1.0,6.0,3.0,1.0) AS fts_rank
                FROM task_fts
                JOIN task AS t ON t.rowid=task_fts.rowid
                WHERE task_fts MATCH ?
                ORDER BY fts_rank
                LIMIT 80
                """,
                (fts_query,),
            ).fetchall()
        scored: list[tuple[float, sqlite3.Row]] = []
        for rank, row in enumerate(rows):
            task_tokens = set(_tokens(f'{row["goal"]} {row["service_categories"]}'))
            if domain_tokens and not domain_tokens.intersection(task_tokens):
                continue
            overlap = _bounded_overlap(goal_tokens, task_tokens, 6)
            relevance = min(1.0, 0.85 * overlap + 0.15 * (1.0 - rank / max(1, len(rows))))
            if relevance >= 0.18:
                scored.append((relevance, row))
        scored.sort(key=lambda item: (-item[0], str(item[1]["task_id"])))
        return tuple(
            PublicPriorEvidence(
                evidence_id=f'task:{row["source_dataset"]}:{row["task_id"]}',
                evidence_kind="task",
                dataset=str(row["source_dataset"]),
                source_role=str(row["role"]),
                relevance=relevance,
                goal=_compact(str(row["goal"]), 500),
                before_text="",
                selected_target="",
                selected_action="",
                after_text="",
                outcome_type="not_applicable",
                progress_label="planning_context",
            )
            for relevance, row in scored[:limit]
        )


def _goal_tokens(goal_text: str, normalized_goal: NormalizedGoal) -> tuple[str, ...]:
    aliases = GOAL_QUERY_ALIASES.get(
        normalized_goal.goal_id,
        (normalized_goal.family, normalized_goal.operation),
    )
    return _unique_tokens((*aliases, *_tokens(goal_text)), limit=16)


def _screen_tokens(screen: SemanticScreenState) -> tuple[tuple[str, ...], tuple[set[str], ...]]:
    candidate_token_sets = tuple(
        set(
            _tokens(
                " ".join(
                    (
                        str(candidate.get("label", "")),
                        str(candidate.get("icon_semantics", "")),
                        str(candidate.get("nearby_text", "")),
                        str(candidate.get("parent_semantics", "")),
                    )
                )
            )
        )
        for candidate in screen.candidate_payloads
    )
    flattened = _unique_tokens(
        (
            *_tokens(screen.title),
            *(token for tokens in candidate_token_sets for token in tokens),
        ),
        limit=16,
    )
    return flattened, candidate_token_sets


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in (match.casefold() for match in TOKEN_PATTERN.findall(text))
        if len(token) >= 2 and token not in STOPWORDS
    )


def _unique_tokens(tokens: Iterable[str], *, limit: int) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for raw in tokens:
        token = str(raw).casefold().strip()
        if len(token) < 2 or token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        values.append(token)
        if len(values) >= limit:
            break
    return tuple(values)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _bounded_overlap(left: set[str], right: set[str], cap: int) -> float:
    if not left or not right:
        return 0.0
    return min(1.0, len(left & right) / max(1, min(len(left), cap)))


def _compact(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."
