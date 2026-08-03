from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_decision_memory import (  # noqa: E402
    NavigationDecisionMemory,
    canonical_json,
    is_dangerous_final_candidate,
    normalize_text,
    redact_text,
    stable_id,
)


SCHEMA_PATH = ROOT / "db" / "navigation_decision_v1.sql"
TARGET_FUNCTIONS = {
    "auth.signup.entry": "account.signup",
    "account.delete.entry": "account.delete",
    "subscription.entry": "membership.join",
    "subscription.change": "membership.change",
    "subscription.change.entry": "membership.change",
    "billing.manage": "membership.manage",
    "subscription.cancel.entry": "membership.cancel",
}
APP_SPLITS = {
    "com.netflix.mediaclient": ("test", "unseen multi-goal app held out from retrieval"),
    "com.google.android.youtube": ("validation", "unseen membership-cancellation app"),
}

GOALS = (
    ("account.signup", "account", "signup", "회원가입 진입", "medium", "stop_for_user"),
    ("account.delete", "account", "delete", "회원탈퇴 확인 화면 진입", "high", "stop_for_user"),
    ("membership.join", "membership", "join", "멤버십 가입 화면 진입", "high", "stop_for_user"),
    ("membership.manage", "membership", "manage", "현재 멤버십 관리 화면 진입", "low", "safe_navigation"),
    ("membership.change", "membership", "change", "멤버십 또는 요금제 변경 화면 진입", "high", "stop_for_user"),
    ("membership.cancel", "membership", "cancel", "멤버십 해지 확인 화면 진입", "high", "stop_for_user"),
)

GOAL_PHRASES: dict[str, tuple[tuple[str, str, float], ...]] = {
    "account.signup": (
        ("회원가입", "ko", 1.0), ("가입하기", "ko", 0.92), ("계정 만들기", "ko", 0.98),
        ("새 계정", "ko", 0.86), ("sign up", "en", 1.0), ("create account", "en", 1.0),
        ("register account", "en", 0.96),
    ),
    "account.delete": (
        ("회원탈퇴", "ko", 1.0), ("회원 탈퇴", "ko", 1.0), ("계정 삭제", "ko", 1.0),
        ("계정 폐쇄", "ko", 0.96), ("delete account", "en", 1.0), ("close account", "en", 0.96),
    ),
    "membership.join": (
        ("멤버십 가입", "ko", 1.0), ("멤버쉽 가입", "ko", 1.0), ("구독 가입", "ko", 0.98),
        ("프리미엄 가입", "ko", 0.98), ("subscribe", "en", 0.92), ("join membership", "en", 1.0),
    ),
    "membership.manage": (
        ("멤버십 관리", "ko", 1.0), ("멤버쉽 관리", "ko", 1.0), ("구독 관리", "ko", 0.98),
        ("플랜 관리", "ko", 0.94), ("멤버십", "ko", 0.64), ("membership management", "en", 1.0),
        ("manage subscription", "en", 0.98),
    ),
    "membership.change": (
        ("멤버십 변경", "ko", 1.0), ("멤버쉽 변경", "ko", 1.0), ("구독 변경", "ko", 0.98),
        ("요금제 변경", "ko", 1.0), ("플랜 변경", "ko", 0.98), ("change plan", "en", 1.0),
        ("change subscription", "en", 0.98),
    ),
    "membership.cancel": (
        ("구독 해지", "ko", 1.0), ("멤버십 해지", "ko", 1.0), ("멤버쉽 해지", "ko", 1.0),
        ("자동결제 해지", "ko", 0.98), ("프리미엄 해지", "ko", 0.98),
        ("cancel subscription", "en", 1.0), ("unsubscribe", "en", 1.0),
        ("end membership", "en", 0.96),
    ),
}

SIGNATURES: dict[str, dict[str, object]] = {
    "account.signup": {
        "name": "account creation gateway",
        "required": {"any_groups": [["회원가입", "계정 만들기", "sign up", "create account"], ["이메일", "전화번호", "비밀번호", "email", "phone", "password"]]},
        "optional": ["약관", "인증", "동의", "verification", "terms"],
        "forbidden": ["로그아웃", "회원탈퇴", "delete account"],
        "terminal": ["가입하기", "계정 생성", "create", "continue"],
        # A login page commonly exposes both credential fields and a
        # "회원가입" navigation link.  Require terminal-form evidence as well
        # before treating the screen as the account-creation boundary.
        "threshold": 0.78,
    },
    "account.delete": {
        "name": "account deletion confirmation boundary",
        "required": {"any_groups": [["회원탈퇴", "계정 삭제", "delete account", "close account"], ["주의", "삭제", "탈퇴", "warning", "permanent"]]},
        "optional": ["개인정보", "복구", "보유", "privacy", "recover"],
        "forbidden": ["프로필 삭제", "delete profile only"],
        "terminal": ["탈퇴하기", "삭제 확인", "영구 삭제", "confirm deletion"],
        "threshold": 0.66,
    },
    "membership.join": {
        "name": "membership purchase boundary",
        "required": {"any_groups": [["멤버십", "프리미엄", "구독", "membership", "premium", "subscription"], ["가격", "요금", "월", "price", "month", "plan"]]},
        "optional": ["혜택", "무료 체험", "다음 결제일", "이용권 구독", "benefits", "trial"],
        "forbidden": [
            "구독 피드",
            "subscriptions feed",
            "channels",
            "프리미엄 회원",
            "premium 회원",
            "현재 멤버십",
            "활성 멤버십",
            "구독 중",
            "혜택 이용중",
            "premium member",
            "current membership",
            "active membership",
            "already subscribed",
            "benefits active",
            "benefits in use",
        ],
        "terminal": ["가입", "구독", "구매", "subscribe", "purchase"],
        "threshold": 0.62,
    },
    "membership.manage": {
        "name": "current membership management",
        "required": {"any_groups": [["멤버십", "구독", "프리미엄", "membership", "subscription", "premium"], ["관리", "현재 요금제", "결제", "manage", "current plan", "billing"]]},
        "optional": ["다음 결제일", "갱신", "결제 수단", "renewal", "payment method"],
        "forbidden": ["구독 피드", "subscriptions feed", "channels"],
        "terminal": ["관리", "manage"],
        "threshold": 0.62,
    },
    "membership.change": {
        "name": "membership plan change boundary",
        "required": {"any_groups": [["멤버십", "요금제", "플랜", "membership", "plan"], ["변경", "업그레이드", "다운그레이드", "change", "upgrade", "downgrade"]]},
        "optional": ["현재 요금제", "가격", "적용일", "current", "effective"],
        "forbidden": ["구독 피드", "subscriptions feed"],
        "terminal": ["변경 확인", "적용", "confirm change"],
        "threshold": 0.66,
    },
    "membership.cancel": {
        "name": "membership cancellation boundary",
        "required": {"any_groups": [["멤버십", "구독", "프리미엄", "membership", "subscription", "premium"], ["해지", "취소", "종료", "cancel", "unsubscribe", "end"]]},
        "optional": ["다음 결제일", "이용 종료일", "환불", "next billing", "end date", "refund"],
        "forbidden": [
            "구독 피드",
            "subscriptions feed",
            "channels",
            "취소 반품 교환",
            "주문 취소",
            "order cancellation",
            "cancel return exchange",
        ],
        "terminal": ["해지 확인", "구독 취소", "confirm cancellation"],
        "threshold": 0.66,
    },
}

# A paid-plan purchase page is not the only valid membership-join boundary.
# Free member programs often present a benefits landing page before handing the
# user to account creation.  Keep this as a separate semantic family so a broad
# menu containing isolated "회원가입" and "혜택" entries is not mistaken for a
# destination.
ADDITIONAL_SIGNATURES: tuple[tuple[str, str, dict[str, object]], ...] = (
    (
        "membership.join",
        "ds_membership_join_subscription_entry_v1",
        {
            "name": "membership subscription enrollment entry boundary",
            "required": {
                "any_groups": [
                    [
                        "이용권 관리",
                        "멤버십 가입",
                        "멤버쉽 가입",
                        "membership plans",
                        "subscription plans",
                        "plan selection",
                    ],
                    [
                        "이용권 구독",
                        "새로운 이용권을 구독",
                        "멤버십 가입",
                        "멤버쉽 가입",
                        "구독하기",
                        "subscribe now",
                        "choose a plan",
                    ],
                ]
            },
            "optional": [
                "보유한 이용권이 없습니다",
                "요금제",
                "플랜",
                "가격",
                "월",
                "price",
                "month",
                "benefits",
            ],
            "forbidden": [
                "구독 피드",
                "subscriptions feed",
                "channels",
                "프리미엄 회원",
                "premium 회원",
                "현재 멤버십",
                "활성 멤버십",
                "구독 중",
                "혜택 이용중",
                "premium member",
                "current membership",
                "active membership",
                "already subscribed",
                "benefits active",
                "benefits in use",
            ],
            "terminal": [
                "이용권 구독",
                "구독하기",
                "subscribe now",
                "choose a plan",
            ],
            "threshold": 0.62,
        },
    ),
    (
        "membership.join",
        "ds_membership_join_member_benefits_v1",
        {
            "name": "member benefits enrollment boundary",
            "required": {
                "any_groups": [
                    [
                        "회원 전용 혜택",
                        "멤버십 전용 혜택",
                        "member-only benefits",
                        "membership benefits",
                    ],
                    [
                        "가입하고 혜택",
                        "가입 후 혜택",
                        "join and get benefits",
                        "sign up and get benefits",
                    ],
                ]
            },
            "optional": [
                "신규회원 혜택",
                "신규 회원 혜택",
                "포인트 적립",
                "회원 할인",
                "new member benefits",
                "earn points",
            ],
            "forbidden": [
                "구독 피드",
                "subscriptions feed",
                "channels",
                "프리미엄 회원",
                "premium 회원",
                "현재 멤버십",
                "활성 멤버십",
                "구독 중",
                "혜택 이용중",
                "premium member",
                "current membership",
                "active membership",
                "already subscribed",
                "benefits active",
                "benefits in use",
            ],
            "terminal": ["회원 가입", "멤버십 가입", "sign up", "join"],
            "threshold": 0.62,
        },
    ),
)

ROLE_ALIASES: dict[str, tuple[str, tuple[tuple[str, str, float], ...], str, bool]] = {
    "navigation.menu": ("전체 내비게이션 메뉴", (("메뉴", "ko", .94), ("더보기", "ko", .92), ("전체 메뉴", "ko", 1.0), ("전체메뉴", "ko", 1.0), ("탐색 서랍", "ko", .96), ("menu", "en", .94), ("more", "en", .86)), "low", False),
    "profile.hub": ("프로필 허브", (("프로필", "ko", 1.0), ("나의 넷플릭스", "ko", .96), ("profile", "en", 1.0)), "low", False),
    "account.hub": ("계정/마이페이지 허브", (("마이페이지", "ko", 1.0), ("내 페이지", "ko", 1.0), ("내 정보", "ko", .98), ("내정보", "ko", .98), ("내 계정", "ko", 1.0), ("계정", "ko", .96), ("마이쿠팡", "ko", .98), ("account", "en", .92), ("my account", "en", 1.0)), "low", False),
    "account.settings": ("계정 설정", (("계정 설정", "ko", 1.0), ("내정보관리", "ko", 1.0), ("회원정보", "ko", .94), ("설정", "ko", .72), ("account settings", "en", 1.0), ("settings", "en", .72)), "low", False),
    "privacy.settings": ("개인정보 설정", (("개인정보", "ko", .98), ("개인 정보", "ko", .98), ("privacy", "en", 1.0), ("personal information", "en", .96)), "low", False),
    "auth.entry": ("로그인/인증 진입", (("로그인", "ko", 1.0), ("인증", "ko", .78), ("log in", "en", 1.0), ("sign in", "en", 1.0)), "low", False),
    "auth.signup.entry": ("회원가입 진입", (("회원가입", "ko", 1.0), ("가입하기", "ko", .94), ("계정 만들기", "ko", 1.0), ("sign up", "en", 1.0), ("create account", "en", 1.0), ("register", "en", .92)), "medium", True),
    "account.delete.entry": ("회원탈퇴 진입", (("회원탈퇴", "ko", 1.0), ("회원 탈퇴", "ko", 1.0), ("계정 삭제", "ko", 1.0), ("delete account", "en", 1.0), ("close account", "en", .96)), "high", True),
    "billing.manage": ("결제/청구 관리", (("결제 관리", "ko", 1.0), ("구매 관리", "ko", .96), ("결제 수단", "ko", .90), ("청구", "ko", .88), ("billing", "en", 1.0), ("payments", "en", .92), ("purchases", "en", .88)), "low", False),
    "membership.hub": ("멤버십 관리 허브", (("멤버십 관리", "ko", 1.0), ("멤버쉽 관리", "ko", 1.0), ("구독 관리", "ko", .98), ("멤버십", "ko", .98), ("멤버쉽", "ko", .98), ("멤버스", "ko", .98), ("이용권", "ko", .96), ("프리미엄", "ko", .86), ("와우 멤버십", "ko", .98), ("membership", "en", .92), ("members", "en", .90), ("manage subscription", "en", 1.0), ("premium", "en", .86)), "low", False),
    "membership.join.entry": ("멤버십 가입 진입", (("멤버십 가입", "ko", 1.0), ("구독 가입", "ko", 1.0), ("프리미엄 가입", "ko", .98), ("이용권 구매", "ko", 1.0), ("이용권을 구매", "ko", 1.0), ("이용권 가입", "ko", 1.0), ("이용권 선택", "ko", .98), ("subscribe", "en", 1.0), ("join membership", "en", 1.0), ("view plans", "en", .98), ("choose a plan", "en", 1.0)), "high", True),
    "membership.change.entry": ("멤버십 변경 진입", (("멤버십 변경", "ko", 1.0), ("요금제 변경", "ko", 1.0), ("플랜 변경", "ko", .98), ("change plan", "en", 1.0), ("upgrade", "en", .86), ("downgrade", "en", .86)), "high", True),
    "membership.cancel.entry": ("멤버십 해지 진입", (("구독 해지", "ko", 1.0), ("멤버십 해지", "ko", 1.0), ("자동결제 해지", "ko", .98), ("cancel subscription", "en", 1.0), ("unsubscribe", "en", 1.0), ("end membership", "en", .96)), "high", True),
    "recovery.back": ("이전 화면 복구", (("뒤로가기", "ko", 1.0), ("이전", "ko", .72), ("back", "en", 1.0)), "low", False),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(value: str | None, fallback: object) -> object:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def seed_database(connection: sqlite3.Connection, source_sha256: str) -> None:
    created_at = utc_now()
    connection.executemany(
        "INSERT INTO goals(goal_id,family,operation,description,risk_class,terminal_action_policy) VALUES (?,?,?,?,?,?)",
        GOALS,
    )
    for goal_id, phrases in GOAL_PHRASES.items():
        for phrase, locale, confidence in phrases:
            phrase_id = stable_id("gp_", goal_id, locale, normalize_text(phrase))
            kind = "canonical" if confidence == 1.0 else "synonym"
            connection.execute(
                "INSERT INTO goal_phrases VALUES (?,?,?,?,?,?,?,?)",
                (phrase_id, goal_id, locale, phrase, normalize_text(phrase), kind, "redesign_seed", confidence),
            )
            connection.execute("INSERT INTO goal_phrase_fts(goal_id,phrase) VALUES (?,?)", (goal_id, phrase))
    for left, right in (("account.signup", "account.delete"), ("membership.join", "membership.cancel")):
        connection.execute("INSERT INTO goal_relations VALUES (?,?, 'opposite')", (left, right))
        connection.execute("INSERT INTO goal_relations VALUES (?,?, 'opposite')", (right, left))
    for goal_id, payload in SIGNATURES.items():
        connection.execute(
            """
            INSERT INTO destination_signatures(
                signature_id,goal_id,name,required_features_json,optional_features_json,
                forbidden_features_json,terminal_features_json,match_threshold,version
            ) VALUES (?,?,?,?,?,?,?,?,1)
            """,
            (
                f"ds_{goal_id.replace('.', '_')}_v1", goal_id, payload["name"],
                canonical_json(payload["required"]), canonical_json(payload["optional"]),
                canonical_json(payload["forbidden"]), canonical_json(payload["terminal"]),
                payload["threshold"],
            ),
        )
    for goal_id, signature_id, payload in ADDITIONAL_SIGNATURES:
        connection.execute(
            """
            INSERT INTO destination_signatures(
                signature_id,goal_id,name,required_features_json,optional_features_json,
                forbidden_features_json,terminal_features_json,match_threshold,version
            ) VALUES (?,?,?,?,?,?,?,?,1)
            """,
            (
                signature_id, goal_id, payload["name"],
                canonical_json(payload["required"]), canonical_json(payload["optional"]),
                canonical_json(payload["forbidden"]), canonical_json(payload["terminal"]),
                payload["threshold"],
            ),
        )
    for role_id, (description, aliases, risk, terminal) in ROLE_ALIASES.items():
        connection.execute(
            "INSERT INTO affordance_roles VALUES (?,?,?,?)",
            (role_id, description, risk, int(terminal)),
        )
        for alias, locale, confidence in aliases:
            negatives: list[str] = []
            if role_id == "membership.hub":
                negatives = ["구독 피드", "구독 채널", "subscriptions feed", "channels"]
            elif role_id == "navigation.menu":
                negatives = [
                    "작업 메뉴",
                    "추가 작업",
                    "동영상 작업",
                    "shorts",
                    "video actions",
                ]
            connection.execute(
                "INSERT INTO affordance_role_aliases VALUES (?,?,?,?,?,?,?)",
                (
                    stable_id("ara_", role_id, locale, normalize_text(alias)), role_id, locale,
                    alias, normalize_text(alias), confidence, canonical_json(negatives),
                ),
            )
    metadata = {
        "schema_version": "1",
        "database_kind": "navigation_decision_memory",
        "scope": "account.signup,account.delete,membership.*",
        "source_sha256": source_sha256,
        "raw_screen_data_policy": "semantic_redacted_only",
        "created_at": created_at,
        "transform_version": "navigation-decision-migration-v1",
    }
    connection.executemany("INSERT INTO navigation_db_metadata VALUES (?,?)", metadata.items())


def _sanitized_observation(context: dict[str, object]) -> dict[str, object]:
    sanitized: list[dict[str, object]] = []
    for item in context.get("elements", []) if isinstance(context.get("elements"), list) else []:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id") or item.get("element_id") or "")
        source_parent = str(item.get("parent_id") or "")
        sanitized.append(
            {
                "node_id": stable_id("node_", source_id) if source_id else "",
                "parent_node_id": stable_id("node_", source_parent) if source_parent else "",
                "role": normalize_text(str(item.get("role") or "unknown")),
                "label": redact_text(str(item.get("label") or item.get("text") or "")),
                "clickable": bool(item.get("clickable")),
                "scrollable": bool(item.get("scrollable")),
            }
        )
    return {
        "window_title": redact_text(str(context.get("window_title") or "")),
        "activity_semantics": "webview" if "webview" in normalize_text(str(context.get("activity_name") or "")) else "native",
        "elements": sanitized[:500],
    }


def _action_payload(raw: object) -> tuple[str, str | None]:
    payload = raw if isinstance(raw, dict) else {}
    name = str(payload.get("name") or "")
    if name == "click_element":
        candidate_id = str((payload.get("arguments") or {}).get("candidate_id") or "") if isinstance(payload.get("arguments"), dict) else ""
        return "click", candidate_id or None
    if name in {"scroll_forward", "scroll_down"}:
        return "scroll", "down"
    if name == "scroll_up":
        return "scroll", "up"
    if name == "back":
        return "back", None
    if name == "mark_destination":
        return "stop_for_user", None
    return "wait_and_observe", None


def _insert_screen_and_affordances(
    connection: sqlite3.Connection,
    memory: NavigationDecisionMemory,
    *,
    context: dict[str, object],
    candidates: list[dict[str, object]],
    app_package: str,
    app_version: str,
    locale: str,
    source_ref: str,
    source_screen_fingerprint: str,
    captured_at: str,
    source_type: str,
) -> tuple[str, dict[str, str]]:
    state = memory.semantic_screen_state(
        window_title=str(context.get("window_title") or ""),
        activity_name=str(context.get("activity_name") or ""),
        candidates=candidates,
        locale=locale,
    )
    screen_id = stable_id("screen_", state.semantic_fingerprint)
    role_counts: dict[str, int] = {}
    for candidate in state.candidate_payloads:
        role = str(candidate["role"])
        role_counts[role] = role_counts.get(role, 0) + 1
    now = utc_now()
    connection.execute(
        """
        INSERT INTO semantic_screens(
            screen_id,semantic_fingerprint,title_normalized,region_roles_json,navigation_depth,
            auth_state,surface_type,semantic_tokens_json,source_hash,created_at,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(semantic_fingerprint) DO UPDATE SET updated_at=excluded.updated_at
        """,
        (
            screen_id, state.semantic_fingerprint, normalize_text(state.title), canonical_json(role_counts),
            None, state.auth_state, state.surface_type, canonical_json(state.tokens),
            hashlib.sha256(source_screen_fingerprint.encode("utf-8")).hexdigest(), now, now,
        ),
    )
    observation_id = stable_id("obs_", source_ref, source_screen_fingerprint)
    native_observation = _sanitized_observation(context)
    ocr_labels = [
        redact_text(str(item.get("label") or ""))
        for item in candidates
        if str(item.get("element_id") or "").startswith("ocr_")
    ]
    connection.execute(
        """
        INSERT OR IGNORE INTO screen_observations(
            observation_id,screen_id,app_package,app_version,locale,accessibility_json,
            ocr_json,vlm_json,source_type,captured_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            observation_id, screen_id, app_package, app_version, locale,
            canonical_json(native_observation), canonical_json({"labels": ocr_labels}), "{}",
            source_type, captured_at or now,
        ),
    )
    source_to_affordance: dict[str, str] = {}
    occurrence: dict[tuple[str, str], int] = {}
    payload_by_id = {str(item["candidate_id"]): item for item in state.candidate_payloads}
    for candidate in candidates:
        source_id = str(candidate.get("element_id") or "")
        payload = payload_by_id.get(source_id)
        if payload is None:
            continue
        label = str(payload["label"])
        role = str(payload["role"])
        occurrence_key = (normalize_text(label), role)
        occurrence[occurrence_key] = occurrence.get(occurrence_key, 0) + 1
        candidate_key = stable_id("cand_", occurrence_key, occurrence[occurrence_key])
        affordance_id = stable_id("aff_", screen_id, candidate_key)
        risk_level = str(payload["risk_level"])
        if risk_level not in {"low", "medium", "high", "blocked"}:
            risk_level = "low"
        connection.execute(
            """
            INSERT OR IGNORE INTO affordances(
                affordance_id,screen_id,candidate_key,label,normalized_label,icon_semantics,role,
                parent_semantics,nearby_text,position_bucket,risk_level,dangerous_final,
                function_roles_json,source_element_key
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                affordance_id, screen_id, candidate_key, label, normalize_text(label), "", role,
                "", "", "unknown", risk_level, int(is_dangerous_final_candidate(label)),
                canonical_json(payload["inferred_function_roles"]),
                hashlib.sha256(str(candidate.get("element_key") or source_id).encode("utf-8")).hexdigest()[:20],
            ),
        )
        source_to_affordance[source_id] = affordance_id
    connection.execute(
        "INSERT OR IGNORE INTO evidence_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            stable_id("ev_", "screen", screen_id, source_ref), "screen", screen_id, source_type,
            source_ref, 1, .94, app_package, app_version, locale, captured_at or now,
        ),
    )
    return screen_id, source_to_affordance


def migrate(source: Path, target: Path, schema: Path, report_path: Path, split_path: Path) -> dict[str, object]:
    if source.resolve() == target.resolve():
        raise ValueError("source and target DB must be different files")
    if target.exists():
        raise FileExistsError(f"refusing to replace existing target DB: {target}")
    source_sha256 = file_sha256(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    source_connection: sqlite3.Connection | None = None
    try:
        connection.executescript(schema.read_text(encoding="utf-8"))
        seed_database(connection, source_sha256)
        for app_package, (split, reason) in APP_SPLITS.items():
            connection.execute(
                "INSERT INTO evaluation_app_splits VALUES ('app-disjoint-v1',?,?,?)",
                (app_package, split, reason),
            )
        connection.commit()
        memory = NavigationDecisionMemory(target, read_only=False)
        source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        source_connection.row_factory = sqlite3.Row
        examples = source_connection.execute(
            """
            SELECT * FROM navigation_training_examples
            WHERE provenance = 'real_device_human_gold'
            ORDER BY source_recording_id, step_ordinal, example_id
            """
        ).fetchall()
        pending_outcomes: list[tuple[str, str, str, str, str]] = []
        migrated_by_goal: dict[str, int] = {}
        migrated_by_app: dict[str, int] = {}
        excluded_non_scope = 0
        for row in examples:
            goal_id = TARGET_FUNCTIONS.get(str(row["target_function"]))
            if goal_id is None:
                excluded_non_scope += 1
                continue
            context = load_json(row["screen_context_json"], {})
            candidates = load_json(row["candidates_json"], [])
            action_payload = load_json(row["correct_action_json"], {})
            if not isinstance(context, dict) or not isinstance(candidates, list):
                continue
            candidate_dicts = [item for item in candidates if isinstance(item, dict)]
            action, action_detail = _action_payload(action_payload)
            screen_id, source_map = _insert_screen_and_affordances(
                connection,
                memory,
                context=context,
                candidates=candidate_dicts,
                app_package=str(row["app_package"]),
                app_version=str(row["app_version"]),
                locale=str(row["locale"]),
                source_ref=str(row["example_id"]),
                source_screen_fingerprint=str(row["screen_fingerprint"]),
                captured_at=str(row["created_at"]),
                source_type="human_gold",
            )
            chosen_affordance_id = source_map.get(action_detail or "") if action == "click" else None
            if action == "click" and chosen_affordance_id is None:
                continue
            signature_id = f"ds_{goal_id.replace('.', '_')}_v1"
            case_id = stable_id("case_", row["example_id"])
            connection.execute(
                """
                INSERT INTO decision_cases(
                    case_id,goal_id,screen_id,goal_text_normalized,goal_conditions_json,
                    chosen_action,chosen_affordance_id,scroll_direction,
                    expected_destination_signature_id,source_app_package,source_record_id,
                    source_step_ordinal,source_type,evidence_weight,observed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    case_id, goal_id, screen_id, normalize_text(str(row["goal_text"])), "{}",
                    action, chosen_affordance_id,
                    action_detail if action == "scroll" else None, signature_id,
                    str(row["app_package"]), str(row["source_recording_id"]), int(row["step_ordinal"]),
                    "human_gold", .98, str(row["created_at"]),
                ),
            )
            connection.execute(
                "INSERT INTO evidence_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    stable_id("ev_", "decision_case", case_id), "decision_case", case_id,
                    "human_gold", str(row["example_id"]), 1, .98, str(row["app_package"]),
                    str(row["app_version"]), str(row["locale"]), str(row["created_at"]),
                ),
            )
            selected_label = ""
            if chosen_affordance_id:
                selected_label = str(connection.execute("SELECT label FROM affordances WHERE affordance_id=?", (chosen_affordance_id,)).fetchone()[0])
            connection.execute(
                "INSERT INTO decision_case_fts(case_id,goal_id,search_text) VALUES (?,?,?)",
                (
                    case_id, goal_id,
                    " ".join((str(row["goal_text"]), str(context.get("window_title") or ""), selected_label,
                              *(str(item.get("label") or "") for item in candidate_dicts[:100]))),
                ),
            )
            pending_outcomes.append(
                (
                    case_id, screen_id, str(row["next_screen_fingerprint"] or ""),
                    str(row["destination_screen_fingerprint"] or ""), str(row["outcome"] or "unknown"),
                )
            )
            migrated_by_goal[goal_id] = migrated_by_goal.get(goal_id, 0) + 1
            package = str(row["app_package"])
            migrated_by_app[package] = migrated_by_app.get(package, 0) + 1
            if package not in APP_SPLITS:
                connection.execute(
                    "INSERT OR IGNORE INTO evaluation_app_splits VALUES ('app-disjoint-v1',?,'train','migration source; never used when held out')",
                    (package,),
                )

        legacy_screen_map = {
            str(row["source_record_id"]): str(row["screen_id"])
            for row in connection.execute(
                """
                SELECT e.source_ref AS source_record_id, e.entity_id AS screen_id
                FROM evidence_records AS e WHERE e.entity_type='screen'
                """
            )
        }
        # The old screen fingerprint is intentionally not persisted in plain
        # text. Resolve next screens by matching its one-way source_hash.
        hash_to_screen = dict(connection.execute("SELECT source_hash,screen_id FROM semantic_screens"))
        for case_id, screen_id, next_fp, destination_fp, source_outcome in pending_outcomes:
            next_screen_id = hash_to_screen.get(hashlib.sha256(next_fp.encode("utf-8")).hexdigest()) if next_fp else None
            reached = bool(destination_fp and next_fp == destination_fp)
            action = str(connection.execute("SELECT chosen_action FROM decision_cases WHERE case_id=?", (case_id,)).fetchone()[0])
            if action == "stop_for_user" or reached:
                outcome_type, progress, before, after, state_changed = "destination_reached", "reached", 0.0, 1.0, int(next_screen_id != screen_id) if next_screen_id else 0
            elif source_outcome == "navigated":
                outcome_type, progress, before, after, state_changed = "navigated", "advanced", 0.0, None, int(next_screen_id != screen_id) if next_screen_id else 1
            elif source_outcome == "no_change":
                outcome_type, progress, before, after, state_changed = "no_change", "unchanged", 0.0, 0.0, 0
            else:
                outcome_type, progress, before, after, state_changed = "unknown", "unknown", None, None, None
            outcome_id = stable_id("out_", case_id)
            connection.execute(
                """
                INSERT INTO transition_outcomes(
                    outcome_id,case_id,next_screen_id,outcome_type,connectivity_status,state_changed,
                    destination_match_before,destination_match_after,distance_before,distance_after,
                    distance_method,progress_label,failure_class,external_target,observed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    outcome_id, case_id, next_screen_id, outcome_type, "observed", state_changed,
                    before, after, None, None, "semantic_signature_only", progress, "", "", utc_now(),
                ),
            )
            connection.execute(
                "INSERT INTO evidence_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    stable_id("ev_", "transition_outcome", outcome_id), "transition_outcome", outcome_id,
                    "human_gold", case_id, 1, .96, "", "", "", utc_now(),
                ),
            )

        failure_rows = source_connection.execute(
            """
            SELECT a.attempt_id,a.screen_fingerprint,a.action_id,a.element_key,a.label,a.command,a.outcome,
                   a.to_screen_fingerprint,e.goal_text,e.target_function,e.app_key,u.app_package,u.app_version,u.locale,
                   s.activity_name,s.title,s.structure_json
            FROM universal_exploration_attempts AS a
            JOIN universal_explorations AS e USING(exploration_id)
            JOIN universal_apps AS u ON u.app_key=e.app_key
            LEFT JOIN universal_screens AS s ON s.screen_fingerprint=a.screen_fingerprint
            WHERE a.outcome='failed'
            ORDER BY a.attempt_id
            """
        ).fetchall()
        migrated_failures = 0
        for row in failure_rows:
            goal_id = TARGET_FUNCTIONS.get(str(row["target_function"]))
            if goal_id is None:
                continue
            context = load_json(row["structure_json"], {})
            if not isinstance(context, dict):
                context = {}
            context.setdefault("activity_name", str(row["activity_name"] or ""))
            context.setdefault("window_title", str(row["title"] or ""))
            candidate_rows = source_connection.execute(
                "SELECT action_id AS element_id,element_key,label,role,risk_level,risk_reason FROM universal_actions WHERE screen_fingerprint=?",
                (row["screen_fingerprint"],),
            ).fetchall()
            candidates = [dict(item) for item in candidate_rows]
            screen_id, source_map = _insert_screen_and_affordances(
                connection, memory, context=context, candidates=candidates,
                app_package=str(row["app_package"]), app_version=str(row["app_version"]), locale=str(row["locale"]),
                source_ref=str(row["attempt_id"]), source_screen_fingerprint=str(row["screen_fingerprint"]), captured_at=utc_now(),
                source_type="real_device",
            )
            chosen_id = source_map.get(str(row["action_id"] or ""))
            if chosen_id is None:
                continue
            case_id = stable_id("case_failure_", row["attempt_id"])
            connection.execute(
                """
                INSERT INTO decision_cases(
                    case_id,goal_id,screen_id,goal_text_normalized,goal_conditions_json,
                    chosen_action,chosen_affordance_id,scroll_direction,
                    expected_destination_signature_id,source_app_package,source_record_id,
                    source_step_ordinal,source_type,evidence_weight,observed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    case_id, goal_id, screen_id, normalize_text(str(row["goal_text"])), "{}",
                    "click", chosen_id, None,
                    f"ds_{goal_id.replace('.', '_')}_v1", str(row["app_package"]), str(row["attempt_id"]),
                    0, "real_device", .72, utc_now(),
                ),
            )
            outcome_id = stable_id("out_", case_id)
            connection.execute(
                """
                INSERT INTO transition_outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    outcome_id, case_id, None, "no_change", "observed", 0, 0.0, 0.0,
                    None, None, "not_measured", "unchanged", "observed_click_failed", "", utc_now(),
                ),
            )
            recovery_id = stable_id("rec_", case_id)
            connection.execute(
                "INSERT INTO recovery_memories VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    recovery_id, goal_id, screen_id, chosen_id, "observed_click_failed", "back", None,
                    "not_observed", 0, case_id, utc_now(),
                ),
            )
            connection.executemany(
                "INSERT INTO evidence_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    (stable_id("ev_", "decision_case", case_id), "decision_case", case_id, "real_device", str(row["attempt_id"]), 1, .72, str(row["app_package"]), str(row["app_version"]), str(row["locale"]), utc_now()),
                    (stable_id("ev_", "recovery_memory", recovery_id), "recovery_memory", recovery_id, "real_device", str(row["attempt_id"]), 1, .62, str(row["app_package"]), str(row["app_version"]), str(row["locale"]), utc_now()),
                ),
            )
            failure_package = str(row["app_package"])
            failure_split, failure_reason = APP_SPLITS.get(
                failure_package,
                ("train", "real-device failure evidence; excluded whenever this app is evaluated"),
            )
            connection.execute(
                "INSERT OR IGNORE INTO evaluation_app_splits VALUES ('app-disjoint-v1',?,?,?)",
                (failure_package, failure_split, failure_reason),
            )
            migrated_failures += 1

        connection.commit()
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in (
                "goals", "goal_phrases", "destination_signatures", "affordance_roles",
                "affordance_role_aliases", "semantic_screens", "screen_observations", "affordances",
                "decision_cases", "transition_outcomes", "recovery_memories", "evidence_records",
            )
        }
    except Exception:
        connection.close()
        if target.exists():
            target.unlink()
        raise
    finally:
        if source_connection is not None:
            source_connection.close()
    connection.close()
    target_sha256 = file_sha256(target)
    split_payload = {
        "schema_version": 1,
        "split_version": "app-disjoint-v1",
        "policy": "an app package occurs in exactly one split; retrieval excludes the evaluated app",
        "apps": [
            {"app_package": package, "split": APP_SPLITS.get(package, ("train", "migration source"))[0]}
            for package in sorted(migrated_by_app)
        ],
        "known_coverage_gap": "membership.join has one source app and cannot support a credible unseen-app estimate",
    }
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_text(json.dumps(split_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "schema_version": 1,
        "source": {"path": str(source), "sha256": source_sha256, "read_only": True},
        "target": {"path": str(target), "sha256": target_sha256, "quick_check": quick_check},
        "scope": sorted(set(TARGET_FUNCTIONS.values())),
        "counts": counts,
        "migrated_human_gold_by_goal": dict(sorted(migrated_by_goal.items())),
        "migrated_cases_by_app": dict(sorted(migrated_by_app.items())),
        "migrated_failure_cases": migrated_failures,
        "excluded_non_scope_training_examples": excluded_non_scope,
        "explicit_exclusions": {
            "legacy_app_routes": "not served; Gold was split into decision cases",
            "full_function_catalog": "not imported; compact role aliases only",
            "raw_coordinates": "not imported",
            "raw_identifiers": "one-way hashed where provenance linkage is required",
        },
        "privacy": (
            "screen labels are normalized and email, handle, masked-name, phone, "
            "currency-amount, and long-number patterns are redacted"
        ),
        "generated_at": utc_now(),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy Navigation v2 evidence into decision-memory v1")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = migrate(
        args.source.resolve(), args.target.resolve(), args.schema.resolve(),
        args.report.resolve(), args.split_manifest.resolve(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
