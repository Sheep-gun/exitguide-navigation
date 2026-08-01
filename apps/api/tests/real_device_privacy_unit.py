from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.real_device_privacy import (  # noqa: E402
    REDACTED,
    classify_human_text,
    classify_human_values,
    redact_if_sensitive,
)


def _has(value: str, category: str, *, field_name: str = "text") -> None:
    finding = classify_human_text(value, field_name=field_name)
    assert finding.metadata_only, (value, finding)
    assert category in finding.categories, (category, finding)
    assert value not in repr(finding), "findings must not retain source text"


def main() -> None:
    _has("문의: tester@example.test", "email")
    _has("연락처 010-1234-5678", "phone")
    _has("고객센터 1599-1500", "phone")
    _has("대표전화 02-1234-5678", "phone")
    _has("주민번호 900101-1234567", "korean_resident_id")
    _has("카드 4111 1111 1111 1111", "payment_card")
    _has("프로필 @sample_user", "account_handle")
    _has("사용자 이름: sample_user", "account_identifier_context")
    _has("서울특별시 테스트구 샘플로 123", "postal_address")
    _has("현재 위치를 배송지로 설정", "location_or_address_context")
    _has("받는 사람: 홍길동", "personal_name")
    _has("홍길동님, 반갑습니다", "personal_name")
    _has("계좌 잔액 12,345원", "financial_balance")
    _has("주문번호 ABC-123", "order_or_booking_data")
    _has("보험 계약번호 TEST-123", "insurance_data")
    _has("인증번호를 입력하세요", "authentication_data")
    _has("Authorization: Bearer abcdefghijklmnop", "secret", field_name="element_id")

    opaque = "task_a3645d76d16f6d51-000-a05f5051:node_01012345678"
    structural = classify_human_text(opaque, field_name="element_id")
    assert structural.metadata_only is False, structural
    assert structural.categories == (), structural

    resource_ids = classify_human_text(
        "com.example:id/profile_name_label",
        field_name="resource_ids_json",
        path="screens.resource_ids_json[rowid=1][0]",
    )
    assert resource_ids.metadata_only is False, resource_ids
    assert resource_ids.categories == (), resource_ids

    element_key = classify_human_text(
        "an_15991500_profile_name",
        field_name="element_key",
    )
    assert element_key.metadata_only is False, element_key
    assert element_key.categories == (), element_key

    hash_with_phone_like_digits = "a01012345678bcdef0123456789abcdef0123456789abcdef0123456789abcd"
    structural_hash = classify_human_text(
        hash_with_phone_like_digits,
        field_name="observations.jsonl",
        path="manifest.artifact_sha256.observations.jsonl",
    )
    assert structural_hash.metadata_only is False, structural_hash
    assert structural_hash.categories == (), structural_hash

    for field_name, machine_value in (
        ("completed_task_ids", "task_161048055a5fa6b6"),
        ("api_ms", "1012345678.25"),
        ("performed_at_epoch_ms", "1785529698123"),
        (
            "accessibility_tree_path",
            "apps/com.google.android.youtube/trees/task_161048055a5fa6b6-000-01012345678.sanitized.xml",
        ),
    ):
        machine_finding = classify_human_text(machine_value, field_name=field_name)
        assert machine_finding.metadata_only is False, machine_finding
        assert machine_finding.categories == (), machine_finding
    secret_path = classify_human_text(
        "apps/flp_abcdefghijklmnop/trees/capture.xml",
        field_name="accessibility_tree_path",
    )
    assert secret_path.metadata_only is True
    assert "secret" in secret_path.categories
    secret_timing = classify_human_text(
        "flp_abcdefghijklmnop",
        field_name="api_ms",
    )
    assert secret_timing.metadata_only is True
    assert "secret" in secret_timing.categories

    benign = (
        "설정",
        "구독 관리",
        "상품 가격 12,000원",
        "고객님을 위한 도움말",
        "android.widget.Button",
        "보험 계약 조회",
        "보험금 청구",
        "이름 없는 상단 가운데 아이콘",
    )
    for value in benign:
        finding = classify_human_text(value, field_name="text")
        assert finding.metadata_only is False, (value, finding)

    for goal in ("보험 계약 조회", "배송지 관리", "비밀번호 변경", "주문 내역 조회"):
        finding = classify_human_text(goal, field_name="goal_text", path="goals[0].goal_text")
        assert finding.metadata_only is False, (goal, finding)
    # Direct identifiers remain blocked even when a user embeds them in a goal.
    direct_goal = classify_human_text(
        "계정 tester@example.test 삭제",
        field_name="user_goal",
        path="request.user_goal",
    )
    assert direct_goal.metadata_only is True
    assert "email" in direct_goal.categories

    combined = classify_human_values(
        (
            ("element_id", "elements[0].element_id", opaque),
            ("text", "elements[0].text", "배송 주소를 확인하세요"),
        )
    )
    assert combined.metadata_only is True
    assert combined.categories == ("location_or_address_context",)
    assert redact_if_sensitive("프로필 @sample_user", field_name="text") == REDACTED
    assert redact_if_sensitive(opaque, field_name="element_id") == opaque
    print("Real-device privacy classifier checks ok")


if __name__ == "__main__":
    main()
