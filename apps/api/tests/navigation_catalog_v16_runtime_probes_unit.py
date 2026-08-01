from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
SCRIPTS = ROOT / "scripts"
for path in (API_ROOT, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.config import Settings  # noqa: E402
from app.schemas import UniversalNavigationObserveRequest  # noqa: E402
from app.services import universal_navigation_agent as agent_module  # noqa: E402
from app.services.navigation_function_catalog import (  # noqa: E402
    GOAL_GOVERNANCE_BLOCKED_INTENT,
    NavigationFunctionCatalog,
    _normalize,
)
from app.services.navigation_semantics import infer_goal_plan  # noqa: E402
from app.services.universal_navigation_agent import observe_universal_navigation  # noqa: E402
from app.services.universal_navigation_graph import (  # noqa: E402
    UniversalNavigationGraphRepository,
)
from navigation_alias_context_overrides import (  # noqa: E402
    apply_alias_context_overrides,
    strip_alias_context_overrides,
)
from navigation_catalog_v16_data import (  # noqa: E402
    REVIEWED_BY_DOMAIN,
    V16_FUNCTIONS,
    V16_INTENTS,
    build_collision_probes,
    build_role_asset_isolation_matrix,
    build_semantic_development_matrix,
    build_state_permission_recovery_matrix,
    load_base_catalog,
    merge_with_base,
)


def _safe_hub_plan(
    catalog: NavigationFunctionCatalog,
    *,
    terminal_function: str,
    preferred_functions: tuple[tuple[str, float], ...],
    expected_hub: str,
) -> bool:
    if terminal_function != expected_hub:
        return False
    if not preferred_functions:
        return False
    for function_id, _weight in preferred_functions:
        definition = catalog.function(function_id)
        if definition is None or definition.terminal or definition.state_changing:
            return False
    hub = catalog.function(expected_hub)
    return bool(
        hub is not None
        and hub.node_kind == "hub"
        and not hub.terminal
        and not hub.state_changing
        and hub.automation_policy == "safe_navigation"
        and hub.stop_policy == "continue"
    )


def main() -> None:
    base = load_base_catalog()
    reviewed = merge_with_base(base)
    # Match the production materializer: collision overrides are regenerated
    # only after V16 is appended, rather than reusing the V15-only ledger.
    runtime_payload = apply_alias_context_overrides(
        strip_alias_context_overrides(reviewed)
    )
    assert runtime_payload["catalog_version"] == "16.0.0"
    assert len(runtime_payload["functions"]) == 3118
    assert len(runtime_payload["intents"]) == 2900

    semantic_counts: Counter[str] = Counter()
    collision_counts: Counter[str] = Counter()
    recovery_counts: Counter[str] = Counter()
    isolation_counts: Counter[str] = Counter()
    boundary_counts: Counter[str] = Counter()
    dangerous_terminal_after_negative_evidence = 0
    negative_failures: list[dict[str, object]] = []
    recovery_failures: list[dict[str, object]] = []
    long_composite_counts: Counter[str] = Counter()
    long_composite_variant_counts: Counter[str] = Counter()
    exact_wrapper_counts: Counter[str] = Counter()
    markerless_class1_counts: Counter[str] = Counter()
    explicit_marker_class1_counts: Counter[str] = Counter()
    ambiguous_composite_counts: Counter[str] = Counter()

    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        catalog_path = root / "function-catalog.v16.runtime.json"
        catalog_path.write_text(
            json.dumps(runtime_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        shutil.copyfile(
            ROOT / "fixtures" / "navigation" / "function-equivalence.v1.json",
            root / "function-equivalence.v1.json",
        )
        catalog = NavigationFunctionCatalog(root / "runtime.sqlite", catalog_path)

        # Preserve a non-V16 exact legacy intent and its simple request wrapper.
        # The long-prose challenge must never reopen either class.
        v16_terminal_ids = {
            str(item["function_id"])
            for item in V16_FUNCTIONS
            if item["terminal"]
        }
        legacy_intent = next(
            item
            for item in runtime_payload["intents"]
            if item.get("terminal_function") not in v16_terminal_ids
            and item.get("patterns")
            and 5 <= len(str(item["patterns"][0])) <= 48
        )
        legacy_pattern = str(legacy_intent["patterns"][0])
        legacy_terminal = catalog.canonical_function_id(
            str(legacy_intent["terminal_function"])
        )
        for goal in (legacy_pattern, f"please {legacy_pattern}"):
            exact_wrapper_counts[
                "preserved"
                if catalog.plan_goal(goal).terminal_function == legacy_terminal
                else "changed"
            ] += 1

        # Development-only long/composite probes are derived from V16's public
        # definitions.  A sibling label is contextual noise; the explicit
        # purpose clause carries the target's role, asset, state, jurisdiction,
        # and stable function-key wording.  No independent fixture wording or
        # case identifier is consumed here.
        governed_by_domain: dict[str, list[dict[str, object]]] = {}
        for function in V16_FUNCTIONS:
            if function["terminal"]:
                governed_by_domain.setdefault(str(function["domain"]), []).append(function)
        generic_roles = {
            "button",
            "image_button",
            "link",
            "menuitem",
            "switch",
            "tab",
            "text",
            "authorized responsible role",
        }
        for domain, functions in sorted(governed_by_domain.items()):
            domain_spec = REVIEWED_BY_DOMAIN[domain]
            domain_name = domain_spec.root_en
            markerless_target = functions[0]
            markerless = (
                f"Reference workflow: {domain_name} {markerless_target['name_en']} "
                "is the reviewed destination in this operational note; guide only."
            )
            markerless_baseline = catalog._best_goal_match(
                _normalize(markerless),
                include_fuzzy=False,
            )
            markerless_plan = catalog.plan_goal(markerless)
            markerless_class1_counts[
                "preserved"
                if markerless_baseline[2][1] == 1
                and markerless_baseline[3] is not None
                and markerless_plan.terminal_function
                == markerless_target["function_id"]
                else "changed"
            ] += 1
            for target_index in (0, 7):
                target = functions[target_index]
                decoy = functions[(target_index + 1) % len(functions)]
                role = next(
                    value
                    for value in target["role_hints"]
                    if value not in generic_roles
                )
                asset = str(target["asset_cues"][-1])
                lifecycle = str(target["state_cues"]["lifecycle"][0])
                jurisdiction = str(target["state_cues"]["jurisdiction"][0])
                purpose = (
                    f"guide the {role} to the {asset} function while it is "
                    f"{lifecycle} under {jurisdiction} in {domain_name}"
                )
                variants = (
                    f"Context label: {decoy['name_en']}. My actual task is: {purpose}; guide only.",
                    f"My actual task is: {purpose}; guide only. Context label: {decoy['name_en']}.",
                    f"화면 문맥에는 {domain_spec.root_ko} {decoy['name_ko']}가 표시됩니다. "
                    f"실제 목적은 {purpose}; 안내만 해줘.",
                    f"실제 목적은 {purpose}; 안내만 해줘. "
                    f"참고 화면은 {domain_spec.root_ko} {decoy['name_ko']}입니다.",
                )
                for variant_index, text in enumerate(variants):
                    baseline = catalog._best_goal_match(
                        _normalize(text),
                        include_fuzzy=False,
                    )
                    explicit_marker_class1_counts[
                        "confirmed"
                        if baseline[2][1] == 1 and baseline[3] is not None
                        else "missing"
                    ] += 1
                    plan = catalog.plan_goal(text)
                    outcome = (
                        "target"
                        if plan.terminal_function == target["function_id"]
                        else (
                            "generic"
                            if plan.intent == "generic_navigation"
                            else "wrong"
                        )
                    )
                    long_composite_counts[outcome] += 1
                    long_composite_variant_counts[
                        f"variant_{variant_index}_{outcome}"
                    ] += 1

            first, second = functions[2], functions[3]
            ambiguous = (
                f"Context lists {first['name_en']} and {second['name_en']}. "
                f"My actual task is: review either {str(first['asset_cues'][-1])} "
                f"or {str(second['asset_cues'][-1])} in {domain_name}; guide only."
            )
            ambiguous_plan = catalog.plan_goal(ambiguous)
            ambiguous_composite_counts[
                "generic"
                if ambiguous_plan.intent == "generic_navigation"
                else "guessed"
            ] += 1

        for probe in build_semantic_development_matrix():
            plan = catalog.plan_goal(str(probe["text"]))
            expected = probe.get("expected_function")
            excluded = probe.get("excluded_function")
            if expected is not None:
                semantic_counts[
                    "positive_exact" if plan.terminal_function == expected else "positive_wrong"
                ] += 1
            else:
                consumer_plan = infer_goal_plan(str(probe["text"]), catalog)
                safe_negative = bool(
                    _safe_hub_plan(
                        catalog,
                        terminal_function=plan.terminal_function,
                        preferred_functions=plan.preferred_functions,
                        expected_hub=str(probe["allowed_fallback"]),
                    )
                    and plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT
                    and consumer_plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT
                    and consumer_plan.terminal_function == probe["allowed_fallback"]
                    and str(excluded) in consumer_plan.avoid_functions
                )
                dangerous_terminal_after_negative_evidence += int(not safe_negative)
                if not safe_negative:
                    negative_failures.append(
                        {
                            "text": probe["text"],
                            "excluded_function": excluded,
                            "allowed_fallback": probe["allowed_fallback"],
                            "catalog_intent": plan.intent,
                            "catalog_terminal": plan.terminal_function,
                            "consumer_intent": consumer_plan.intent,
                            "consumer_terminal": consumer_plan.terminal_function,
                            "consumer_avoid_functions": consumer_plan.avoid_functions,
                        }
                    )
                semantic_counts[
                    "negative_safe"
                    if safe_negative and plan.terminal_function != excluded
                    else "negative_terminal_selected"
                ] += 1

        for probe in build_collision_probes():
            plan = catalog.plan_goal(str(probe["text"]))
            collision_counts[
                "exact"
                if plan.terminal_function == probe["expected_function"]
                else "wrong"
            ] += 1

        for probe in build_state_permission_recovery_matrix():
            plan = catalog.plan_goal(str(probe["text"]))
            consumer_plan = infer_goal_plan(str(probe["text"]), catalog)
            recovery_safe = bool(
                _safe_hub_plan(
                    catalog,
                    terminal_function=plan.terminal_function,
                    preferred_functions=plan.preferred_functions,
                    expected_hub=str(probe["allowed_fallback"]),
                )
                and plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT
                and consumer_plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT
                and consumer_plan.terminal_function == probe["allowed_fallback"]
                and probe["excluded_function"] in consumer_plan.avoid_functions
            )
            recovery_counts["safe_hub" if recovery_safe else "unsafe_or_wrong"] += 1
            if not recovery_safe:
                recovery_failures.append(
                    {
                        "text": probe["text"],
                        "excluded_function": probe["excluded_function"],
                        "allowed_fallback": probe["allowed_fallback"],
                        "catalog_intent": plan.intent,
                        "catalog_terminal": plan.terminal_function,
                        "consumer_intent": consumer_plan.intent,
                        "consumer_terminal": consumer_plan.terminal_function,
                        "consumer_avoid_functions": consumer_plan.avoid_functions,
                    }
                )

        for probe in build_role_asset_isolation_matrix():
            plan = catalog.plan_goal(str(probe["text"]))
            consumer_plan = infer_goal_plan(str(probe["text"]), catalog)
            isolation_counts[
                "safe_hub"
                if _safe_hub_plan(
                    catalog,
                    terminal_function=plan.terminal_function,
                    preferred_functions=plan.preferred_functions,
                    expected_hub=str(probe["allowed_fallback"]),
                )
                and plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT
                and consumer_plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT
                and consumer_plan.terminal_function == probe["allowed_fallback"]
                and probe["excluded_function"] in consumer_plan.avoid_functions
                else "unsafe_or_wrong"
            ] += 1

        governed_functions = [
            item
            for item in runtime_payload["functions"]
            if "v16_role_governed_operations" in item.get("legacy_tags", [])
        ]
        hubs_by_domain = {
            str(item["domain"]): item
            for item in governed_functions
            if item.get("node_kind") == "hub"
        }
        terminals_by_domain = {
            domain: next(
                item
                for item in governed_functions
                if item.get("terminal") and item["domain"] == domain
            )
            for domain in hubs_by_domain
        }
        intents_by_terminal = {
            str(item["terminal_function"]): item
            for item in runtime_payload["intents"]
        }
        explicit_failure_phrases = (
            "wrong role",
            "role not authorized",
            "other professional role",
            "access denied",
            "you are not authorized",
            "user isn't authorized",
            "unauthorised operator",
            "insufficient permissions",
            "different governed asset",
            "wrong person or record",
            "different lifecycle state",
            "missing jurisdiction",
            "jurisdiction hold",
            "permission denied",
            "unavailable permission",
            "disabled control",
            "button is disabled",
            "control is disabled",
            "disabled button",
            "currently unavailable",
            "unavailable control",
            "action unavailable",
            "feature unavailable",
            "service unavailable",
            "system is offline",
            "currently offline",
            "offline data",
            "data is stale",
            "stale data",
            "legal hold",
            "safety hold",
            "quality hold",
            "security hold",
            "interlock",
            "권한 없는 역할",
            "잘못된 역할",
            "다른 전문 역할",
            "다른 관리 자산",
            "다른 사람 또는 기록",
            "다른 생명주기 상태",
            "권한 거부",
            "권한 부족",
            "접근 거부",
            "허가되지 않음",
            "버튼이 비활성",
            "비활성 버튼",
            "컨트롤 비활성",
            "사용 불가",
            "관할 누락",
            "오프라인 상태",
            "오래된 데이터",
            "법적 보류",
            "안전 보류",
            "품질 보류",
            "보안 보류",
        )
        false_positive_controls = (
            "disabled veteran benefit",
            "offline language pack download",
            "unavailable dates calendar",
            "pending review queue",
            "library hold request",
            "role based dashboard",
            "asset inventory report",
            "registration listing deactivate",
            "비활성화 등록 목록",
            "오프라인 언어팩 다운로드",
            "도서 대출 보류 신청",
        )
        positive_plans = {}
        for domain, terminal in terminals_by_domain.items():
            intent = intents_by_terminal[str(terminal["function_id"])]
            positive_goal = str(intent["patterns_by_locale"]["en-US"][0])
            positive_plan = catalog.plan_goal(positive_goal)
            assert positive_plan.terminal_function == terminal["function_id"]
            positive_plans[domain] = positive_plan
            hub = str(hubs_by_domain[domain]["function_id"])
            domain_name = str(hubs_by_domain[domain]["name_en"])
            for index, phrase in enumerate(explicit_failure_phrases):
                wrapper = (
                    f"NOTICE ({index}): {domain_name}; {phrase}."
                    if index % 2 == 0
                    else f"{phrase} — {domain_name} [state evidence]"
                )
                bounded = catalog.apply_governance_evidence_boundary(
                    result=positive_plan,
                    evidence_text=wrapper,
                )
                if _safe_hub_plan(
                    catalog,
                    terminal_function=bounded.terminal_function,
                    preferred_functions=bounded.preferred_functions,
                    expected_hub=hub,
                ) and bounded.intent == GOAL_GOVERNANCE_BLOCKED_INTENT:
                    boundary_counts["explicit_blocked"] += 1
                else:
                    boundary_counts["explicit_missed"] += 1
            for control in false_positive_controls:
                bounded = catalog.apply_governance_evidence_boundary(
                    result=positive_plan,
                    evidence_text=control,
                )
                boundary_counts[
                    "false_positive_clear" if bounded == positive_plan else "false_positive_blocked"
                ] += 1

        ordered_domains = sorted(hubs_by_domain)
        for index, domain in enumerate(ordered_domains):
            other = ordered_domains[(index + 1) % len(ordered_domains)]
            bounded = catalog.apply_governance_evidence_boundary(
                result=positive_plans[domain],
                evidence_text=(
                    f"{hubs_by_domain[domain]['name_en']} and "
                    f"{hubs_by_domain[other]['name_en']}: wrong role"
                ),
            )
            if (
                bounded.intent == GOAL_GOVERNANCE_BLOCKED_INTENT
                and not bounded.terminal_function
                and not bounded.preferred_functions
            ):
                boundary_counts["ambiguous_fail_closed"] += 1
            else:
                boundary_counts["ambiguous_selected_domain"] += 1

        # The public guide-mode consumer must stop before cache, route, or LLM
        # selection.  A catalog-only assertion would miss a provider choosing
        # the dangerous button again after the goal parser had rejected it.
        guide_probe = build_state_permission_recovery_matrix()[0]
        target_function = str(guide_probe["excluded_function"])
        target_definition = catalog.function(target_function)
        assert target_definition is not None
        target_intent = next(
            item
            for item in runtime_payload["intents"]
            if item["terminal_function"] == target_function
        )
        positive_goal = str(target_intent["patterns_by_locale"]["en-US"][0])

        def guide_request(
            *,
            suffix: str,
            title: str,
            enabled: bool,
            goal_text: str = positive_goal,
        ):
            return UniversalNavigationObserveRequest.model_validate(
                {
                    "request_id": f"v16_governance_{suffix}",
                    "session_id": f"v16_governance_{suffix}",
                    "app_package": "com.example.governed",
                    "app_version": "1",
                    "locale": "en-US",
                    "goal_text": goal_text,
                    "operation_mode": "guide",
                    "screen": {
                        "activity_name": "GovernedActivity",
                        "window_title": title,
                        "elements": [
                            {
                                "id": "dangerous-final-action",
                                "parent_id": "root",
                                "text": target_definition.name_en,
                                "role": "button",
                                "clickable": True,
                                "enabled": enabled,
                                "visible": True,
                                "bounds": [0, 0, 100, 100],
                            }
                        ],
                    },
                }
            )

        requests = (
            guide_request(suffix="permission", title="Permission denied", enabled=True),
            guide_request(suffix="disabled", title="Governed operation", enabled=False),
            guide_request(suffix="loading", title="Loading", enabled=True),
            guide_request(suffix="offline", title="You are offline", enabled=True),
            guide_request(suffix="error", title="Something went wrong", enabled=True),
            guide_request(suffix="relogin", title="Session expired", enabled=True),
            guide_request(suffix="record", title="Record mismatch", enabled=True),
            guide_request(suffix="jurisdiction", title="Jurisdiction mismatch", enabled=True),
            guide_request(suffix="state", title="Invalid lifecycle state", enabled=True),
        )
        repository = UniversalNavigationGraphRepository(root / "guide-consumer.sqlite")
        original_catalog_getter = agent_module.get_navigation_function_catalog
        original_provider_getter = agent_module._provider_for
        provider_calls = 0

        def forbidden_provider(_settings: Settings):
            nonlocal provider_calls
            provider_calls += 1
            raise AssertionError("provider must not run after governance block")

        agent_module.get_navigation_function_catalog = lambda _settings: catalog
        agent_module._provider_for = forbidden_provider
        try:
            responses = [
                observe_universal_navigation(
                    request,
                    settings=Settings(
                        navigation_agent_provider="mock",
                        android_control_index_path="",
                    ),
                    repository=repository,
                )
                for request in requests
            ]
        finally:
            agent_module.get_navigation_function_catalog = original_catalog_getter
            agent_module._provider_for = original_provider_getter

        assert provider_calls == 0
        for response, expected_status in zip(
            responses,
            (
                "needs_user_input",
                "no_safe_action",
                "needs_user_input",
                "needs_user_input",
                "needs_user_input",
                "needs_user_input",
                "needs_user_input",
                "needs_user_input",
                "needs_user_input",
            ),
            strict=True,
        ):
            assert response.status == expected_status
            assert response.phase == "stopped"
            assert response.goal_interpretation == GOAL_GOVERNANCE_BLOCKED_INTENT
            assert response.decision_mode == "deterministic_fallback"
            assert response.automation.action == "none"
            assert response.automation.safe_to_execute is False
            assert response.automation.selected_element_id is None
            assert response.recommendation is not None
            assert response.recommendation.selected_element_id is None
            assert response.recommendation.risk_level == "blocked"
            assert response.recommendation.target_function == guide_probe["allowed_fallback"]

        generic_response = observe_universal_navigation(
            guide_request(
                suffix="generic",
                title="Operations",
                enabled=True,
                goal_text="open whichever option seems useful",
            ),
            settings=Settings(
                navigation_agent_provider="mock",
                android_control_index_path="",
            ),
            repository=repository,
            catalog=catalog,
        )
        assert provider_calls == 0
        assert generic_response.status == "needs_user_input"
        assert generic_response.phase == "stopped"
        assert generic_response.goal_interpretation == "insufficient_screen_evidence"
        assert generic_response.decision_mode == "deterministic_fallback"
        assert generic_response.automation.action == "none"
        assert generic_response.automation.safe_to_execute is False
        assert generic_response.recommendation is not None
        assert generic_response.recommendation.selected_element_id is None

    print(
        json.dumps(
            {
                "checkpoint": "aggregate_only",
                "semantic": dict(semantic_counts),
                "collision": dict(collision_counts),
                "recovery": dict(recovery_counts),
                "isolation": dict(isolation_counts),
                "exact_wrapper": dict(exact_wrapper_counts),
                "markerless_class1": dict(markerless_class1_counts),
                "explicit_marker_class1": dict(explicit_marker_class1_counts),
                "long_composite": dict(long_composite_counts),
                "long_variants": dict(long_composite_variant_counts),
                "ambiguous_composite": dict(ambiguous_composite_counts),
                "dangerous_terminal_after_negative_evidence": (
                    dangerous_terminal_after_negative_evidence
                ),
                "guide_provider_calls_after_block": provider_calls,
                "negative_failures": negative_failures,
                "recovery_failures": recovery_failures,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )

    assert semantic_counts == {"positive_exact": 480, "negative_safe": 960}, (
        semantic_counts,
        negative_failures,
    )
    assert collision_counts == {"exact": 720}, collision_counts
    assert recovery_counts == {"safe_hub": 960}, (recovery_counts, recovery_failures)
    assert isolation_counts == {"safe_hub": 720}, isolation_counts
    assert dangerous_terminal_after_negative_evidence == 0
    assert exact_wrapper_counts == {"preserved": 2}, exact_wrapper_counts
    assert markerless_class1_counts == {"preserved": 12}, markerless_class1_counts
    assert explicit_marker_class1_counts == {"confirmed": 96}, (
        explicit_marker_class1_counts
    )
    assert long_composite_counts["wrong"] == 0, (
        long_composite_counts,
        long_composite_variant_counts,
    )
    assert long_composite_counts["target"] >= 30, long_composite_counts
    assert (
        long_composite_counts["target"] + long_composite_counts["generic"] == 96
    ), long_composite_counts
    assert ambiguous_composite_counts == {"generic": 12}, ambiguous_composite_counts
    assert boundary_counts == {
        "explicit_blocked": len(hubs_by_domain) * len(explicit_failure_phrases),
        "false_positive_clear": len(hubs_by_domain) * len(false_positive_controls),
        "ambiguous_fail_closed": len(hubs_by_domain),
    }, boundary_counts

    print(
        json.dumps(
            {
                "result": "PASS",
                "runtime_probe_count": 3840,
                "semantic_positive_exact": semantic_counts["positive_exact"],
                "semantic_negative_safe": semantic_counts["negative_safe"],
                "collision_exact": collision_counts["exact"],
                "recovery_safe_hub": recovery_counts["safe_hub"],
                "isolation_safe_hub": isolation_counts["safe_hub"],
                "dangerous_terminal_after_negative_evidence": (
                    dangerous_terminal_after_negative_evidence
                ),
                "guide_provider_calls_after_block": provider_calls,
                "legacy_exact_wrapper_preserved": exact_wrapper_counts["preserved"],
                "markerless_class1_preserved": markerless_class1_counts["preserved"],
                "explicit_marker_class1_confirmed": explicit_marker_class1_counts[
                    "confirmed"
                ],
                "long_composite_target": long_composite_counts["target"],
                "ambiguous_composite_fail_closed": ambiguous_composite_counts["generic"],
                "governance_boundary_probes": sum(boundary_counts.values()),
                "governance_false_positive_controls": boundary_counts[
                    "false_positive_clear"
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
