from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from app.schemas import UniversalNavigationCandidate, UniversalNavigationObserveRequest
from app.services.android_control_index import AndroidControlEvidence
from app.services.navigation_semantics import (
    candidate_contexts,
    infer_goal_plan,
    text_similarity,
)


SCHEMA_VERSION = 1
FEATURE_NAMES = (
    "independent_semantic_score",
    "gold_label_similarity",
    "gold_exact_label",
    "graph_label_similarity",
    "android_control_support",
    "goal_label_similarity",
    "terminal_function_match",
    "preferred_function_match",
    "content_role",
    "structurally_unlabeled",
    "position_top",
    "position_middle",
    "position_bottom",
    "low_risk",
    "back_navigation_label",
    "structural_top_label",
    "structural_middle_label",
    "structural_bottom_label",
    "notification_target_direct_label",
    "notification_target_general_gateway",
    "account_goal_top_icon",
    "repeats_recent_history_label",
    "after_settings_general_gateway",
    "after_settings_notification_entry",
    "direct_goal_domain_conflict",
)
CONTENT_ROLES = frozenset({"card", "feed", "video", "article", "product"})
STRUCTURAL_MARKERS = (
    "이름 없는",
    "unlabeled",
    "unknown icon",
    "unnamed",
)
DIRECT_DOMAIN_MARKERS = {
    "notification": ("알림", "푸시", "notification", "alert"),
    "subscription": ("구독", "멤버십", "membership", "subscription", "premium"),
    "privacy": ("개인정보", "privacy", "personal data"),
    "payment": ("결제", "청구", "payment", "billing"),
    "order": ("주문", "order"),
    "refund": ("환불", "refund"),
}


@dataclass(frozen=True)
class PolicyRerankerArtifact:
    weights: dict[str, float]
    training_examples: int
    training_pairs: int
    source_sha256: str
    created_at: str
    metrics: dict[str, float]

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "model_type": "pairwise_logistic_linear_reranker",
            "feature_names": list(FEATURE_NAMES),
            "weights": {name: round(float(self.weights.get(name, 0.0)), 8) for name in FEATURE_NAMES},
            "training_examples": self.training_examples,
            "training_pairs": self.training_pairs,
            "source_sha256": self.source_sha256,
            "created_at": self.created_at,
            "metrics": self.metrics,
            "runtime_contract": {
                "reranks_current_screen_candidates_only": True,
                "never_replays_gold_route": True,
                "k_exaone_still_emits_hermes_action": True,
            },
        }


@dataclass(frozen=True)
class RankedPolicyCandidate:
    candidate: UniversalNavigationCandidate
    score: float
    features: dict[str, float]

    def prompt_payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate.element_id,
            "label": self.candidate.label,
            "policy_support_score": round(self.score, 6),
            "feature_evidence": {
                name: round(value, 5)
                for name, value in self.features.items()
                if abs(value) >= 0.00001
            },
        }


class NavigationPolicyReranker:
    """A small portable ranker trained from Gold preference pairs.

    The ranker has no route, coordinate, or click executor. It scores only
    candidates observed on the current screen. K-EXAONE remains responsible
    for producing the strict Hermes action from the bounded shortlist.
    """

    def __init__(self, artifact: PolicyRerankerArtifact) -> None:
        self.artifact = artifact

    @classmethod
    def load(cls, path: str | Path) -> "NavigationPolicyReranker":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(payload.get("schema_version", 0)) != SCHEMA_VERSION:
            raise ValueError("unsupported Navigation policy reranker schema")
        if tuple(payload.get("feature_names", ())) != FEATURE_NAMES:
            raise ValueError("Navigation policy reranker feature contract mismatch")
        weights = payload.get("weights")
        if not isinstance(weights, dict) or set(weights) != set(FEATURE_NAMES):
            raise ValueError("Navigation policy reranker weights are incomplete")
        artifact = PolicyRerankerArtifact(
            weights={name: float(weights[name]) for name in FEATURE_NAMES},
            training_examples=int(payload.get("training_examples", 0)),
            training_pairs=int(payload.get("training_pairs", 0)),
            source_sha256=str(payload.get("source_sha256", "")),
            created_at=str(payload.get("created_at", "")),
            metrics={
                str(key): float(value)
                for key, value in dict(payload.get("metrics", {})).items()
            },
        )
        return cls(artifact)

    def rank(
        self,
        *,
        goal_text: str,
        request: UniversalNavigationObserveRequest,
        candidates: Sequence[UniversalNavigationCandidate],
        graph_hints: Sequence[Mapping[str, object]],
        demonstrations: Sequence[AndroidControlEvidence],
    ) -> list[RankedPolicyCandidate]:
        features = candidate_feature_vectors(
            goal_text=goal_text,
            request=request,
            candidates=candidates,
            graph_hints=graph_hints,
            demonstrations=demonstrations,
        )
        ranked = [
            RankedPolicyCandidate(
                candidate=candidate,
                score=_sigmoid(_dot(self.artifact.weights, features[candidate.element_id])),
                features=features[candidate.element_id],
            )
            for candidate in candidates
        ]
        ranked.sort(key=lambda item: (-item.score, item.candidate.label, item.candidate.element_id))
        return ranked

    def shortlist(
        self,
        ranked: Sequence[RankedPolicyCandidate],
        *,
        max_candidates: int = 3,
        decisive_score: float = 0.62,
        decisive_margin: float = 0.10,
    ) -> list[UniversalNavigationCandidate]:
        if not ranked:
            return []
        if len(ranked) == 1:
            return [ranked[0].candidate]
        margin = ranked[0].score - ranked[1].score
        if ranked[0].score >= decisive_score and margin >= decisive_margin:
            return [ranked[0].candidate]
        return [item.candidate for item in ranked[: max(1, max_candidates)]]


def candidate_feature_vectors(
    *,
    goal_text: str,
    request: UniversalNavigationObserveRequest,
    candidates: Sequence[UniversalNavigationCandidate],
    graph_hints: Sequence[Mapping[str, object]],
    demonstrations: Sequence[AndroidControlEvidence],
) -> dict[str, dict[str, float]]:
    candidate_list = list(candidates)
    plan = infer_goal_plan(goal_text)
    contexts = candidate_contexts(
        request=request,
        candidates=candidate_list,
        demonstrations=list(demonstrations),
        plan=plan,
    )
    preferred = dict(plan.preferred_functions)
    gold_hints = [hint for hint in graph_hints if hint.get("source") == "human_gold"]
    transition_hints = [
        hint
        for hint in graph_hints
        if hint.get("source") not in {"human_gold", "current_session_history"}
    ]
    session_steps = [
        step
        for hint in graph_hints
        if hint.get("source") == "current_session_history"
        for step in hint.get("steps", [])
        if isinstance(step, dict)
    ]
    recent_history_labels = [
        str(step.get("selected_label", ""))
        for step in session_steps[-8:]
        if str(step.get("selected_label", "")).strip()
    ]
    last_history_label = recent_history_labels[-1].casefold() if recent_history_labels else ""
    result: dict[str, dict[str, float]] = {}
    for candidate in candidate_list:
        context = contexts[candidate.element_id]
        label_lower = candidate.label.casefold()
        is_back_navigation = _is_back_navigation_label(label_lower)
        gold_similarity = 0.0
        gold_exact = 0.0
        normalized_label = _normalize(candidate.label)
        for hint in gold_hints:
            historic_label = str(
                hint.get("historically_chosen_label")
                or hint.get("candidate_label")
                or ""
            )
            if not historic_label:
                continue
            retrieval = min(1.0, max(0.0, float(hint.get("retrieval_score", 1.0)) / 8.0))
            similarity = (
                0.0
                if is_back_navigation
                else text_similarity(candidate.label, historic_label) * retrieval
            )
            gold_similarity = max(gold_similarity, similarity)
            if (
                not is_back_navigation
                and normalized_label
                and normalized_label == _normalize(historic_label)
            ):
                gold_exact = max(gold_exact, retrieval)
        graph_similarity = 0.0
        for hint in transition_hints:
            historic_label = str(hint.get("label") or hint.get("candidate_label") or "")
            if not historic_label:
                continue
            successes = max(0.0, float(hint.get("success_count", 0.0)))
            failures = max(0.0, float(hint.get("failure_count", 0.0)))
            reliability = (successes + 1.0) / (successes + failures + 2.0)
            graph_similarity = max(
                graph_similarity,
                text_similarity(candidate.label, historic_label) * reliability,
            )
        function_scores = dict(context.function_matches)
        preferred_score = max(
            (
                weight
                * max(
                    function_scores.get(function_id, 0.0),
                    1.0 if function_id in context.function_tags else 0.0,
                )
                for function_id, weight in preferred.items()
            ),
            default=0.0,
        )
        terminal_match = max(
            function_scores.get(plan.terminal_function, 0.0),
            1.0 if plan.terminal_function in context.function_tags else 0.0,
        ) if plan.terminal_function else 0.0
        is_notification_target = plan.terminal_function.startswith("notification.")
        target_domain = plan.terminal_function.split(".", 1)[0]
        direct_label_domains = {
            domain
            for domain, markers in DIRECT_DOMAIN_MARKERS.items()
            if any(marker in label_lower for marker in markers)
        }
        is_account_or_settings_goal = plan.terminal_function.startswith(
            ("notification.", "subscription.", "account.", "privacy.", "payment.")
        )
        structural_top = any(
            marker in label_lower
            for marker in ("이름 없는 상단", "unlabeled top", "unnamed top")
        )
        structural_middle = any(
            marker in label_lower
            for marker in ("이름 없는 중앙", "unlabeled middle", "unnamed middle")
        )
        structural_bottom = any(
            marker in label_lower
            for marker in ("이름 없는 하단", "unlabeled bottom", "unnamed bottom")
        )
        result[candidate.element_id] = {
            "independent_semantic_score": context.semantic_score,
            "gold_label_similarity": gold_similarity,
            "gold_exact_label": gold_exact,
            "graph_label_similarity": graph_similarity,
            "android_control_support": context.demonstration_support,
            "goal_label_similarity": text_similarity(goal_text, candidate.label),
            "terminal_function_match": terminal_match,
            "preferred_function_match": preferred_score,
            "content_role": 1.0 if candidate.role.casefold() in CONTENT_ROLES else 0.0,
            "structurally_unlabeled": 1.0 if any(marker in label_lower for marker in STRUCTURAL_MARKERS) or not normalized_label else 0.0,
            "position_top": 1.0 if context.position == "top" else 0.0,
            "position_middle": 1.0 if context.position == "middle" else 0.0,
            "position_bottom": 1.0 if context.position == "bottom" else 0.0,
            "low_risk": 1.0 if candidate.risk_level == "low" else 0.0,
            "back_navigation_label": 1.0 if is_back_navigation else 0.0,
            "structural_top_label": 1.0 if structural_top else 0.0,
            "structural_middle_label": 1.0 if structural_middle else 0.0,
            "structural_bottom_label": 1.0 if structural_bottom else 0.0,
            "notification_target_direct_label": 1.0
            if is_notification_target
            and any(marker in label_lower for marker in ("알림", "푸시", "notification", "alert"))
            else 0.0,
            "notification_target_general_gateway": 1.0
            if is_notification_target
            and _normalize(candidate.label) in {"일반", "general"}
            else 0.0,
            "account_goal_top_icon": 1.0
            if is_account_or_settings_goal and structural_top
            else 0.0,
            "repeats_recent_history_label": max(
                (text_similarity(candidate.label, label) for label in recent_history_labels),
                default=0.0,
            ),
            "after_settings_general_gateway": 1.0
            if any(marker in last_history_label for marker in ("설정", "settings", "preference"))
            and _normalize(candidate.label) in {"일반", "general"}
            else 0.0,
            "after_settings_notification_entry": 1.0
            if any(
                marker in last_history_label
                for marker in ("설정", "settings", "preference", "일반", "general")
            )
            and any(marker in label_lower for marker in ("알림", "푸시", "notification", "alert"))
            else 0.0,
            "direct_goal_domain_conflict": 1.0
            if target_domain in DIRECT_DOMAIN_MARKERS
            and direct_label_domains
            and target_domain not in direct_label_domains
            else 0.0,
        }
    return result


def train_pairwise_reranker(
    pairs: Sequence[tuple[Mapping[str, float], Mapping[str, float]]],
    *,
    training_examples: int,
    source_sha256: str,
    epochs: int = 80,
    learning_rate: float = 0.08,
    l2: float = 0.002,
    seed: int = 5247,
) -> PolicyRerankerArtifact:
    if not pairs:
        raise ValueError("at least one positive/negative preference pair is required")
    weights = {name: 0.0 for name in FEATURE_NAMES}
    order = list(range(len(pairs)))
    generator = random.Random(seed)
    for epoch in range(max(1, epochs)):
        generator.shuffle(order)
        rate = learning_rate / math.sqrt(1.0 + epoch * 0.08)
        for index in order:
            positive, negative = pairs[index]
            delta = {
                name: float(positive.get(name, 0.0)) - float(negative.get(name, 0.0))
                for name in FEATURE_NAMES
            }
            probability = _sigmoid(_dot(weights, delta))
            for name in FEATURE_NAMES:
                weights[name] += rate * ((1.0 - probability) * delta[name] - l2 * weights[name])
    correct = 0
    loss = 0.0
    for positive, negative in pairs:
        delta = {
            name: float(positive.get(name, 0.0)) - float(negative.get(name, 0.0))
            for name in FEATURE_NAMES
        }
        probability = _sigmoid(_dot(weights, delta))
        correct += probability > 0.5
        loss -= math.log(max(1e-9, probability))
    return PolicyRerankerArtifact(
        weights=weights,
        training_examples=training_examples,
        training_pairs=len(pairs),
        source_sha256=source_sha256,
        created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        metrics={
            "training_pair_accuracy": round(correct / len(pairs), 6),
            "training_pair_log_loss": round(loss / len(pairs), 6),
        },
    )


def write_reranker_artifact(artifact: PolicyRerankerArtifact, path: str | Path) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(artifact.payload(), ensure_ascii=False, indent=2) + "\n"
    # ``Path.write_text`` uses platform newline translation on Windows, which
    # made the returned digest describe LF bytes while the artifact on disk
    # contained CRLF. Emit exact portable bytes so the manifest checksum is
    # reproducible on Windows and Linux.
    destination.write_bytes(serialized.encode("utf-8"))
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def _dot(weights: Mapping[str, float], features: Mapping[str, float]) -> float:
    return sum(float(weights.get(name, 0.0)) * float(features.get(name, 0.0)) for name in FEATURE_NAMES)


def _sigmoid(value: float) -> float:
    bounded = max(-40.0, min(40.0, value))
    return 1.0 / (1.0 + math.exp(-bounded))


def _normalize(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _is_back_navigation_label(value: str) -> bool:
    normalized = " ".join(value.split())
    return (
        normalized.startswith(("←", "‹", "<"))
        or normalized in {"뒤로", "위로 탐색", "back", "navigate up", "up navigation"}
        or "위로 탐색" in normalized
    )
