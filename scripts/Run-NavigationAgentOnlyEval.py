from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.config import Settings  # noqa: E402
from app.services.android_control_index import AndroidControlIndex  # noqa: E402
from app.services.navigation_agent_only_evaluation import (  # noqa: E402
    TrainingFunctionGraphEvidenceIndex,
    evaluate_agent_only_policy,
    evaluate_agent_only_trajectories,
    write_agent_only_report,
    write_agent_only_trajectory_report,
)
from app.services.navigation_gold_retrieval import HumanGoldEvidenceIndex  # noqa: E402
from app.services.navigation_policy_reranker import NavigationPolicyReranker  # noqa: E402
from app.services.navigation_training_examples import read_materialized_examples  # noqa: E402
from app.services.universal_navigation_agent import (  # noqa: E402
    DeterministicNavigationDecisionProvider,
    ExaoneNavigationDecisionProvider,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Leakage-controlled Agent-only policy evaluation; no Gold or route replay."
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", choices=("heuristic", "exaone"), default="heuristic")
    parser.add_argument("--split", choices=("train", "validation", "test"), default="test")
    parser.add_argument("--max-examples", type=int, default=0)
    parser.add_argument("--android-control-index", type=Path)
    parser.add_argument("--without-gold-evidence", action="store_true")
    parser.add_argument("--without-android-control", action="store_true")
    parser.add_argument("--without-function-graph", action="store_true")
    parser.add_argument(
        "--leave-one-app-out",
        action="store_true",
        help="Exclude every example from the evaluated app from Gold/graph retrieval.",
    )
    parser.add_argument(
        "--allow-same-app-evidence",
        action="store_true",
        help=(
            "Run the weaker leave-one-route-out benchmark. Test-split runs are "
            "leave-one-app-out by default unless this flag is explicit."
        ),
    )
    parser.add_argument("--policy-reranker", type=Path)
    parser.add_argument("--reranker-max-candidates", type=int, default=5)
    parser.add_argument(
        "--trajectory",
        action="store_true",
        help="Roll out grouped held-out screen sequences and stop on the first wrong action.",
    )
    args = parser.parse_args()

    if not args.database.is_file():
        parser.error(f"evaluation database does not exist: {args.database}")
    if args.android_control_index and not args.android_control_index.is_file():
        parser.error(
            f"AndroidControl index does not exist: {args.android_control_index}"
        )

    examples = list(read_materialized_examples(args.database, splits=[args.split]))
    if args.max_examples > 0:
        examples = examples[: args.max_examples]
    if not examples:
        raise RuntimeError(
            f"no materialized navigation examples found for split={args.split!r} "
            f"in {args.database}"
        )
    settings = Settings(navigation_agent_provider="exaone" if args.provider == "exaone" else "mock")
    if args.provider == "exaone":
        provider = ExaoneNavigationDecisionProvider(settings)
        policy_reranker = (
            NavigationPolicyReranker.load(args.policy_reranker.resolve())
            if args.policy_reranker
            else None
        )

        def planner(goal, request, candidates, graph_hints, demonstrations, allow_mark_destination):
            planner_candidates = candidates
            planner_hints = graph_hints
            if policy_reranker is not None and candidates:
                ranked = policy_reranker.rank(
                    goal_text=goal,
                    request=request,
                    candidates=candidates,
                    graph_hints=graph_hints,
                    demonstrations=demonstrations,
                )
                planner_candidates = policy_reranker.shortlist(
                    ranked,
                    max_candidates=max(1, args.reranker_max_candidates),
                    decisive_score=0.62,
                    decisive_margin=0.07,
                )
                planner_hints = [
                    {
                        "source": "learned_policy_reranker",
                        "evidence_only": True,
                        "shortlisted_candidate_ids": [
                            candidate.element_id for candidate in planner_candidates
                        ],
                        "candidate_scores": [item.prompt_payload() for item in ranked[:10]],
                    },
                    *graph_hints,
                ]
            return provider.plan_exploration_step(
                goal_text=goal,
                request=request,
                candidates=planner_candidates,
                graph_hints=planner_hints,
                demonstrations=demonstrations,
                allow_scroll=False,
                allow_back=False,
                allow_mark_destination=allow_mark_destination,
            )
    else:
        provider = DeterministicNavigationDecisionProvider()

        def planner(goal, request, candidates, graph_hints, demonstrations, allow_mark_destination):
            decision = provider.decide(
                goal_text=goal,
                request=request,
                candidates=candidates,
                graph_hints=graph_hints,
                demonstrations=demonstrations,
            )
            return {
                "command": (
                    "mark_destination"
                    if allow_mark_destination or decision.goal_reached
                    else ("click" if decision.selected_element_id else "stop_for_user")
                ),
                "selected_element_id": decision.selected_element_id or "",
                "alternative_candidate_ids": [],
                "confidence": decision.confidence,
            }

    gold_index = None if args.without_gold_evidence else HumanGoldEvidenceIndex(args.database)
    function_graph_index = (
        None
        if args.without_function_graph
        else TrainingFunctionGraphEvidenceIndex(
            read_materialized_examples(args.database, splits=["train"])
        )
    )
    android_index = None
    if not args.without_android_control and args.android_control_index:
        android_index = AndroidControlIndex(args.android_control_index)
    leave_one_app_out = bool(
        args.leave_one_app_out
        or (args.split == "test" and not args.allow_same_app_evidence)
    )
    evaluator = evaluate_agent_only_trajectories if args.trajectory else evaluate_agent_only_policy
    report = evaluator(
        examples=examples,
        planner=planner,
        gold_index=gold_index,
        android_control_index=android_index,
        function_graph_index=function_graph_index,
        include_gold_evidence=not args.without_gold_evidence,
        include_android_control=not args.without_android_control,
        include_function_graph=not args.without_function_graph,
        leave_one_app_out=leave_one_app_out,
    )
    report["provider"] = args.provider
    report["split"] = args.split
    report["configuration"] = {
        "human_gold_evidence": not args.without_gold_evidence,
        "android_control": android_index is not None,
        "function_graph": function_graph_index is not None,
        "vlm": False,
        "policy_reranker": bool(args.policy_reranker),
        "leave_one_app_out": leave_one_app_out,
    }
    if args.trajectory:
        write_agent_only_trajectory_report(report, args.output)
    else:
        write_agent_only_report(report, args.output)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
