#!/usr/bin/env python3
"""Train a portable pairwise candidate reranker from reviewed Human Gold."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_agent_only_evaluation import (  # noqa: E402
    _mutated_candidates,
    _request,
)
from app.services.navigation_gold_retrieval import HumanGoldEvidenceIndex  # noqa: E402
from app.services.navigation_policy_reranker import (  # noqa: E402
    NavigationPolicyReranker,
    candidate_feature_vectors,
    train_pairwise_reranker,
    write_reranker_artifact,
)
from app.services.navigation_training_examples import (  # noqa: E402
    NavigationTrainingExample,
    read_materialized_examples,
)


MUTATIONS = ("original", "order_reversed", "label_synonym", "unnamed_target", "dangerous_decoy")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-split", action="append", default=["train"])
    parser.add_argument("--validation-split", default="validation")
    args = parser.parse_args()

    database = args.database.resolve()
    gold_index = HumanGoldEvidenceIndex(database)
    indexed = gold_index.rebuild()
    training = list(read_materialized_examples(database, splits=args.train_split))
    validation = list(read_materialized_examples(database, splits=[args.validation_split]))
    training_ids = {example.example_id for example in training}
    pairs: list[tuple[dict[str, float], dict[str, float]]] = []
    used_examples = 0
    for example in training:
        if _correct_candidate_id(example):
            used_examples += 1
            pairs.extend(_example_pairs(example, gold_index, training_ids))

    source_sha256 = hashlib.sha256(database.read_bytes()).hexdigest()
    artifact = train_pairwise_reranker(
        pairs,
        training_examples=used_examples,
        source_sha256=source_sha256,
    )
    reranker = NavigationPolicyReranker(artifact)
    metrics = {
        **artifact.metrics,
        "train_top1_accuracy": _top1_accuracy(training, reranker, gold_index, training_ids),
        "validation_top1_accuracy": _top1_accuracy(
            validation, reranker, gold_index, training_ids
        ),
        "indexed_gold_examples": float(indexed),
    }
    artifact = artifact.__class__(
        weights=artifact.weights,
        training_examples=artifact.training_examples,
        training_pairs=artifact.training_pairs,
        source_sha256=artifact.source_sha256,
        created_at=artifact.created_at,
        metrics=metrics,
    )
    artifact_sha256 = write_reranker_artifact(artifact, args.output.resolve())
    print(
        json.dumps(
            {
                "artifact": str(args.output.resolve()),
                "artifact_sha256": artifact_sha256,
                "training_examples": used_examples,
                "training_pairs": len(pairs),
                "metrics": metrics,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _example_pairs(
    example: NavigationTrainingExample,
    gold_index: HumanGoldEvidenceIndex,
    allowed_evidence_ids: set[str],
) -> list[tuple[dict[str, float], dict[str, float]]]:
    expected_id = _correct_candidate_id(example)
    result: list[tuple[dict[str, float], dict[str, float]]] = []
    for mutation in MUTATIONS:
        candidates = _mutated_candidates(example, mutation)
        request = _request(example, candidates, mutation)
        evidence = _gold_payloads(example, candidates, gold_index, allowed_evidence_ids)
        features = candidate_feature_vectors(
            goal_text=example.goal_text,
            request=request,
            candidates=candidates,
            graph_hints=evidence,
            demonstrations=[],
        )
        positive = features.get(expected_id)
        if positive is None:
            continue
        result.extend(
            (positive, features[candidate.element_id])
            for candidate in candidates
            if candidate.element_id != expected_id
        )
    return result


def _top1_accuracy(
    examples: list[NavigationTrainingExample],
    reranker: NavigationPolicyReranker,
    gold_index: HumanGoldEvidenceIndex,
    allowed_evidence_ids: set[str],
) -> float:
    correct = 0
    total = 0
    for example in examples:
        expected_id = _correct_candidate_id(example)
        if not expected_id:
            continue
        for mutation in MUTATIONS:
            candidates = _mutated_candidates(example, mutation)
            request = _request(example, candidates, mutation)
            ranked = reranker.rank(
                goal_text=example.goal_text,
                request=request,
                candidates=candidates,
                graph_hints=_gold_payloads(
                    example, candidates, gold_index, allowed_evidence_ids
                ),
                demonstrations=[],
            )
            total += 1
            correct += bool(ranked and ranked[0].candidate.element_id == expected_id)
    return round(correct / total, 6) if total else 0.0


def _gold_payloads(
    example: NavigationTrainingExample,
    candidates,
    index: HumanGoldEvidenceIndex,
    allowed_ids: set[str],
) -> list[dict[str, object]]:
    rows = index.search(
        goal_text=example.goal_text,
        target_function=example.target_function,
        app_package=example.app_package,
        app_version=example.app_version,
        locale=example.locale,
        screen_text=str(
            example.screen_context.get("title")
            or example.screen_context.get("window_title")
            or ""
        ),
        candidate_labels=[candidate.label for candidate in candidates],
        top_k=80,
        exclude_recording_ids=[example.source_recording_id],
    )
    history = {
        "source": "current_session_history",
        "evidence_only": True,
        "never_replay_as_macro": True,
        "steps": [
            {
                "screen_fingerprint": str(step.get("screen_fingerprint", "")),
                "screen_title": str(step.get("screen_title", "")),
                "selected_label": str(step.get("selected_label", "")),
                "selected_role": str(step.get("selected_role", "")),
                "target_function": str(step.get("target_function", "")),
                "outcome": str(step.get("outcome", "")),
            }
            for step in example.history[-8:]
            if isinstance(step, dict)
        ],
    }
    return [history, *[
        row.prompt_payload() for row in rows if row.example_id in allowed_ids
    ][:5]]


def _correct_candidate_id(example: NavigationTrainingExample) -> str:
    if example.correct_action.get("name") not in {"click", "click_element"}:
        return ""
    arguments = example.correct_action.get("arguments", {})
    return str(arguments.get("candidate_id", "")) if isinstance(arguments, dict) else ""


if __name__ == "__main__":
    raise SystemExit(main())
