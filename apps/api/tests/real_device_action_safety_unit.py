from __future__ import annotations

import sys
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.real_device_action_safety import (
    ACTION_GUARD_EVALUATION_PHASE,
    ACTION_GUARD_POLICY_VERSION,
    evaluate_auto_action_guard,
    guard_evidence_matches,
    is_final_or_consequential_label,
    is_final_or_consequential_resource_id,
    is_safe_menu_or_settings_action,
)


def test_korean_and_english_terminal_labels_are_user_owned() -> None:
    labels = (
        "회원 탈퇴하기",
        "계정 삭제",
        "구독 해지",
        "무료 체험 취소",
        "자동결제 해제",
        "결제하기",
        "구매 확정",
        "예약 제출",
        "보험금 청구하기",
        "Delete my account",
        "Deactivate profile",
        "Cancel subscription",
        "End my membership",
        "Turn off auto-renewal",
        "Pay now",
        "Confirm payment",
        "Request a refund",
    )
    for label in labels:
        assert is_final_or_consequential_label(label), label


def test_informational_and_management_labels_are_not_terminal() -> None:
    labels = (
        "해지 안내",
        "구독 관리",
        "예약 조회",
        "계정 설정",
        "Cancellation policy",
        "Manage subscription",
        "Account settings",
        "Payment history",
    )
    for label in labels:
        assert not is_final_or_consequential_label(label), label


def test_safe_menu_classifier_uses_label_or_structural_resource() -> None:
    assert is_safe_menu_or_settings_action(selected_label="개인정보 설정")
    assert is_safe_menu_or_settings_action(selected_label="Account settings")
    assert is_safe_menu_or_settings_action(
        selected_label="",
        element_labels=("", ""),
        resource_id="com.example:id/navigation_profile",
    )
    assert not is_safe_menu_or_settings_action(selected_label="둘러보기")
    assert not is_safe_menu_or_settings_action(
        selected_label="Explore", resource_id="com.example:id/discover"
    )


def test_final_classification_overrides_safe_menu_word() -> None:
    decision = evaluate_auto_action_guard(
        "click",
        selected_label="Account settings",
        element_labels=("Delete account",),
        resource_id="com.example:id/account_settings",
    )
    assert decision.computed_final_or_consequential is True
    assert decision.safe_menu_match is True
    assert decision.allowed is False
    assert decision.reason == "final_or_consequential_action"


def test_unnamed_consequential_resource_ids_are_user_owned() -> None:
    resources = (
        "com.example:id/delete_account_button",
        "com.example:id/deleteAccountButton",
        "com.example:id/cancel_subscription",
        "com.example:id/pay_now",
        "com.example:id/submit",
        "com.example:id/close_profile",
        "com.example:id/end_membership",
        "com.example:id/disable_auto_renewal",
        "com.example:id/make_payment",
        "com.example:id/marketing_opt_out",
    )
    for resource_id in resources:
        assert is_final_or_consequential_resource_id(resource_id), resource_id
        decision = evaluate_auto_action_guard(
            "click",
            selected_label="",
            element_labels=(),
            resource_id=resource_id,
        )
        assert decision.computed_final_or_consequential is True, resource_id
        assert decision.allowed is False, resource_id
        assert decision.reason == "final_or_consequential_action", resource_id

    assert not is_final_or_consequential_resource_id(
        "com.example:id/account_settings"
    )
    assert not is_final_or_consequential_resource_id(
        "com.example:id/payment_methods"
    )


def test_guard_evidence_is_label_free_exact_and_pre_execution() -> None:
    decision = evaluate_auto_action_guard(
        "click",
        selected_label="Settings",
        element_labels=("Settings",),
        resource_id="com.example:id/settings",
    )
    evidence = decision.evidence()
    assert evidence == {
        "policy_version": ACTION_GUARD_POLICY_VERSION,
        "evaluation_phase": ACTION_GUARD_EVALUATION_PHASE,
        "action_type": "click",
        "allowed": True,
        "computed_final_or_consequential": False,
        "safe_menu_match": True,
        "reason": "physical_safe_menu_navigation",
    }
    assert "Settings" not in str(evidence)
    assert guard_evidence_matches(evidence, decision)
    tampered = dict(evidence)
    tampered["safe_menu_match"] = False
    assert not guard_evidence_matches(tampered, decision)


def main() -> None:
    test_korean_and_english_terminal_labels_are_user_owned()
    test_informational_and_management_labels_are_not_terminal()
    test_safe_menu_classifier_uses_label_or_structural_resource()
    test_final_classification_overrides_safe_menu_word()
    test_unnamed_consequential_resource_ids_are_user_owned()
    test_guard_evidence_is_label_free_exact_and_pre_execution()
    print("Real-device shared action safety checks ok")


if __name__ == "__main__":
    main()
