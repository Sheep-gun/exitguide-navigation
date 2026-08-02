from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from app.schemas import UniversalNavigationCandidate, UniversalNavigationObserveRequest
from app.services.navigation_policy_reranker import (
    FEATURE_NAMES,
    NavigationPolicyReranker,
    candidate_feature_vectors,
    train_pairwise_reranker,
    write_reranker_artifact,
)


def main() -> None:
    positive = {name: 0.0 for name in FEATURE_NAMES}
    negative = {name: 0.0 for name in FEATURE_NAMES}
    positive["independent_semantic_score"] = 0.9
    positive["gold_exact_label"] = 1.0
    positive["low_risk"] = 1.0
    negative["content_role"] = 1.0
    negative["low_risk"] = 1.0
    artifact = train_pairwise_reranker(
        [(positive, negative)] * 12,
        training_examples=1,
        source_sha256="a" * 64,
        epochs=20,
    )
    assert artifact.weights["gold_exact_label"] > 0
    assert artifact.weights["content_role"] < 0

    with TemporaryDirectory() as temporary_directory:
        path = Path(temporary_directory) / "policy-reranker.json"
        artifact_sha256 = write_reranker_artifact(artifact, path)
        assert artifact_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
        reranker = NavigationPolicyReranker.load(path)
        request = UniversalNavigationObserveRequest.model_validate(
            {
                "request_id": "reranker-test",
                "session_id": "reranker-test",
                "app_package": "com.example",
                "app_version": "1",
                "locale": "ko-KR",
                "goal_text": "알림 설정을 열고 싶어",
                "operation_mode": "explore",
                "screen": {
                    "window_title": "홈",
                    "elements": [
                        {
                            "id": "settings",
                            "text": "알림 설정",
                            "role": "button",
                            "clickable": True,
                            "enabled": True,
                            "visible": True,
                            "bounds": [0, 100, 100, 200],
                        },
                        {
                            "id": "video",
                            "text": "추천 영상",
                            "role": "video",
                            "clickable": True,
                            "enabled": True,
                            "visible": True,
                            "bounds": [0, 300, 100, 400],
                        },
                    ],
                },
            }
        )
        candidates = [
            UniversalNavigationCandidate(
                element_id="settings",
                element_key="settings",
                label="알림 설정",
                role="button",
                risk_level="low",
            ),
            UniversalNavigationCandidate(
                element_id="video",
                element_key="video",
                label="추천 영상",
                role="video",
                risk_level="low",
            ),
        ]
        subscription_features = candidate_feature_vectors(
            goal_text="구독을 해지하고 싶어",
            request=request.model_copy(update={"goal_text": "구독을 해지하고 싶어"}),
            candidates=candidates,
            graph_hints=[],
            demonstrations=[],
        )
        assert subscription_features["settings"]["direct_goal_domain_conflict"] == 1.0
        assert subscription_features["video"]["direct_goal_domain_conflict"] == 0.0
        ranked = reranker.rank(
            goal_text=request.goal_text,
            request=request,
            candidates=candidates,
            graph_hints=[
                {
                    "source": "human_gold",
                    "historically_chosen_label": "알림 설정",
                    "retrieval_score": 8.0,
                }
            ],
            demonstrations=[],
        )
        assert ranked[0].candidate.element_id == "settings"
        assert reranker.shortlist(ranked, decisive_score=0.5, decisive_margin=0.01) == [
            candidates[0]
        ]
    print("navigation policy reranker checks ok")


if __name__ == "__main__":
    main()
