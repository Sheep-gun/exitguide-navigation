from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from contextlib import closing
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = 1
ALLOWED_ACTIONS = (
    "click",
    "scroll",
    "back",
    "wait_and_observe",
    "stop_for_user",
)
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)")
LONG_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{7,}(?!\d)")
ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)
DANGEROUS_FINAL_PHRASES = (
    "최종 탈퇴",
    "탈퇴 확정",
    "영구 삭제",
    "삭제 확인",
    "결제하기",
    "구매하기",
    "개인정보 제출",
    "confirm deletion",
    "delete permanently",
    "pay now",
    "purchase now",
    "submit personal information",
)

GOAL_ROLE_PRIORS: dict[str, dict[str, float]] = {
    "account.signup": {
        "auth.signup.entry": 1.0,
        "auth.entry": 0.78,
        "account.hub": 0.44,
        "navigation.menu": 0.36,
    },
    "account.delete": {
        "account.delete.entry": 1.0,
        "privacy.settings": 0.82,
        "account.settings": 0.78,
        "account.hub": 0.62,
        "profile.hub": 0.55,
        "navigation.menu": 0.40,
    },
    "membership.join": {
        "membership.join.entry": 1.0,
        "membership.hub": 0.82,
        "billing.manage": 0.55,
        "account.hub": 0.44,
        "navigation.menu": 0.36,
    },
    "membership.manage": {
        "membership.hub": 1.0,
        "billing.manage": 0.88,
        "account.hub": 0.55,
        "profile.hub": 0.46,
        "navigation.menu": 0.38,
    },
    "membership.change": {
        "membership.change.entry": 1.0,
        "membership.hub": 0.84,
        "billing.manage": 0.78,
        "account.hub": 0.46,
        "navigation.menu": 0.36,
    },
    "membership.cancel": {
        "membership.cancel.entry": 1.0,
        "membership.hub": 0.84,
        "billing.manage": 0.78,
        "account.hub": 0.50,
        "profile.hub": 0.44,
        "navigation.menu": 0.38,
    },
}


@dataclass(frozen=True)
class NormalizedGoal:
    goal_id: str
    family: str
    operation: str
    confidence: float
    matched_phrase: str
    terminal_action_policy: str

    def prompt_payload(self) -> dict[str, object]:
        return {
            "goal_id": self.goal_id,
            "family": self.family,
            "operation": self.operation,
            "confidence": round(self.confidence, 4),
            "terminal_action_policy": self.terminal_action_policy,
        }


@dataclass(frozen=True)
class SemanticScreenState:
    semantic_fingerprint: str
    title: str
    auth_state: str
    surface_type: str
    navigation_depth: int | None
    tokens: tuple[str, ...]
    candidate_payloads: tuple[dict[str, object], ...]

    def prompt_payload(self) -> dict[str, object]:
        return {
            "semantic_fingerprint": self.semantic_fingerprint,
            "title": self.title,
            "auth_state": self.auth_state,
            "surface_type": self.surface_type,
            "navigation_depth": self.navigation_depth,
            "semantic_tokens": list(self.tokens[:80]),
        }


@dataclass(frozen=True)
class DecisionEvidence:
    case_id: str
    score: float
    action: str
    selected_label: str
    selected_role: str
    function_roles: tuple[str, ...]
    outcome_type: str
    progress_label: str
    evidence_confidence: float

    def prompt_payload(self) -> dict[str, object]:
        return {
            "similarity": round(self.score, 4),
            "action": self.action,
            "selected_affordance": {
                "label": self.selected_label,
                "role": self.selected_role,
                "function_roles": list(self.function_roles),
            }
            if self.selected_label
            else None,
            "observed_outcome": self.outcome_type,
            "progress": self.progress_label,
            "evidence_confidence": round(self.evidence_confidence, 4),
            "cross_app": True,
        }


@dataclass(frozen=True)
class DecisionMemoryQuery:
    goal: NormalizedGoal | None
    screen: SemanticScreenState
    destination_signatures: tuple[dict[str, object], ...]
    evidence: tuple[DecisionEvidence, ...]
    candidate_scores: Mapping[str, float]
    destination_match: float

    def prompt_payload(self) -> dict[str, object]:
        return {
            "normalized_goal": None if self.goal is None else self.goal.prompt_payload(),
            "destination_signatures": list(self.destination_signatures),
            "current_semantic_screen": self.screen.prompt_payload(),
            "current_candidates": [
                {
                    **candidate,
                    "decision_memory_score": round(
                        self.candidate_scores.get(str(candidate["candidate_id"]), 0.0), 4
                    ),
                }
                for candidate in self.screen.candidate_payloads
            ],
            "similar_decision_cases": [item.prompt_payload() for item in self.evidence],
            "destination_match": round(self.destination_match, 4),
            "allowed_actions": list(ALLOWED_ACTIONS),
        }


class NavigationDecisionMemory:
    """App-independent decision-case retriever for the Navigation DB redesign.

    The model never receives a database handle or an app route. This class
    returns a compact evidence packet derived from the current screen and
    cross-app cases. Runtime callers should use ``read_only=True`` and record
    outcomes through a server-owned writer after observing the next screen.
    """

    def __init__(self, path: str | Path, *, read_only: bool = True) -> None:
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"navigation decision DB does not exist: {self.path}")
        self.read_only = read_only
        with closing(self._connect()) as connection:
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            metadata = dict(connection.execute("SELECT key, value FROM navigation_db_metadata"))
        if user_version != SCHEMA_VERSION:
            raise ValueError(
                f"navigation decision DB schema mismatch: expected {SCHEMA_VERSION}, got {user_version}"
            )
        if metadata.get("schema_version") != str(SCHEMA_VERSION):
            raise ValueError("navigation decision DB metadata is missing the expected schema version")
        self.metadata = metadata

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            connection = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        else:
            connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def normalize_goal(self, goal_text: str, *, locale: str = "ko-KR") -> NormalizedGoal | None:
        normalized = normalize_text(goal_text)
        if not normalized:
            return None
        locale_prefix = locale.split("-", 1)[0].casefold()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT p.goal_id, p.phrase, p.normalized_phrase, p.phrase_kind, p.confidence,
                       g.family, g.operation, g.terminal_action_policy
                FROM goal_phrases AS p
                JOIN goals AS g ON g.goal_id = p.goal_id
                WHERE g.active = 1 AND (lower(p.locale) = lower(?) OR lower(p.locale) = ? OR p.locale = '*')
                """,
                (locale, locale_prefix),
            ).fetchall()
        scored: list[tuple[float, sqlite3.Row]] = []
        goal_tokens = set(tokenize(normalized))
        for row in rows:
            phrase = str(row["normalized_phrase"])
            phrase_tokens = set(tokenize(phrase))
            containment = 1.0 if phrase and phrase in normalized else 0.0
            token_recall = (
                len(goal_tokens & phrase_tokens) / len(phrase_tokens) if phrase_tokens else 0.0
            )
            sequence = SequenceMatcher(None, normalized, phrase).ratio()
            score = max(containment * 0.98, token_recall * 0.88, sequence * 0.76)
            score *= float(row["confidence"])
            if row["phrase_kind"] == "negative":
                score *= -1.0
            scored.append((score, row))
        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], len(str(item[1]["normalized_phrase"]))), reverse=True)
        score, row = scored[0]
        if score < 0.42:
            return None
        return NormalizedGoal(
            goal_id=str(row["goal_id"]),
            family=str(row["family"]),
            operation=str(row["operation"]),
            confidence=round(min(1.0, score), 4),
            matched_phrase=str(row["phrase"]),
            terminal_action_policy=str(row["terminal_action_policy"]),
        )

    def infer_affordance_roles(self, text: str, *, locale: str = "ko-KR") -> tuple[str, ...]:
        normalized = normalize_text(text)
        if not normalized:
            return ()
        locale_prefix = locale.split("-", 1)[0].casefold()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT role_id, normalized_alias, confidence, negative_context_json
                FROM affordance_role_aliases
                WHERE lower(locale) = lower(?) OR lower(locale) = ? OR locale = '*'
                ORDER BY confidence DESC, length(normalized_alias) DESC
                """,
                (locale, locale_prefix),
            ).fetchall()
        scored: dict[str, float] = {}
        for row in rows:
            alias = str(row["normalized_alias"])
            if not alias or alias not in normalized:
                continue
            negatives = tuple(json.loads(row["negative_context_json"] or "[]"))
            if any(normalize_text(str(value)) in normalized for value in negatives):
                continue
            role_id = str(row["role_id"])
            scored[role_id] = max(scored.get(role_id, 0.0), float(row["confidence"]))
        return tuple(role for role, _ in sorted(scored.items(), key=lambda item: (-item[1], item[0])))

    def semantic_screen_state(
        self,
        *,
        window_title: str,
        activity_name: str,
        candidates: Sequence[object],
        locale: str = "ko-KR",
        navigation_depth: int | None = None,
    ) -> SemanticScreenState:
        title = redact_text(window_title)
        activity = normalize_text(activity_name)
        candidate_payloads: list[dict[str, object]] = []
        screen_tokens: set[str] = set(tokenize(title))
        role_counts: dict[str, int] = {}
        labels: list[str] = []
        for index, candidate in enumerate(candidates):
            candidate_id = str(_value(candidate, "element_id", _value(candidate, "candidate_id", index)))
            label = redact_text(str(_value(candidate, "label", "")))
            role = normalize_text(str(_value(candidate, "role", "unknown"))) or "unknown"
            risk_level = str(_value(candidate, "risk_level", "low"))
            inferred_roles = self.infer_affordance_roles(label, locale=locale)
            labels.append(label)
            screen_tokens.update(tokenize(label))
            screen_tokens.update(inferred_roles)
            role_counts[role] = role_counts.get(role, 0) + 1
            candidate_payloads.append(
                {
                    "candidate_id": candidate_id,
                    "label": label,
                    "role": role,
                    "risk_level": risk_level,
                    "dangerous_final": is_dangerous_final_candidate(label),
                    "inferred_function_roles": list(inferred_roles),
                }
            )
        joined = " ".join((title, *labels)).casefold()
        auth_state = "unknown"
        if any(token in joined for token in ("로그인", "회원가입", "sign in", "log in", "sign up")):
            auth_state = "logged_out"
        if any(token in joined for token in ("로그아웃", "내 계정", "마이페이지", "sign out", "my account")):
            auth_state = "logged_in"
        if any(token in joined for token in ("다시 로그인", "세션 만료", "reauth", "session expired")):
            auth_state = "reauthentication"
        surface_type = "webview" if "webview" in activity else "native"
        semantic_payload = {
            "title": normalize_text(title),
            "auth_state": auth_state,
            "surface_type": surface_type,
            "role_counts": role_counts,
            "tokens": sorted(screen_tokens),
        }
        fingerprint = "dss_" + hashlib.sha256(
            canonical_json(semantic_payload).encode("utf-8")
        ).hexdigest()[:20]
        return SemanticScreenState(
            semantic_fingerprint=fingerprint,
            title=title,
            auth_state=auth_state,
            surface_type=surface_type,
            navigation_depth=navigation_depth,
            tokens=tuple(sorted(screen_tokens)),
            candidate_payloads=tuple(candidate_payloads),
        )

    def retrieve(
        self,
        *,
        goal_text: str,
        window_title: str,
        activity_name: str,
        candidates: Sequence[object],
        locale: str = "ko-KR",
        exclude_app_package: str = "",
        top_k: int = 5,
    ) -> DecisionMemoryQuery:
        screen = self.semantic_screen_state(
            window_title=window_title,
            activity_name=activity_name,
            candidates=candidates,
            locale=locale,
        )
        goal = self.normalize_goal(goal_text, locale=locale)
        if goal is None:
            return DecisionMemoryQuery(None, screen, (), (), {}, 0.0)
        with closing(self._connect()) as connection:
            signatures = tuple(
                _signature_payload(row)
                for row in connection.execute(
                    """
                    SELECT signature_id, name, required_features_json, optional_features_json,
                           forbidden_features_json, terminal_features_json, match_threshold
                    FROM destination_signatures WHERE goal_id = ? ORDER BY version DESC, name
                    """,
                    (goal.goal_id,),
                )
            )
            params: list[object] = [goal.goal_id]
            app_filter = ""
            if exclude_app_package:
                app_filter = " AND source_app_package <> ?"
                params.append(exclude_app_package)
            rows = connection.execute(
                f"""
                SELECT * FROM verified_decision_cases
                WHERE goal_id = ? {app_filter}
                  AND connectivity_status IN ('observed', 'not_observed')
                ORDER BY evidence_weight DESC
                LIMIT 500
                """,
                params,
            ).fetchall()
        evidence = self._score_evidence(screen, rows, top_k=max(0, top_k))
        candidate_scores = self._score_current_candidates(goal, screen, evidence)
        destination_match = _destination_match(screen.tokens, signatures)
        return DecisionMemoryQuery(
            goal=goal,
            screen=screen,
            destination_signatures=signatures,
            evidence=tuple(evidence),
            candidate_scores=candidate_scores,
            destination_match=destination_match,
        )

    def _score_evidence(
        self,
        screen: SemanticScreenState,
        rows: Iterable[sqlite3.Row],
        *,
        top_k: int,
    ) -> list[DecisionEvidence]:
        current_tokens = set(screen.tokens)
        current_labels = [str(item["label"]) for item in screen.candidate_payloads]
        current_roles = {
            role
            for item in screen.candidate_payloads
            for role in item["inferred_function_roles"]  # type: ignore[union-attr]
        }
        scored: list[DecisionEvidence] = []
        for row in rows:
            stored_tokens = set(json.loads(row["semantic_tokens_json"] or "[]"))
            screen_overlap = jaccard(current_tokens, stored_tokens)
            selected_label = str(row["chosen_label"] or "")
            label_match = max(
                (text_similarity(selected_label, label) for label in current_labels),
                default=0.0,
            )
            function_roles = tuple(json.loads(row["function_roles_json"] or "[]"))
            role_overlap = jaccard(current_roles, set(function_roles))
            progress = {"reached": 1.0, "advanced": 0.82, "unchanged": 0.15, "regressed": 0.0}.get(
                str(row["progress_label"]), 0.25
            )
            confidence = float(row["evidence_weight"])
            score = (
                screen_overlap * 0.32
                + label_match * 0.24
                + role_overlap * 0.14
                + confidence * 0.16
                + progress * 0.09
                + 0.05
            )
            if row["outcome_type"] in {"no_change", "wrong_destination", "infinite_feed"}:
                score *= 0.45
            scored.append(
                DecisionEvidence(
                    case_id=str(row["case_id"]),
                    score=round(min(1.0, score), 4),
                    action=str(row["chosen_action"]),
                    selected_label=selected_label,
                    selected_role=str(row["chosen_role"] or ""),
                    function_roles=function_roles,
                    outcome_type=str(row["outcome_type"] or "unknown"),
                    progress_label=str(row["progress_label"] or "unknown"),
                    evidence_confidence=confidence,
                )
            )
        scored.sort(key=lambda item: (-item.score, item.case_id))
        return scored[:top_k]

    def _score_current_candidates(
        self,
        goal: NormalizedGoal,
        screen: SemanticScreenState,
        evidence: Sequence[DecisionEvidence],
    ) -> dict[str, float]:
        priors = GOAL_ROLE_PRIORS.get(goal.goal_id, {})
        scores: dict[str, float] = {}
        for candidate in screen.candidate_payloads:
            candidate_id = str(candidate["candidate_id"])
            label = str(candidate["label"])
            roles = set(candidate["inferred_function_roles"])  # type: ignore[arg-type]
            ontology = max((priors.get(role, 0.0) for role in roles), default=0.0)
            memory_support = 0.0
            for item in evidence:
                if item.action != "click":
                    continue
                label_score = text_similarity(label, item.selected_label)
                role_score = jaccard(roles, set(item.function_roles))
                memory_support = max(
                    memory_support,
                    item.score * (label_score * 0.58 + role_score * 0.42),
                )
            lexical = text_similarity(goal.goal_id.replace(".", " "), label)
            score = max(ontology * 0.72 + memory_support * 0.28, memory_support * 0.82, lexical * 0.25)
            if str(candidate["risk_level"]) in {"high", "blocked"}:
                score = min(score, 0.05)
            scores[candidate_id] = round(max(0.0, min(1.0, score)), 4)
        return scores

    def recommend_action(self, query: DecisionMemoryQuery) -> tuple[str, str | None, str | None, float]:
        if query.goal is None:
            return "wait_and_observe", None, None, 0.0
        if query.destination_match >= 0.72:
            return "stop_for_user", None, None, query.destination_match
        ranked = sorted(query.candidate_scores.items(), key=lambda item: (-item[1], item[0]))
        if ranked and ranked[0][1] >= 0.24:
            best_id, best_score = ranked[0]
            candidate = next(
                item for item in query.screen.candidate_payloads if item["candidate_id"] == best_id
            )
            if str(candidate["risk_level"]) in {"medium", "high", "blocked"}:
                return "stop_for_user", None, None, best_score
            return "click", best_id, None, best_score
        non_click = next(
            (
                item
                for item in query.evidence
                if item.action in {"scroll", "back", "wait_and_observe"} and item.score >= 0.38
            ),
            None,
        )
        if non_click is not None:
            return non_click.action, None, "down" if non_click.action == "scroll" else None, non_click.score
        return "wait_and_observe", None, None, 0.15


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").translate(ZERO_WIDTH)
    return " ".join(normalized.casefold().split())


def redact_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").translate(ZERO_WIDTH)
    value = EMAIL_PATTERN.sub("[email]", value)
    value = PHONE_PATTERN.sub("[phone]", value)
    value = LONG_NUMBER_PATTERN.sub("[number]", value)
    return " ".join(value.split())[:500]


def is_dangerous_final_candidate(label: str) -> bool:
    normalized = normalize_text(label)
    return any(phrase in normalized for phrase in DANGEROUS_FINAL_PHRASES)


def tokenize(value: str) -> tuple[str, ...]:
    return tuple(TOKEN_PATTERN.findall(normalize_text(value)))


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(prefix: str, *parts: object, length: int = 20) -> str:
    payload = "\x1f".join(canonical_json(part) for part in parts)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def text_similarity(left: str, right: str) -> float:
    left_normalized = normalize_text(left)
    right_normalized = normalize_text(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0
    left_tokens = set(tokenize(left_normalized))
    right_tokens = set(tokenize(right_normalized))
    containment = 0.92 if left_normalized in right_normalized or right_normalized in left_normalized else 0.0
    return max(
        containment,
        SequenceMatcher(None, left_normalized, right_normalized).ratio() * 0.82,
        jaccard(left_tokens, right_tokens),
    )


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _value(value: object, key: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _signature_payload(row: sqlite3.Row) -> dict[str, object]:
    return {
        "signature_id": str(row["signature_id"]),
        "name": str(row["name"]),
        "required_features": json.loads(row["required_features_json"]),
        "optional_features": json.loads(row["optional_features_json"]),
        "forbidden_features": json.loads(row["forbidden_features_json"]),
        "terminal_features": json.loads(row["terminal_features_json"]),
        "threshold": float(row["match_threshold"]),
    }


def _destination_match(tokens: Sequence[str], signatures: Sequence[dict[str, object]]) -> float:
    token_text = " ".join(tokens)
    best = 0.0
    for signature in signatures:
        required = signature.get("required_features", {})
        optional = signature.get("optional_features", [])
        forbidden = signature.get("forbidden_features", [])
        terminal = signature.get("terminal_features", [])
        groups = required.get("any_groups", []) if isinstance(required, dict) else []
        required_score = (
            sum(any(normalize_text(str(term)) in token_text for term in group) for group in groups)
            / len(groups)
            if groups
            else 0.0
        )
        optional_values = list(optional) if isinstance(optional, list) else []
        optional_score = (
            sum(normalize_text(str(term)) in token_text for term in optional_values) / len(optional_values)
            if optional_values
            else 0.0
        )
        terminal_values = list(terminal) if isinstance(terminal, list) else []
        terminal_score = (
            max((normalize_text(str(term)) in token_text for term in terminal_values), default=False)
        )
        forbidden_values = list(forbidden) if isinstance(forbidden, list) else []
        forbidden_hit = any(normalize_text(str(term)) in token_text for term in forbidden_values)
        score = required_score * 0.70 + optional_score * 0.18 + float(terminal_score) * 0.12
        if forbidden_hit:
            score *= 0.2
        best = max(best, score)
    return round(min(1.0, best), 4)
