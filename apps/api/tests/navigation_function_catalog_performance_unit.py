from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

import app.services.navigation_function_catalog as catalog_module
from app.schemas import (
    UniversalNavigationCandidate,
    UniversalNavigationElement,
    UniversalNavigationObserveRequest,
    UniversalNavigationScreen,
)
from app.services.navigation_function_catalog import (
    DEFAULT_CATALOG_PATH,
    NavigationFunctionCatalog,
)
from app.services.navigation_semantics import candidate_contexts, infer_goal_plan


YOUTUBE_PREMIUM_CASES = (
    {
        "label": "Purchases and memberships",
        "parent_label": "YouTube",
        "nearby_text": "YouTube Premium membership and billing",
        "expected": "subscription.manage",
    },
    {
        "label": "Manage membership",
        "parent_label": "Purchases and memberships",
        "nearby_text": "YouTube Premium individual membership next billing date",
        "expected": "subscription.manage",
    },
    {
        "label": "Cancel membership",
        "parent_label": "YouTube Premium",
        "nearby_text": "Membership settings next billing date",
        "expected": "subscription.cancel.entry",
    },
)


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "function-catalog.sqlite",
            DEFAULT_CATALOG_PATH,
        )
        stats = catalog.stats()
        # This test is intentionally tied to the expanded catalog that exposed
        # the regression; a tiny fixture would not exercise the hot path.
        assert int(stats["function_count"]) >= 2_800
        assert int(stats["state_cue_count"]) >= 100_000

        _assert_alias_top_results_equal_exhaustive(catalog)
        _assert_candidate_matches_equal_exhaustive(catalog)

        cold_similarity_calls = 0
        original_similarity = catalog_module._phrase_similarity

        def counted_similarity(label: str, alias: str) -> float:
            nonlocal cold_similarity_calls
            cold_similarity_calls += 1
            return original_similarity(label, alias)

        cold_started = perf_counter()
        with patch.object(catalog_module, "_phrase_similarity", counted_similarity):
            for case in YOUTUBE_PREMIUM_CASES:
                # Explicitly clear both layers so this region protects the
                # first observation of every visible screen label.
                catalog._candidate_match_cache.clear()
                catalog._candidate_alias_pair_cache.clear()
                catalog._candidate_alias_bound_cache.clear()
                matches = catalog.match_candidate(
                    label=case["label"],
                    parent_label=case["parent_label"],
                    nearby_text=case["nearby_text"],
                    role="button",
                    locale="en-US",
                    enabled=True,
                    limit=40,
                )
                assert matches[0].function_id == case["expected"], matches[:5]
                _assert_match_alias_evidence_equal_exhaustive(catalog, matches[:5], case["label"])
        cold_elapsed_seconds = perf_counter() - cold_started

        # The prior implementation invoked SequenceMatcher for all 53k aliases
        # per cold label.  The deterministic call bound is the primary guard;
        # the wall bound is deliberately loose for slower CI hosts.
        assert cold_similarity_calls < 50_000, cold_similarity_calls
        assert cold_elapsed_seconds < 4.0, cold_elapsed_seconds

        for case in YOUTUBE_PREMIUM_CASES:
            matches = catalog.match_candidate(
                label=case["label"],
                parent_label=case["parent_label"],
                nearby_text=case["nearby_text"],
                role="button",
                locale="en-US",
                enabled=True,
                limit=40,
            )
            assert matches[0].function_id == case["expected"], matches[:5]

        normalize_calls = 0
        original_normalize = catalog_module._normalize

        def counted_normalize(value: str) -> str:
            nonlocal normalize_calls
            normalize_calls += 1
            return original_normalize(value)

        started = perf_counter()
        with patch.object(catalog_module, "_normalize", counted_normalize):
            for ordinal, case in enumerate(YOUTUBE_PREMIUM_CASES):
                matches = catalog.match_candidate(
                    label=case["label"],
                    parent_label=case["parent_label"],
                    nearby_text=f"{case['nearby_text']} observed screen {ordinal}",
                    role="button",
                    locale="en-US",
                    enabled=True,
                    limit=40,
                )
                assert matches[0].function_id == case["expected"], matches[:5]
        elapsed_seconds = perf_counter() - started

        # Before state-cue compilation this was proportional to all 112k cues
        # for every candidate and took seconds per call.  The generous wall
        # bound catches that regression without depending on workstation speed;
        # the normalization-count bound is the deterministic primary guard.
        assert normalize_calls < 500, normalize_calls
        assert elapsed_seconds < 2.0, elapsed_seconds

        screen_elapsed_seconds, screen_similarity_calls = _assert_whole_screen_performance(
            catalog
        )

    print(
        "navigation function catalog performance checks ok "
        f"(cold={cold_elapsed_seconds:.3f}s, "
        f"similarity_calls={cold_similarity_calls}, warm={elapsed_seconds:.3f}s, "
        f"normalize_calls={normalize_calls}, screen={screen_elapsed_seconds:.3f}s, "
        f"screen_similarity_calls={screen_similarity_calls})"
    )


def _assert_candidate_matches_equal_exhaustive(
    catalog: NavigationFunctionCatalog,
) -> None:
    """Compare lazy top-k evaluation with a forced all-function pass."""

    cases = (
        {
            "label": "Purchases and memberships",
            "parent_label": "YouTube",
            "nearby_text": "YouTube Premium membership and billing",
            "role": "button",
            "position": "middle",
            "locale": "en-US",
            "enabled": True,
            "limit": 16,
        },
        {
            "label": "Manage membership",
            "parent_label": "Purchases and memberships",
            "nearby_text": "next billing date",
            "role": "menuitem",
            "position": "middle",
            "locale": "en-US",
            "enabled": True,
            "limit": 40,
        },
        {
            "label": "Cancel membership",
            "parent_label": "YouTube Premium",
            "nearby_text": "membership settings",
            "role": "button",
            "position": "middle",
            "locale": "en-US",
            "enabled": True,
            "limit": 16,
        },
        {
            "label": "Subscriptions",
            "parent_label": "",
            "nearby_text": "Home Shorts Library",
            "role": "tab",
            "position": "bottom",
            "locale": "en-US",
            "enabled": True,
            "selected": True,
            "limit": 16,
        },
        {
            "label": "delete accunt",
            "parent_label": "Privacy settings",
            "nearby_text": "",
            "role": "button",
            "position": "middle",
            "locale": "en-US",
            "enabled": True,
            "limit": 8,
        },
        {
            "label": "YouTube Premium individual membership 14,900",
            "parent_label": "Purchases and memberships",
            "nearby_text": "billing",
            "role": "button",
            "position": "middle",
            "locale": "en-US",
            "enabled": True,
            "limit": 16,
        },
        {
            "label": "내 페이지",
            "parent_label": "YouTube",
            "nearby_text": "홈 Shorts 구독",
            "role": "button",
            "position": "bottom",
            "locale": "ko-KR",
            "enabled": True,
            "limit": 16,
        },
        {
            "label": "설정",
            "parent_label": "내 페이지",
            "nearby_text": "계정",
            "role": "image",
            "position": "top",
            "locale": "ko-KR",
            "enabled": True,
            "limit": 16,
        },
        {
            "label": "구매 항목 및 멤버십",
            "parent_label": "설정",
            "nearby_text": "YouTube Premium 결제",
            "role": "button",
            "position": "middle",
            "locale": "ko-KR",
            "enabled": True,
            "limit": 16,
        },
        {
            "label": "YouTube Premium 개인 멤버십 #14,900",
            "parent_label": "구매 항목 및 멤버십",
            "nearby_text": "다음 결제일",
            "role": "button",
            "position": "middle",
            "locale": "ko-KR",
            "enabled": True,
            "limit": 16,
        },
        {
            "label": "취소",
            "parent_label": "YouTube Premium 개인 멤버십",
            "nearby_text": "다음 결제일",
            "role": "button",
            "position": "middle",
            "locale": "ko-KR",
            "enabled": True,
            "limit": 16,
        },
        {
            "label": "Google Play에서 관리",
            "parent_label": "YouTube Premium 개인 멤버십",
            "nearby_text": "구독 결제",
            "role": "button",
            "position": "middle",
            "locale": "ko-KR",
            "enabled": True,
            "limit": 16,
        },
        {
            "label": "구독자 98명",
            "parent_label": "채널",
            "nearby_text": "동영상 재생목록",
            "role": "button",
            "position": "middle",
            "locale": "ko-KR",
            "enabled": True,
            "limit": 16,
        },
    )
    original_bound = catalog_module._alias_score_contribution_bound

    def force_exhaustive_bound(
        label_value: str,
        normalized_locale: str,
        features: tuple,
        *,
        label_character_counts: dict,
    ) -> tuple[float, bool]:
        _bound, has_exact_alias = original_bound(
            label_value,
            normalized_locale,
            features,
            label_character_counts=label_character_counts,
        )
        # A ceiling above the maximum possible final score prevents the lazy
        # stopping rule from omitting any physical function.
        return 10.0, has_exact_alias

    for case in cases:
        catalog._candidate_match_cache.clear()
        catalog._candidate_alias_bound_cache.clear()
        optimized = catalog.match_candidate(**case)
        catalog._candidate_match_cache.clear()
        catalog._candidate_alias_bound_cache.clear()
        with patch.object(
            catalog_module,
            "_alias_score_contribution_bound",
            force_exhaustive_bound,
        ):
            exhaustive = catalog.match_candidate(**case)
        assert optimized == exhaustive, case


def _assert_whole_screen_performance(
    catalog: NavigationFunctionCatalog,
) -> tuple[float, int]:
    """Guard the row-20 regression: one ordinary screen must not take 17s."""

    labels = (
        "YouTube Premium",
        "Search",
        "Notifications",
        "Home",
        "Shorts",
        "Subscriptions",
        "Library",
        "My page",
        "Settings",
        "Purchases and memberships",
        "Manage membership",
        "Payment methods",
        "Billing history",
        "Privacy",
        "Security",
        "Account",
        "Help and feedback",
        "Your data",
        "Downloads",
        "Watch history",
        "Playback",
        "Autoplay",
        "General",
        "Connected apps",
        "Family sharing",
        "Membership benefits",
        "Next billing date",
        "Individual membership",
        "Premium plan details",
        "Change plan",
        "Pause membership",
        "Cancel membership",
        "Deactivate auto renewal",
        "Subscription status",
        "Terms and conditions",
        "Customer support",
        "More options",
        "Back",
        "Profile",
        "Sign out",
    )
    elements = [
        UniversalNavigationElement(
            id=f"candidate-{index}",
            text=label,
            role="button",
            clickable=True,
            bounds=[0, index * 20, 500, index * 20 + 18],
        )
        for index, label in enumerate(labels)
    ]
    request = UniversalNavigationObserveRequest(
        request_id="screen-performance-request",
        session_id="screen-performance-session",
        app_package="com.example.video",
        app_version="1",
        locale="en-US",
        goal_text="Cancel YouTube Premium subscription",
        operation_mode="explore",
        screen=UniversalNavigationScreen(
            activity_name="MembershipActivity",
            window_title="YouTube Premium",
            elements=elements,
        ),
    )
    candidates = [
        UniversalNavigationCandidate(
            element_id=element.id,
            element_key=f"key-{index}",
            label=element.text or "",
            role=element.role,
            risk_level="low",
        )
        for index, element in enumerate(elements)
    ]
    similarity_calls = 0
    original_similarity = catalog_module._phrase_similarity

    def counted_similarity(label: str, alias: str) -> float:
        nonlocal similarity_calls
        similarity_calls += 1
        return original_similarity(label, alias)

    catalog._candidate_match_cache.clear()
    catalog._candidate_alias_pair_cache.clear()
    catalog._candidate_alias_bound_cache.clear()
    started = perf_counter()
    with patch.object(catalog_module, "_phrase_similarity", counted_similarity):
        contexts = candidate_contexts(
            request=request,
            candidates=candidates,
            demonstrations=[],
            plan=infer_goal_plan(request.goal_text, catalog),
            catalog=catalog,
        )
    elapsed = perf_counter() - started
    assert len(contexts) == len(labels)
    cancel_matches = dict(contexts["candidate-31"].function_matches)
    assert cancel_matches.get("subscription.cancel.entry", 0.0) >= 0.75
    # The old implementation made roughly 400k SequenceMatcher calls for a
    # 40-label screen. The deterministic bound is the primary regression
    # guard; the wall limit is deliberately generous for slower CI hosts.
    assert similarity_calls < 100_000, similarity_calls
    assert elapsed < 12.0, elapsed
    return elapsed, similarity_calls


def _assert_alias_top_results_equal_exhaustive(catalog: NavigationFunctionCatalog) -> None:
    cases = (
        ("Purchases and memberships", "en-US"),
        ("Manage membership", "en-US"),
        ("Cancel membership", "en-US"),
        ("Settings", "en-US"),
        ("My page", "en-US"),
        ("구독 취소", "ko-KR"),
    )
    for label, locale in cases:
        normalized_label = catalog_module._normalize(label)
        normalized_locale = catalog_module._normalize_locale(locale)
        catalog._candidate_alias_pair_cache.clear()
        optimized = catalog._alias_pairs_for_label(normalized_label, normalized_locale)
        for function_id, aliases in catalog._aliases.items():
            exhaustive = tuple(
                sorted(
                    (
                        (
                            catalog_module._phrase_similarity(
                                normalized_label,
                                alias.normalized,
                            ),
                            catalog_module._locale_affinity(
                                normalized_locale,
                                alias.locale,
                            ),
                            alias,
                        )
                        for alias in aliases
                    ),
                    key=lambda item: (
                        item[0] + item[1],
                        item[0],
                        item[2].phrase,
                    ),
                    reverse=True,
                )[:1]
            )
            assert _alias_signature(optimized[function_id]) == _alias_signature(exhaustive), (
                label,
                function_id,
                optimized[function_id],
                exhaustive,
            )


def _assert_match_alias_evidence_equal_exhaustive(
    catalog: NavigationFunctionCatalog,
    matches: list,
    label: str,
) -> None:
    normalized_label = catalog_module._normalize(label)
    normalized_locale = catalog_module._normalize_locale("en-US")
    for match in matches:
        function_id = match.matched_function_id or match.function_id
        exhaustive = tuple(
            sorted(
                (
                    (
                        catalog_module._phrase_similarity(
                            normalized_label,
                            alias.normalized,
                        ),
                        catalog_module._locale_affinity(
                            normalized_locale,
                            alias.locale,
                        ),
                        alias,
                    )
                    for alias in catalog._aliases.get(function_id, ())
                ),
                key=lambda item: (
                    item[0] + item[1],
                    item[0],
                    item[2].phrase,
                ),
                reverse=True,
            )[:3]
        )
        assert match.matched_aliases == tuple(
            alias.phrase for score, _, alias in exhaustive if score > 0.35
        )
        assert match.matched_alias_locales == tuple(
            alias.locale for score, _, alias in exhaustive if score > 0.35
        )


def _alias_signature(values: tuple) -> tuple[tuple[float, float, str, str], ...]:
    return tuple(
        (score, locale_score, alias.locale, alias.phrase)
        for score, locale_score, alias in values
    )


if __name__ == "__main__":
    main()
