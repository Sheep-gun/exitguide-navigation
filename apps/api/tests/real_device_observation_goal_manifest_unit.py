from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "fixtures" / "navigation" / "real-device-observation-apps.v1.json"

EXPECTED_APPS = {
    "YouTube": "com.google.android.youtube",
    "Netflix": "com.netflix.mediaclient",
    "배민": "com.sampleapp",
    "Coupang": "com.coupang.mobile",
    "제주항공": "com.parksmt.jejuair.android16",
    "X": "com.twitter.android",
    "Toss": "viva.republica.toss",
    "NH손보": "ni.mh.android.launcher",
    "정부24": "kr.go.minwon.m",
    "The건강보험": "kr.or.nhic",
    "MyKT": "com.ktshow.cs",
    "Naver": "com.nhn.android.search",
    "당근": "com.towneers.www",
    "Instagram": "com.instagram.android",
}

REQUIRED_GOAL_FAMILIES = {
    "signup",
    "login",
    "logout",
    "account_deletion",
    "subscription_manage",
    "subscription_change",
    "subscription_cancel",
    "free_trial_cancel",
    "autopay_off",
    "payment_methods",
    "order_cancel_refund",
    "marketing_notifications_off",
    "optional_consent_withdrawal",
    "privacy_settings",
    "data_download_delete",
    "customer_support",
    "security_settings",
    "insurance_contract_lookup",
    "insurance_contract_change",
    "insurance_contract_cancel",
    "insurance_claim",
    "flight_booking_lookup",
    "flight_booking_cancel",
}

SUPPLEMENTAL_GOAL_FAMILIES = {
    "public_document_issuance",
    "insurance_premium_lookup",
    "insurance_refund_lookup",
    "telecom_billing_lookup",
}

LEGACY_PRIORITY_GOALS = {
    "com.google.android.youtube": {
        "YouTube Premium 구독 관리 화면 찾기",
        "YouTube Premium 해지 직전 화면 찾기",
        "개인정보 설정 화면 찾기",
    },
    "com.netflix.mediaclient": {
        "회원가입 시작 화면 찾기",
        "계정 관리 화면 찾기",
        "멤버십 해지 직전 화면 찾기",
    },
    "com.sampleapp": {
        "배민클럽 구독 관리 화면 찾기",
        "배민클럽 해지 직전 화면 찾기",
        "결제수단 관리 화면 찾기",
    },
    "com.coupang.mobile": {
        "회원가입 화면 찾기",
        "와우 멤버십 관리 화면 찾기",
        "와우 멤버십 해지 직전 화면 찾기",
    },
    "com.parksmt.jejuair.android16": {
        "회원가입 화면 찾기",
        "예약 조회 화면 찾기",
        "예약 취소 안내 화면 찾기",
    },
    "com.twitter.android": {
        "회원가입 화면 찾기",
        "계정 비활성화 직전 화면 찾기",
        "개인정보 설정 화면 찾기",
    },
    "viva.republica.toss": {
        "로그인 또는 본인인증 경계 화면 찾기",
        "보안 설정 화면 찾기",
        "고객센터 화면 찾기",
    },
    "ni.mh.android.launcher": {
        "보험 계약 조회 화면 찾기",
        "보험금 청구 시작 화면 찾기",
        "보험 계약 해지 안내 화면 찾기",
    },
    "kr.go.minwon.m": {
        "로그인 또는 본인인증 경계 화면 찾기",
        "주민등록등본 발급 서비스 화면 찾기",
        "개인정보 설정 화면 찾기",
    },
    "kr.or.nhic": {
        "보험료 조회 화면 찾기",
        "환급금 조회 화면 찾기",
        "민원 서류 발급 화면 찾기",
    },
    "com.ktshow.cs": {
        "요금 조회 화면 찾기",
        "부가서비스 해지 직전 화면 찾기",
        "마케팅 알림 설정 화면 찾기",
    },
    "com.nhn.android.search": {
        "멤버십 관리 화면 찾기",
        "검색 기록 삭제 화면 찾기",
        "개인정보 설정 화면 찾기",
    },
    "com.towneers.www": {
        "회원가입 화면 찾기",
        "알림 설정 화면 찾기",
        "계정 탈퇴 직전 화면 찾기",
    },
    "com.instagram.android": {
        "회원가입 화면 찾기",
        "계정 비활성화 직전 화면 찾기",
        "데이터 다운로드 화면 찾기",
    },
}


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert_manifest_governance_is_unchanged(manifest)
    assert_exact_app_cohort_and_collector_compatibility(manifest)
    assert_required_families_are_applicability_aware_and_complete(manifest)
    print("Real-device observation goal manifest checks ok")


def assert_manifest_governance_is_unchanged(manifest: dict[str, object]) -> None:
    assert manifest["provenance"] == "real_device_observation_candidate"
    assert manifest["dataset_role"] == "real_device_observation_candidate"
    assert manifest["review_status"] == "unreviewed_candidate"
    assert manifest["route_lifecycle"] == "shadow"
    assert manifest["canonical_catalog_mutation"] is False
    assert manifest["canonical_catalog"] == {
        "version": "15.0.0",
        "sha256": "e0eeef03195a48ec8172421926d08c30823bc678c72ea72082bb513dbec36e24",
        "equivalence_sha256": "197aa0253c0353e439a6679a3597efed25297c44c554a15c0402a30f077ab2e8",
        "domain_count": 179,
        "function_count": 2866,
        "terminal_function_count": 2660,
        "intent_count": 2660,
    }
    policy = manifest["collection_policy"]
    assert isinstance(policy, dict)
    assert policy["installed_apps_only"] is True
    assert policy["missing_app_status"] == "skipped_missing"
    assert set(policy["allowed_observation_statuses"]) == {
        "installed_not_selected",
        "installed_observed",
        "skipped_missing",
    }
    assert policy["never_execute_unsafe_action"] is True
    assert policy["never_execute_final_action"] is True
    assert policy["gold_promotion_allowed"] is False


def assert_exact_app_cohort_and_collector_compatibility(manifest: dict[str, object]) -> None:
    apps = manifest["apps"]
    assert isinstance(apps, list)
    observed = {
        str(app["app_name"]): str(app["app_package"])
        for app in apps
        if isinstance(app, dict)
    }
    assert observed == EXPECTED_APPS
    assert len(apps) == 14
    assert observed["MyKT"] == "com.ktshow.cs"

    for app in apps:
        assert isinstance(app, dict)
        package = str(app["app_package"])
        goals = app["priority_goals"]
        mapping = app["goal_family_mapping"]
        assert isinstance(goals, list)
        assert isinstance(mapping, dict)
        assert len(goals) >= 10, f"{package} needs a useful goal set"
        assert len(mapping) >= 8, f"{package} needs multiple applicable families"
        assert all(isinstance(goal, str) and goal.strip() for goal in goals)
        assert all(goal.endswith("화면 찾기") for goal in goals)
        assert len(goals) == len(set(goals)), f"duplicate priority goal for {package}"

        mapped_goals = [
            goal
            for family_goals in mapping.values()
            for goal in family_goals
        ]
        assert len(mapped_goals) == len(set(mapped_goals)), f"goal mapped twice for {package}"
        assert set(mapped_goals) == set(goals), f"priority/mapping drift for {package}"
        assert LEGACY_PRIORITY_GOALS[package] <= set(goals)


def assert_required_families_are_applicability_aware_and_complete(
    manifest: dict[str, object],
) -> None:
    definitions = manifest["required_goal_families"]
    assert isinstance(definitions, list)
    by_family = {
        str(item["family_id"]): item
        for item in definitions
        if isinstance(item, dict)
    }
    assert set(by_family) == REQUIRED_GOAL_FAMILIES
    assert len(definitions) == len(REQUIRED_GOAL_FAMILIES)
    assert all(
        item["terminal_policy"]
        in {"navigation_only", "user_boundary", "user_final_action", "mixed_user_owned"}
        for item in definitions
    )
    supplemental_definitions = manifest["supplemental_goal_families"]
    assert isinstance(supplemental_definitions, list)
    supplemental_by_family = {
        str(item["family_id"]): item
        for item in supplemental_definitions
        if isinstance(item, dict)
    }
    assert set(supplemental_by_family) == SUPPLEMENTAL_GOAL_FAMILIES
    assert all(
        item["terminal_policy"] in {"navigation_only", "user_final_action"}
        for item in supplemental_definitions
    )

    coverage: dict[str, set[str]] = defaultdict(set)
    goals_by_family: dict[str, list[str]] = defaultdict(list)
    apps = manifest["apps"]
    assert isinstance(apps, list)
    for app in apps:
        assert isinstance(app, dict)
        package = str(app["app_package"])
        mapping = app["goal_family_mapping"]
        assert isinstance(mapping, dict)
        assert set(mapping) <= REQUIRED_GOAL_FAMILIES | SUPPLEMENTAL_GOAL_FAMILIES
        for family_id, goals in mapping.items():
            assert isinstance(goals, list) and goals
            coverage[str(family_id)].add(package)
            goals_by_family[str(family_id)].extend(str(goal) for goal in goals)

    assert set(coverage) == REQUIRED_GOAL_FAMILIES | SUPPLEMENTAL_GOAL_FAMILIES

    insurance_families = {
        "insurance_contract_lookup",
        "insurance_contract_change",
        "insurance_contract_cancel",
        "insurance_claim",
    }
    for family_id in insurance_families:
        assert coverage[family_id] == {"ni.mh.android.launcher"}

    flight_families = {"flight_booking_lookup", "flight_booking_cancel"}
    for family_id in flight_families:
        assert coverage[family_id] == {"com.parksmt.jejuair.android16"}

    non_subscription_packages = {
        "viva.republica.toss",
        "ni.mh.android.launcher",
        "kr.go.minwon.m",
        "kr.or.nhic",
        "com.parksmt.jejuair.android16",
        "com.towneers.www",
    }
    subscription_families = {
        "subscription_manage",
        "subscription_change",
        "subscription_cancel",
        "free_trial_cancel",
    }
    for family_id in subscription_families:
        assert not (coverage[family_id] & non_subscription_packages)

    for family_id, definition in by_family.items():
        if definition["terminal_policy"] == "user_final_action":
            assert any(
                "직전" in goal or "안내" in goal
                for goal in goals_by_family[family_id]
            ), f"{family_id} lacks an explicit user-owned stop point"

    mixed_goals = goals_by_family["data_download_delete"]
    assert any("다운로드" in goal for goal in mixed_goals)
    assert any("삭제" in goal and "직전" in goal for goal in mixed_goals)


if __name__ == "__main__":
    main()
