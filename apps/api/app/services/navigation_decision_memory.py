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


LEGACY_SCHEMA_VERSION = 1
PROFILE_SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = (LEGACY_SCHEMA_VERSION, PROFILE_SCHEMA_VERSION)
ALLOWED_ACTIONS = (
    "click",
    "scroll",
    "back",
    "wait_and_observe",
    "stop_for_user",
)
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
USER_HANDLE_PATTERN = re.compile(r"(?<![\w@])@[0-9A-Za-z._-]{2,64}\b")
MASKED_KOREAN_NAME_PATTERN = re.compile(
    r"(?<![가-힣])(?:[가-힣]{1,2}\*+[가-힣]{1,2})(?![가-힣])"
)
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:"
    r"(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}"
    r"|0(?:2|[3-6]\d)[- ]?\d{3,4}[- ]?\d{4}"
    r"|1[568]\d{2}[- ]?\d{4}"
    r")(?!\d)"
)
CURRENCY_AMOUNT_PATTERN = re.compile(
    r"(?<![\w])(?:"
    r"(?:₩|\$|€|¥)\s?\d[\d,]*(?:\.\d{1,2})?"
    r"|\d[\d,]*(?:\.\d{1,2})?\s?(?:원|KRW|USD|달러)"
    r")(?![\w])",
    re.IGNORECASE,
)
LONG_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{7,}(?!\d)")
ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)
DIRECT_FUNCTION_ROLE_THRESHOLD = 0.50
KOREAN_TOKEN_SUFFIXES = tuple(
    sorted(
        (
            "\ud558고싶어요",
            "\ud558고싶어",
            "\ud558려고",
            "\ud558고",
            "\ud569니다",
            "\ud574요",
            "\uc744",
            "\ub97c",
            "\uc740",
            "\ub294",
            "\uc774",
            "\uac00",
            "\uc5d0서",
            "\uc5d0",
            "\uc73c로",
            "\ub85c",
            "\uc640",
            "\uacfc",
            "\ub3c4",
            "\ub9cc",
        ),
        key=len,
        reverse=True,
    )
)
DANGEROUS_FINAL_PHRASES = (
    "최종 탈퇴",
    "탈퇴 확정",
    "영구 삭제",
    "삭제 확인",
    "결제하기",
    "구매하기",
    "개인정보 제출",
    "로그아웃",
    "계정 전환",
    "프로필 저장",
    "프로필 수정 완료",
    "모두 동의하고",
    "동의하고 가입",
    "신청서 제출",
    "신청하기",
    "메시지 보내기",
    "전송하기",
    "장바구니 담기",
    "주문하기",
    "구독 확정",
    "구독 시작",
    "멤버십 가입 완료",
    "confirm deletion",
    "delete permanently",
    "pay now",
    "purchase now",
    "submit personal information",
    "sign out",
    "switch account",
    "save profile",
    "submit application",
    "send message",
    "add to cart",
    "place order",
    "start subscription",
)

# Exact labels that commit a state change but are too generic to search as
# substrings in the whole candidate context.  For example, a harmless menu
# can have "저장하기" in nearby text, while a button whose own label is
# "저장하기" must stop for the user.
STATE_CHANGING_ACTION_LABELS = frozenset(
    {
        "저장",
        "저장하기",
        "변경 저장",
        "변경 내용 저장",
        "변경사항 저장",
        "적용",
        "적용하기",
        "제출",
        "제출하기",
        "save",
        "save changes",
        "apply",
        "apply changes",
        "submit",
    }
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
    scroll_direction: str
    selected_label: str
    selected_role: str
    function_roles: tuple[str, ...]
    outcome_type: str
    progress_label: str
    evidence_confidence: float
    source_app_package: str
    source_type: str
    verification_count: int
    provenance_validated: bool
    screen_similarity: float

    def prompt_payload(self) -> dict[str, object]:
        return {
            "similarity": round(self.score, 4),
            "action": self.action,
            "scroll_direction": self.scroll_direction or None,
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
            "source_type": self.source_type,
            "verification_count": self.verification_count,
            "provenance_validated": self.provenance_validated,
            "cross_app": True,
        }


@dataclass(frozen=True)
class CandidateMemoryConfidence:
    candidate_id: str
    score: float
    support_tier: str
    supporting_cases: int
    supporting_apps: int
    conflicting_cases: int
    provenance_quality: float
    fast_path_eligible: bool
    reasons: tuple[str, ...]

    def prompt_payload(self) -> dict[str, object]:
        return {
            "score": round(self.score, 4),
            "support_tier": self.support_tier,
            "supporting_cases": self.supporting_cases,
            "supporting_apps": self.supporting_apps,
            "conflicting_cases": self.conflicting_cases,
            "provenance_quality": round(self.provenance_quality, 4),
            "fast_path_eligible": self.fast_path_eligible,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class DecisionMemoryQuery:
    goal: NormalizedGoal | None
    screen: SemanticScreenState
    destination_signatures: tuple[dict[str, object], ...]
    evidence: tuple[DecisionEvidence, ...]
    candidate_scores: Mapping[str, float]
    candidate_confidence: Mapping[str, CandidateMemoryConfidence]
    action_scores: Mapping[str, float]
    destination_match: float
    standards_profile: str

    def fast_path_candidate_id(self) -> str | None:
        eligible = sorted(
            (
                item
                for item in self.candidate_confidence.values()
                if item.fast_path_eligible
            ),
            key=lambda item: (-item.score, item.candidate_id),
        )
        if not eligible:
            return None
        best = eligible[0]
        competing_scores = sorted(
            (
                item.score
                for item in self.candidate_confidence.values()
                if item.candidate_id != best.candidate_id
            ),
            reverse=True,
        )
        second = competing_scores[0] if competing_scores else 0.0
        return best.candidate_id if best.score - second >= 0.08 else None

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
                    "memory_confidence": self.candidate_confidence.get(
                        str(candidate["candidate_id"])
                    ).prompt_payload()
                    if str(candidate["candidate_id"]) in self.candidate_confidence
                    else None,
                }
                for candidate in self.screen.candidate_payloads
            ],
            "similar_decision_cases": [item.prompt_payload() for item in self.evidence],
            "destination_match": round(self.destination_match, 4),
            "memory_action_scores": {
                key: round(value, 4) for key, value in self.action_scores.items()
            },
            "standards_profile": self.standards_profile,
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
        if user_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                "navigation decision DB schema mismatch: expected one of "
                f"{SUPPORTED_SCHEMA_VERSIONS}, got {user_version}"
            )
        if metadata.get("schema_version") != str(user_version):
            raise ValueError("navigation decision DB metadata is missing the expected schema version")
        self.schema_version = user_version
        self.profile_enabled = (
            user_version == PROFILE_SCHEMA_VERSION
            and metadata.get("standards_profile") == "exitguide.navigation-experience.v1"
        )
        self.metadata = metadata

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            connection = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        else:
            connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def goal_catalog(self, *, locale: str = "ko-KR") -> tuple[dict[str, object], ...]:
        """Return the bounded Goal Ontology catalog exposed to the classifier."""

        locale_prefix = locale.split("-", 1)[0].casefold()
        with closing(self._connect()) as connection:
            if self.profile_enabled:
                rows = connection.execute(
                    """
                    SELECT g.goal_id, g.family, g.operation, g.description, g.risk_class,
                           g.terminal_action_policy, p.locale, p.phrase, p.phrase_kind,
                           p.confidence, c.concept_uri, c.notation,
                           l.skos_property_uri, l.language_tag
                    FROM goals AS g
                    JOIN goal_standard_concepts AS c ON c.goal_id=g.goal_id
                    LEFT JOIN goal_phrases AS p ON p.goal_id=g.goal_id
                    LEFT JOIN goal_label_mappings AS l ON l.phrase_id=p.phrase_id
                    WHERE g.active=1 AND c.concept_status='active'
                    ORDER BY g.goal_id,
                             CASE l.skos_property_uri
                               WHEN 'http://www.w3.org/2004/02/skos/core#prefLabel' THEN 0
                               ELSE 1 END,
                             p.confidence DESC,length(p.phrase)
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT g.goal_id, g.family, g.operation, g.description, g.risk_class,
                           g.terminal_action_policy, p.locale, p.phrase, p.phrase_kind,
                           p.confidence, '' AS concept_uri, g.goal_id AS notation,
                           '' AS skos_property_uri, p.locale AS language_tag
                    FROM goals AS g
                    LEFT JOIN goal_phrases AS p ON p.goal_id = g.goal_id
                    WHERE g.active = 1
                    ORDER BY g.goal_id, p.confidence DESC, length(p.phrase)
                    """
                ).fetchall()
        catalog: dict[str, dict[str, object]] = {}
        for row in rows:
            goal_id = str(row["goal_id"])
            item = catalog.setdefault(
                goal_id,
                {
                    "goal_id": goal_id,
                    "family": str(row["family"]),
                    "operation": str(row["operation"]),
                    "description": str(row["description"]),
                    "risk_class": str(row["risk_class"]),
                    "terminal_action_policy": str(row["terminal_action_policy"]),
                    "concept_uri": str(row["concept_uri"] or ""),
                    "notation": str(row["notation"] or goal_id),
                    "positive_phrases": [],
                    "negative_phrases": [],
                },
            )
            phrase = str(row["phrase"] or "").strip()
            phrase_locale = str(row["language_tag"] or row["locale"] or "").casefold()
            if not phrase or phrase_locale not in {locale.casefold(), locale_prefix, "*"}:
                continue
            key = "negative_phrases" if str(row["phrase_kind"]) == "negative" else "positive_phrases"
            phrases = item[key]
            assert isinstance(phrases, list)
            if phrase not in phrases and len(phrases) < 12:
                phrases.append(phrase)
        return tuple(catalog[goal_id] for goal_id in sorted(catalog))

    def goal_by_id(
        self,
        goal_id: str,
        *,
        confidence: float = 1.0,
        matched_phrase: str = "validated_goal_id",
    ) -> NormalizedGoal | None:
        """Validate a model/session goal ID against the active DB catalog."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT goal_id, family, operation, terminal_action_policy
                FROM goals WHERE goal_id = ? AND active = 1
                """,
                (goal_id,),
            ).fetchone()
        if row is None:
            return None
        return NormalizedGoal(
            goal_id=str(row["goal_id"]),
            family=str(row["family"]),
            operation=str(row["operation"]),
            confidence=round(max(0.0, min(1.0, confidence)), 4),
            matched_phrase=matched_phrase[:500],
            terminal_action_policy=str(row["terminal_action_policy"]),
        )

    def normalize_goal(self, goal_text: str, *, locale: str = "ko-KR") -> NormalizedGoal | None:
        normalized = normalize_text(goal_text)
        if not normalized:
            return None
        locale_prefix = locale.split("-", 1)[0].casefold()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT p.goal_id, p.locale, p.phrase, p.normalized_phrase, p.phrase_kind, p.confidence,
                       g.family, g.operation, g.terminal_action_policy
                FROM goal_phrases AS p
                JOIN goals AS g ON g.goal_id = p.goal_id
                WHERE g.active = 1
                """
            ).fetchall()
        scored: list[tuple[float, sqlite3.Row]] = []
        goal_tokens = set(tokenize(normalized))
        token_goal_ids: dict[str, set[str]] = {}
        for candidate_row in rows:
            for token in tokenize(str(candidate_row["normalized_phrase"])):
                token_goal_ids.setdefault(token, set()).add(str(candidate_row["goal_id"]))
        for row in rows:
            phrase = str(row["normalized_phrase"])
            phrase_tokens = set(tokenize(phrase))
            containment = 1.0 if phrase and phrase in normalized else 0.0
            token_recall = (
                len(goal_tokens & phrase_tokens) / len(phrase_tokens) if phrase_tokens else 0.0
            )
            sequence = SequenceMatcher(None, normalized, phrase).ratio()
            discriminative_hit = any(
                token in phrase_tokens and len(token_goal_ids.get(token, ())) == 1
                for token in goal_tokens
            )
            row_locale = str(row["locale"]).casefold()
            locale_weight = (
                1.0
                if row_locale in {locale.casefold(), locale_prefix, "*"}
                else 0.92
            )
            score = max(
                containment * 0.98,
                token_recall * 0.88,
                sequence * 0.76,
                0.86 if discriminative_hit else 0.0,
            )
            score *= float(row["confidence"]) * locale_weight
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

    def infer_affordance_role_scores(
        self,
        text: str,
        *,
        locale: str = "ko-KR",
        negative_context: str = "",
    ) -> dict[str, float]:
        normalized = normalize_text(text)
        if not normalized:
            return {}
        normalized_context = normalize_text(" ".join((text, negative_context)))
        locale_prefix = locale.split("-", 1)[0].casefold()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT role_id, locale, normalized_alias, confidence, negative_context_json
                FROM affordance_role_aliases
                ORDER BY confidence DESC, length(normalized_alias) DESC
                """
            ).fetchall()
        scored: dict[str, float] = {}
        for row in rows:
            alias = str(row["normalized_alias"])
            if not alias or alias not in normalized:
                continue
            negatives = tuple(json.loads(row["negative_context_json"] or "[]"))
            if any(normalize_text(str(value)) in normalized_context for value in negatives):
                continue
            role_id = str(row["role_id"])
            row_locale = str(row["locale"]).casefold()
            locale_weight = 1.0 if row_locale in {locale.casefold(), locale_prefix, "*"} else 0.92
            scored[role_id] = max(
                scored.get(role_id, 0.0),
                float(row["confidence"]) * locale_weight,
            )
        return {
            role: round(score, 4)
            for role, score in sorted(scored.items(), key=lambda item: (-item[1], item[0]))
        }

    def infer_affordance_roles(self, text: str, *, locale: str = "ko-KR") -> tuple[str, ...]:
        return tuple(self.infer_affordance_role_scores(text, locale=locale))

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
            icon_semantics = redact_text(str(_value(candidate, "icon_semantics", "")))
            nearby_text = redact_text(str(_value(candidate, "nearby_text", "")))
            parent_semantics = redact_text(str(_value(candidate, "parent_semantics", "")))
            child_semantics = redact_text(str(_value(candidate, "child_semantics", "")))
            visual_role = redact_text(str(_value(candidate, "visual_role", "")))
            visual_region = redact_text(str(_value(candidate, "visual_region", "")))
            visual_relevance_value = _value(candidate, "visual_relevance", None)
            visual_relevance = (
                None
                if visual_relevance_value is None
                else max(0.0, min(1.0, float(visual_relevance_value)))
            )
            position_bucket = str(_value(candidate, "position_bucket", "unknown"))
            clickable = bool(_value(candidate, "clickable", True))
            enabled = bool(_value(candidate, "enabled", True))
            selected = bool(_value(candidate, "selected", False))
            checked_value = _value(candidate, "checked", None)
            checked = None if checked_value is None else bool(checked_value)
            semantic_context = " ".join(
                value
                for value in (
                    label,
                    icon_semantics,
                    nearby_text,
                    parent_semantics,
                    child_semantics,
                    visual_role,
                    visual_region,
                )
                if value
            )
            field_role_scores: dict[str, float] = {}
            # A candidate's own label/icon is direct evidence. Nearby and
            # parent text are useful context, but must not make an unrelated
            # child inherit the parent's function at full strength.
            for field_text, field_weight in (
                (label, 1.0),
                (icon_semantics, 0.95),
                (nearby_text, 0.55),
                (parent_semantics, 0.35),
                (child_semantics, 0.75),
                (visual_role, 0.9),
                (visual_region, 0.2),
            ):
                for function_role, alias_score in self.infer_affordance_role_scores(
                    field_text,
                    locale=locale,
                    negative_context=semantic_context,
                ).items():
                    field_role_scores[function_role] = max(
                        field_role_scores.get(function_role, 0.0),
                        alias_score * field_weight,
                    )
            inferred_roles = tuple(
                role
                for role, score in sorted(
                    field_role_scores.items(),
                    key=lambda item: (-item[1], item[0]),
                )
                if score >= DIRECT_FUNCTION_ROLE_THRESHOLD
            )
            labels.append(label)
            screen_tokens.update(tokenize(semantic_context))
            screen_tokens.update(inferred_roles)
            role_counts[role] = role_counts.get(role, 0) + 1
            candidate_payloads.append(
                {
                    "candidate_id": candidate_id,
                    "label": label,
                    "role": role,
                    "risk_level": risk_level,
                    "icon_semantics": icon_semantics,
                    "nearby_text": nearby_text,
                    "parent_semantics": parent_semantics,
                    "child_semantics": child_semantics,
                    "visual_role": visual_role,
                    "visual_region": visual_region,
                    "visual_relevance": visual_relevance,
                    "position_bucket": position_bucket,
                    "clickable": clickable,
                    "enabled": enabled,
                    "selected": selected,
                    "checked": checked,
                    "dangerous_final": (
                        is_state_changing_action_label(label)
                        or is_dangerous_final_candidate(semantic_context)
                    ),
                    "inferred_function_roles": list(inferred_roles),
                    "function_role_scores": {
                        role: round(score, 4)
                        for role, score in sorted(field_role_scores.items())
                    },
                }
            )
        joined = " ".join((title, *labels)).casefold()
        auth_state = "unknown"
        if any(token in joined for token in ("다시 로그인", "세션 만료", "reauth", "session expired")):
            auth_state = "reauthentication"
        elif any(
            token in joined
            for token in ("로그인", "회원가입", "sign in", "log in", "sign up")
        ):
            # A generic My Page tab is commonly visible while logged out. An
            # explicit login/signup affordance is therefore stronger evidence.
            auth_state = "logged_out"
        elif any(
            token in joined
            for token in ("로그아웃", "내 계정", "계정 관리", "sign out", "my account")
        ):
            auth_state = "logged_in"
        surface_type = "webview" if "webview" in activity else "native"
        semantic_payload = {
            "title": normalize_text(title),
            "auth_state": auth_state,
            "surface_type": surface_type,
            "navigation_depth": navigation_depth,
            "role_counts": role_counts,
            "tokens": sorted(screen_tokens),
            "candidate_states": sorted(
                (
                    normalize_text(str(item["label"])),
                    bool(item["selected"]),
                    item["checked"],
                )
                for item in candidate_payloads
                if bool(item["selected"]) or item["checked"] is not None
            ),
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
        normalized_goal: NormalizedGoal | None = None,
        resolve_goal_from_text: bool = True,
    ) -> DecisionMemoryQuery:
        screen = self.semantic_screen_state(
            window_title=window_title,
            activity_name=activity_name,
            candidates=candidates,
            locale=locale,
        )
        goal = normalized_goal
        if goal is None and resolve_goal_from_text:
            goal = self.normalize_goal(goal_text, locale=locale)
        if goal is None:
            return DecisionMemoryQuery(
                None,
                screen,
                (),
                (),
                {},
                {},
                {},
                0.0,
                self.metadata.get("standards_profile", "legacy-v1"),
            )
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
            if self.profile_enabled:
                rows = connection.execute(
                    f"""
                    SELECT v.*,
                           COALESCE((
                               SELECT er.source_type FROM evidence_records AS er
                               WHERE er.entity_type='decision_case' AND er.entity_id=v.case_id
                               ORDER BY er.confidence DESC,er.verification_count DESC LIMIT 1
                           ),v.source_type) AS profile_source_type,
                           COALESCE((
                               SELECT MAX(er.confidence) FROM evidence_records AS er
                               WHERE er.entity_type='decision_case' AND er.entity_id=v.case_id
                           ),v.evidence_weight) AS profile_confidence,
                           COALESCE((
                               SELECT MAX(er.verification_count) FROM evidence_records AS er
                               WHERE er.entity_type='decision_case' AND er.entity_id=v.case_id
                           ),1) AS profile_verification_count,
                           EXISTS(
                               SELECT 1 FROM evidence_records AS er
                               JOIN evidence_provenance AS ep ON ep.evidence_id=er.evidence_id
                               WHERE er.entity_type='decision_case' AND er.entity_id=v.case_id
                           ) AS provenance_validated
                    FROM verified_decision_cases AS v
                    WHERE v.goal_id = ? {app_filter}
                      AND v.connectivity_status IN ('observed', 'not_observed')
                    ORDER BY profile_confidence DESC,v.evidence_weight DESC
                    LIMIT 500
                    """,
                    params,
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""
                    SELECT v.*,v.source_type AS profile_source_type,
                           v.evidence_weight AS profile_confidence,
                           1 AS profile_verification_count,
                           0 AS provenance_validated
                    FROM verified_decision_cases AS v
                    WHERE v.goal_id = ? {app_filter}
                      AND v.connectivity_status IN ('observed', 'not_observed')
                    ORDER BY v.evidence_weight DESC
                    LIMIT 500
                    """,
                    params,
                ).fetchall()
        all_evidence = self._score_evidence(screen, rows)
        evidence = all_evidence[: max(0, top_k)]
        candidate_scores, candidate_confidence = self._score_current_candidates(
            goal,
            screen,
            all_evidence,
        )
        action_scores = self._score_non_click_actions(all_evidence)
        destination_match = _destination_match(
            screen.tokens,
            signatures,
            title=screen.title,
            candidate_payloads=screen.candidate_payloads,
        )
        return DecisionMemoryQuery(
            goal=goal,
            screen=screen,
            destination_signatures=signatures,
            evidence=tuple(evidence),
            candidate_scores=candidate_scores,
            candidate_confidence=candidate_confidence,
            action_scores=action_scores,
            destination_match=destination_match,
            standards_profile=self.metadata.get("standards_profile", "legacy-v1"),
        )

    def _score_evidence(
        self,
        screen: SemanticScreenState,
        rows: Iterable[sqlite3.Row],
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
            confidence = float(row["profile_confidence"])
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
                    scroll_direction=str(row["scroll_direction"] or ""),
                    selected_label=selected_label,
                    selected_role=str(row["chosen_role"] or ""),
                    function_roles=function_roles,
                    outcome_type=str(row["outcome_type"] or "unknown"),
                    progress_label=str(row["progress_label"] or "unknown"),
                    evidence_confidence=float(row["profile_confidence"]),
                    source_app_package=str(row["source_app_package"]),
                    source_type=str(row["profile_source_type"]),
                    verification_count=int(row["profile_verification_count"]),
                    provenance_validated=bool(row["provenance_validated"]),
                    screen_similarity=round(screen_overlap, 4),
                )
            )
        scored.sort(key=lambda item: (-item.score, item.case_id))
        return scored

    def _score_non_click_actions(
        self,
        evidence: Sequence[DecisionEvidence],
    ) -> dict[str, float]:
        if not self.profile_enabled:
            return {}
        positive: dict[str, list[float]] = {}
        negative: dict[str, list[float]] = {}
        for item in evidence:
            if item.action == "click":
                continue
            key = (
                f"scroll:{item.scroll_direction or 'down'}"
                if item.action == "scroll"
                else item.action
            )
            source_weight = {
                "human_gold": 1.0,
                "real_device": 0.95,
                "synthetic": 0.55,
                "model_inference": 0.4,
            }.get(item.source_type, 0.3)
            value = item.score * source_weight * item.evidence_confidence
            target = (
                positive
                if item.progress_label in {"advanced", "reached"}
                and item.outcome_type not in {"no_change", "wrong_destination", "infinite_feed"}
                else negative
            )
            target.setdefault(key, []).append(value)
        result: dict[str, float] = {}
        for key in sorted(set(positive) | set(negative)):
            supports = sorted(positive.get(key, ()), reverse=True)
            conflicts = sorted(negative.get(key, ()), reverse=True)
            if not supports:
                result[key] = 0.0
                continue
            strongest = supports[0]
            repeated_support = min(1.0, len(supports) / 2.0)
            conflict = conflicts[0] if conflicts else 0.0
            result[key] = round(
                max(0.0, min(1.0, strongest * 0.86 + repeated_support * 0.14 - conflict * 0.8)),
                4,
            )
        return result

    def _score_current_candidates(
        self,
        goal: NormalizedGoal,
        screen: SemanticScreenState,
        evidence: Sequence[DecisionEvidence],
    ) -> tuple[dict[str, float], dict[str, CandidateMemoryConfidence]]:
        priors = GOAL_ROLE_PRIORS.get(goal.goal_id, {})
        scores: dict[str, float] = {}
        confidences: dict[str, CandidateMemoryConfidence] = {}
        ontology_scores = {
            str(candidate["candidate_id"]): _candidate_ontology_score(candidate, priors)
            for candidate in screen.candidate_payloads
        }
        for candidate in screen.candidate_payloads:
            candidate_id = str(candidate["candidate_id"])
            label = str(candidate["label"])
            roles = set(candidate["inferred_function_roles"])  # type: ignore[arg-type]
            ontology = _candidate_ontology_score(candidate, priors)
            memory_support = 0.0
            failure_support = 0.0
            positive_matches: list[tuple[float, DecisionEvidence]] = []
            negative_matches: list[tuple[float, DecisionEvidence]] = []
            for item in evidence:
                if item.action != "click":
                    continue
                label_score = text_similarity(label, item.selected_label)
                role_score = jaccard(roles, set(item.function_roles))
                support = item.score * (label_score * 0.58 + role_score * 0.42)
                if item.outcome_type in {"no_change", "wrong_destination", "infinite_feed"}:
                    failure_support = max(failure_support, support)
                    if support >= 0.18:
                        negative_matches.append((support, item))
                else:
                    memory_support = max(memory_support, support)
                    if item.progress_label in {"advanced", "reached"} and support >= 0.18:
                        positive_matches.append((support, item))
            lexical = text_similarity(goal.goal_id.replace(".", " "), label)
            score = max(ontology * 0.72 + memory_support * 0.28, memory_support * 0.82, lexical * 0.25)
            source_quality = {
                "human_gold": 1.0,
                "real_device": 0.95,
                "synthetic": 0.55,
                "model_inference": 0.4,
            }
            supporting_apps = {
                item.source_app_package
                for _, item in positive_matches
                if item.source_app_package
            }
            verified_apps = {
                item.source_app_package
                for _, item in positive_matches
                if item.provenance_validated
                and item.source_type in {"human_gold", "real_device"}
                and item.source_app_package
            }
            provenance_quality = max(
                (
                    source_quality.get(item.source_type, 0.3)
                    * item.evidence_confidence
                    * min(1.0, 0.7 + item.verification_count * 0.1)
                    for _, item in positive_matches
                ),
                default=0.0,
            )
            if self.profile_enabled:
                app_coverage = min(1.0, len(verified_apps) / 2.0)
                score = max(
                    score * 0.86 + app_coverage * 0.08 + provenance_quality * 0.06,
                    memory_support * 0.72 + app_coverage * 0.16 + provenance_quality * 0.12,
                )
            # A recorded failure is negative evidence, never a weak positive
            # example. Exact cross-app failure similarity can veto the
            # candidate even when its generic role prior is attractive.
            score *= max(0.0, 1.0 - failure_support * 1.8)
            if failure_support >= max(0.32, memory_support + 0.08):
                score = 0.0
            if str(candidate["risk_level"]) in {"high", "blocked"}:
                score = min(score, 0.05)
            score = round(max(0.0, min(1.0, score)), 4)
            scores[candidate_id] = score

            direct_ontology = (
                ontology >= 0.95
                and sum(value >= 0.95 for value in ontology_scores.values()) == 1
            )
            cross_app_verified = (
                len(verified_apps) >= 2
                and len(positive_matches) >= 2
                and memory_support >= 0.38
            )
            single_app_exact = (
                len(verified_apps) >= 1
                and memory_support >= 0.72
                and ontology >= 0.78
            )
            if cross_app_verified:
                support_tier = "cross_app_verified"
            elif single_app_exact:
                support_tier = "single_app_exact"
            elif direct_ontology:
                support_tier = "ontology_direct"
            elif positive_matches:
                support_tier = "weak_experience"
            else:
                support_tier = "ontology_only"
            conflict_free = not negative_matches or failure_support < memory_support * 0.55
            safe_candidate = str(candidate["risk_level"]) == "low" and not bool(
                candidate["dangerous_final"]
            )
            fast_path_eligible = (
                self.profile_enabled
                and safe_candidate
                and conflict_free
                and (cross_app_verified or single_app_exact or direct_ontology)
            )
            reasons = [support_tier]
            if positive_matches:
                reasons.append(f"positive_cases={len(positive_matches)}")
                reasons.append(f"supporting_apps={len(supporting_apps)}")
            if negative_matches:
                reasons.append(f"conflicting_cases={len(negative_matches)}")
            if not safe_candidate:
                reasons.append("safety_gate_required")
            confidences[candidate_id] = CandidateMemoryConfidence(
                candidate_id=candidate_id,
                score=score,
                support_tier=support_tier,
                supporting_cases=len(positive_matches),
                supporting_apps=len(supporting_apps),
                conflicting_cases=len(negative_matches),
                provenance_quality=round(provenance_quality, 4),
                fast_path_eligible=fast_path_eligible,
                reasons=tuple(reasons),
            )
        return scores, confidences

    def recommend_action(self, query: DecisionMemoryQuery) -> tuple[str, str | None, str | None, float]:
        if query.goal is None:
            return "wait_and_observe", None, None, 0.0
        destination_threshold = min(
            (
                float(signature.get("threshold", 0.72))
                for signature in query.destination_signatures
            ),
            default=0.72,
        )
        if query.destination_match >= destination_threshold:
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


def _candidate_ontology_score(
    candidate: Mapping[str, object],
    priors: Mapping[str, float],
) -> float:
    role_scores = candidate.get("function_role_scores", {})
    if isinstance(role_scores, Mapping) and role_scores:
        return max(
            (
                priors.get(str(role), 0.0) * float(alias_score)
                for role, alias_score in role_scores.items()
            ),
            default=0.0,
        )
    roles = candidate.get("inferred_function_roles", ())
    return max(
        (priors.get(str(role), 0.0) for role in roles),  # type: ignore[union-attr]
        default=0.0,
    )


def redact_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").translate(ZERO_WIDTH)
    value = EMAIL_PATTERN.sub("[email]", value)
    value = USER_HANDLE_PATTERN.sub("[account]", value)
    value = MASKED_KOREAN_NAME_PATTERN.sub("[account]", value)
    value = PHONE_PATTERN.sub("[phone]", value)
    value = CURRENCY_AMOUNT_PATTERN.sub("[amount]", value)
    value = LONG_NUMBER_PATTERN.sub("[number]", value)
    return " ".join(value.split())[:500]


def is_dangerous_final_candidate(label: str) -> bool:
    normalized = normalize_text(label)
    return any(phrase in normalized for phrase in DANGEROUS_FINAL_PHRASES)


def is_state_changing_action_label(label: str) -> bool:
    """Return true only when the candidate's own label commits a mutation."""

    return normalize_text(label) in STATE_CHANGING_ACTION_LABELS


def tokenize(value: str) -> tuple[str, ...]:
    return tuple(_stem_token(token) for token in TOKEN_PATTERN.findall(normalize_text(value)))


def _stem_token(token: str) -> str:
    if not any("\uac00" <= character <= "\ud7a3" for character in token):
        return token
    for suffix in KOREAN_TOKEN_SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix) + 1:
            return token[: -len(suffix)]
    return token


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


def _destination_match(
    tokens: Sequence[str],
    signatures: Sequence[dict[str, object]],
    *,
    title: str = "",
    candidate_payloads: Sequence[Mapping[str, object]] = (),
) -> float:
    # Function-role IDs (for example ``membership.plan``) are useful for
    # cross-app retrieval, but they are not screen evidence. Including them
    # here can satisfy both "membership" and "plan" without either word being
    # visible to the user.
    visible_tokens = {token for token in tokens if "." not in token}

    def feature_present(value: object, region: set[str] | None = None) -> bool:
        # Screen tokens are stored as a sorted set, so phrase substring checks
        # lose the original word order.  A semantic feature is present when all
        # of its normalized tokens are visible on the screen.
        feature_tokens = set(tokenize(str(value)))
        return bool(feature_tokens) and feature_tokens.issubset(
            visible_tokens if region is None else region
        )

    title_tokens = set(tokenize(title))
    semantic_regions = [title_tokens]
    for candidate in candidate_payloads:
        candidate_context = " ".join(
            str(candidate.get(field, ""))
            for field in (
                "label",
                "icon_semantics",
                "nearby_text",
                "parent_semantics",
                "child_semantics",
                "visual_role",
                "visual_region",
            )
        )
        semantic_regions.append(title_tokens | set(tokenize(candidate_context)))

    best = 0.0
    for signature in signatures:
        required = signature.get("required_features", {})
        optional = signature.get("optional_features", [])
        forbidden = signature.get("forbidden_features", [])
        terminal = signature.get("terminal_features", [])
        groups = required.get("any_groups", []) if isinstance(required, dict) else []
        required_score = (
            sum(any(feature_present(term) for term in group) for group in groups)
            / len(groups)
            if groups
            else 0.0
        )
        required_cooccurs = (
            len(groups) <= 1
            or any(
                all(
                    any(feature_present(term, region) for term in group)
                    for group in groups
                )
                for region in semantic_regions
            )
        )
        optional_values = list(optional) if isinstance(optional, list) else []
        optional_score = (
            sum(feature_present(term) for term in optional_values) / len(optional_values)
            if optional_values
            else 0.0
        )
        terminal_values = list(terminal) if isinstance(terminal, list) else []
        terminal_score = max((feature_present(term) for term in terminal_values), default=False)
        forbidden_values = list(forbidden) if isinstance(forbidden, list) else []
        forbidden_hit = any(feature_present(term) for term in forbidden_values)
        score = required_score * 0.70 + optional_score * 0.18 + float(terminal_score) * 0.12
        if not required_cooccurs and forbidden_hit:
            score *= 0.45
        if forbidden_hit:
            score *= 0.2
        best = max(best, score)
    return round(min(1.0, best), 4)
