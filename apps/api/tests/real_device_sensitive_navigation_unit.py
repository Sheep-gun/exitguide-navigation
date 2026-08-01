from __future__ import annotations

import json

from app.services.real_device_sensitive_navigation import (
    NEUTRAL_DISCOVERY_FAMILY,
    PERSISTED_GUARD_LABEL_BUCKET,
    choose_sensitive_local_menu_action,
    classify_sensitive_surface_boundary,
    collect_sensitive_local_goal_signal_evidence,
)


def _element(
    element_id: str,
    label: str,
    *,
    resource_id: str = "",
    clickable: bool = True,
    checkable: bool = False,
    class_name: str = "android.widget.Button",
    role: str = "button",
) -> dict[str, object]:
    return {
        "element_id": element_id,
        "label": label,
        "text": label,
        "content_description": "",
        "inferred_label": "",
        "resource_id": resource_id,
        "class_name": class_name,
        "role": role,
        "clickable": clickable,
        "enabled": True,
        "visible": True,
        "checkable": checkable,
        "password": False,
        "bounds": (10, 10, 100, 80),
    }


def main() -> None:
    finance_screen = [
        _element("adb_1111111111111111", "잔액 1,234,567원", resource_id="balance_value"),
        _element("adb_2222222222222222", "송금하기", resource_id="transfer_button"),
        _element("adb_3333333333333333", "", resource_id="toolbar_settings"),
    ]
    settings = choose_sensitive_local_menu_action(
        finance_screen,
        goal_family_id="security_settings",
    )
    assert settings.allowed is True
    assert settings.element_id == "adb_3333333333333333"
    assert settings.score_bucket == "structural_gateway"
    serialized = json.dumps(settings.evidence(), ensure_ascii=False)
    assert "잔액" not in serialized
    assert "송금" not in serialized
    assert "toolbar_settings" not in serialized
    assert settings.evidence()["external_api_transfer_count"] == 0
    assert settings.evidence()["persisted_guard_label_bucket"] == PERSISTED_GUARD_LABEL_BUCKET
    assert settings.evidence()["human_text_persisted"] is False
    assert len(settings.evidence()["semantic_commitment_sha256"]) == 64

    neutral = choose_sensitive_local_menu_action(
        finance_screen,
        goal_family_id=NEUTRAL_DISCOVERY_FAMILY,
    )
    assert neutral.allowed is True
    assert neutral.element_id == "adb_3333333333333333"
    assert neutral.goal_family_id == NEUTRAL_DISCOVERY_FAMILY

    direct = choose_sensitive_local_menu_action(
        [
            _element("adb_4444444444444444", "내 계정"),
            _element("adb_5555555555555555", "구독 관리"),
        ],
        goal_family_id="subscription_manage",
    )
    assert direct.allowed is True
    assert direct.element_id == "adb_5555555555555555"
    assert direct.score_bucket == "direct_goal_signal"

    final = choose_sensitive_local_menu_action(
        [_element("adb_6666666666666666", "계정 삭제하기")],
        goal_family_id="account_deletion",
    )
    assert final.allowed is False
    assert final.reason == "sensitive_goal_entry_user_boundary"
    assert final.boundary_kind == "sensitive_goal_entry_user_boundary"

    toggle = choose_sensitive_local_menu_action(
        [_element("adb_7777777777777777", "마케팅 알림", checkable=True)],
        goal_family_id="marketing_notifications_off",
    )
    assert toggle.allowed is False
    assert toggle.boundary_kind == "sensitive_goal_entry_user_boundary"

    unnamed_destructive = choose_sensitive_local_menu_action(
        [
            _element(
                "adb_7171717171717171",
                "",
                resource_id="com.example:id/delete_account_button",
            )
        ],
        goal_family_id=NEUTRAL_DISCOVERY_FAMILY,
    )
    assert unnamed_destructive.allowed is False
    assert unnamed_destructive.reason == "no_safe_local_menu_candidate"

    disguised_goal_final = choose_sensitive_local_menu_action(
        [
            _element(
                "adb_7272727272727272",
                "보험 계약 조회",
                resource_id="com.example:id/delete_account_button",
            )
        ],
        goal_family_id="insurance_contract_lookup",
    )
    assert disguised_goal_final.allowed is False
    assert disguised_goal_final.boundary_kind == "sensitive_goal_entry_user_boundary"
    assert disguised_goal_final.action_guard is not None
    assert disguised_goal_final.action_guard.computed_final_or_consequential is True

    structural_switch = choose_sensitive_local_menu_action(
        [
            _element(
                "adb_7373737373737373",
                "마케팅 알림",
                checkable=False,
                class_name="android.widget.Switch",
            )
        ],
        goal_family_id="marketing_notifications_off",
    )
    assert structural_switch.allowed is False
    assert structural_switch.boundary_kind == "sensitive_goal_entry_user_boundary"

    structural_input = choose_sensitive_local_menu_action(
        [
            _element(
                "adb_7474747474747474",
                "계정",
                class_name="android.view.View",
                role="text_field",
            )
        ],
        goal_family_id="login",
    )
    assert structural_input.allowed is False

    forbidden = choose_sensitive_local_menu_action(
        [_element("adb_8888888888888888", "결제수단 관리")],
        goal_family_id="payment_methods",
    )
    assert forbidden.allowed is False
    assert forbidden.reason == "goal_family_not_allowed_in_sensitive_scope"

    insurance = choose_sensitive_local_menu_action(
        [_element("adb_9999999999999999", "보험 계약 조회")],
        goal_family_id="insurance_contract_lookup",
    )
    assert insurance.allowed is True
    assert insurance.terminal_policy == "user_boundary"
    assert insurance.score_bucket == "direct_goal_signal"
    assert insurance.matched_signal_ids == ("insurance.contract_lookup",)
    insurance_payload = json.dumps(insurance.evidence(), ensure_ascii=False)
    assert "보험 계약 조회" not in insurance_payload

    cancellation = choose_sensitive_local_menu_action(
        [_element("adb_aaaaaaaaaaaaaaaa", "보험 계약 해지")],
        goal_family_id="insurance_contract_cancel",
    )
    assert cancellation.allowed is False
    assert cancellation.terminal_policy == "user_boundary"
    assert cancellation.boundary_kind == "sensitive_goal_entry_user_boundary"
    assert "insurance.contract_cancel" in cancellation.matched_signal_ids

    signal_evidence = collect_sensitive_local_goal_signal_evidence(
        [
            _element("adb_9999999999999999", "보험 계약 조회"),
            _element("adb_aaaaaaaaaaaaaaaa", "보험 계약 해지"),
            _element(
                "adb_dddddddddddddddd", "마케팅 알림", checkable=True
            ),
        ]
    )
    by_family = {value.family_id: value for value in signal_evidence}
    assert by_family["insurance_contract_lookup"].terminal_policy == "user_boundary"
    assert by_family["insurance_contract_lookup"].auto_navigation_allowed is True
    assert by_family["insurance_contract_cancel"].action_guard.allowed is False
    assert by_family["marketing_notifications_off"].control_bucket == "checkable"
    assert by_family["marketing_notifications_off"].auto_navigation_allowed is False
    signal_json = json.dumps(
        [value.evidence() for value in signal_evidence], ensure_ascii=False
    )
    assert "보험 계약" not in signal_json
    assert "마케팅 알림" not in signal_json

    assert classify_sensitive_surface_boundary(
        [_element("adb_bbbbbbbbbbbbbbbb", "잔액 9,876,543원")]
    ) == "financial_content_boundary"
    assert classify_sensitive_surface_boundary(
        [_element("adb_cccccccccccccccc", "설정")]
    ) is None

    print("Real-device sensitive local navigation checks ok")


if __name__ == "__main__":
    main()
