from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_decision_memory import normalize_text, stable_id  # noqa: E402


PATCH_VERSION = "navigation-decision-patch-20260804-membership-join-boundary-v1"
ALIASES = (
    ("account.hub", "ko", "계정", 0.96, []),
    (
        "membership.hub",
        "ko",
        "이용권",
        0.96,
        ["구독 피드", "구독 채널", "subscriptions feed", "channels"],
    ),
    ("membership.join.entry", "ko", "이용권 구매", 1.0, []),
    ("membership.join.entry", "ko", "이용권을 구매", 1.0, []),
    ("membership.join.entry", "ko", "이용권 가입", 1.0, []),
    ("membership.join.entry", "ko", "이용권 선택", 0.98, []),
    ("membership.join.entry", "en", "view plans", 0.98, []),
    ("membership.join.entry", "en", "choose a plan", 1.0, []),
)

SUBSCRIPTION_ENTRY_SIGNATURE = {
    "signature_id": "ds_membership_join_subscription_entry_v1",
    "goal_id": "membership.join",
    "name": "membership subscription enrollment entry boundary",
    "required_features": {
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
    "optional_features": [
        "보유한 이용권이 없습니다",
        "요금제",
        "플랜",
        "가격",
        "월",
        "price",
        "month",
        "benefits",
    ],
    "forbidden_features": [
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
    "terminal_features": [
        "이용권 구독",
        "구독하기",
        "subscribe now",
        "choose a plan",
    ],
    "match_threshold": 0.62,
    "version": 1,
}


def apply_patches(database: Path) -> dict[str, object]:
    database = database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(database)

    connection = sqlite3.connect(database)
    try:
        integrity_before = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity_before != "ok":
            raise RuntimeError(f"database integrity check failed: {integrity_before}")

        connection.execute("BEGIN IMMEDIATE")
        inserted = 0
        unchanged = 0
        for role_id, locale, alias, confidence, negatives in ALIASES:
            if connection.execute(
                "SELECT 1 FROM affordance_roles WHERE role_id = ?", (role_id,)
            ).fetchone() is None:
                raise RuntimeError(f"missing affordance role: {role_id}")
            normalized = normalize_text(alias)
            existing = connection.execute(
                """
                SELECT confidence, negative_context_json
                FROM affordance_role_aliases
                WHERE role_id = ? AND locale = ? AND normalized_alias = ?
                """,
                (role_id, locale, normalized),
            ).fetchone()
            expected_negatives = json.dumps(negatives, ensure_ascii=False, separators=(",", ":"))
            if existing is not None:
                if float(existing[0]) != confidence or str(existing[1]) != expected_negatives:
                    raise RuntimeError(
                        f"existing alias differs from patch contract: {role_id}/{locale}/{normalized}"
                    )
                unchanged += 1
                continue
            connection.execute(
                """
                INSERT INTO affordance_role_aliases(
                    alias_id, role_id, locale, alias, normalized_alias,
                    confidence, negative_context_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stable_id("ara_", role_id, locale, normalized),
                    role_id,
                    locale,
                    alias,
                    normalized,
                    confidence,
                    expected_negatives,
                ),
            )
            inserted += 1
        signature = SUBSCRIPTION_ENTRY_SIGNATURE
        expected_signature = (
            signature["goal_id"],
            signature["name"],
            json.dumps(
                signature["required_features"],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            json.dumps(
                signature["optional_features"],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            json.dumps(
                signature["forbidden_features"],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            json.dumps(
                signature["terminal_features"],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            signature["match_threshold"],
            signature["version"],
        )
        existing_signature = connection.execute(
            """
            SELECT goal_id, name, required_features_json, optional_features_json,
                   forbidden_features_json, terminal_features_json, match_threshold, version
            FROM destination_signatures WHERE signature_id = ?
            """,
            (signature["signature_id"],),
        ).fetchone()
        inserted_signatures = 0
        unchanged_signatures = 0
        if existing_signature is None:
            connection.execute(
                """
                INSERT INTO destination_signatures(
                    signature_id, goal_id, name, required_features_json,
                    optional_features_json, forbidden_features_json,
                    terminal_features_json, match_threshold, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (signature["signature_id"], *expected_signature),
            )
            inserted_signatures = 1
        elif tuple(existing_signature) == expected_signature:
            unchanged_signatures = 1
        else:
            raise RuntimeError(
                "existing membership.join subscription-entry signature differs from patch contract"
            )
        connection.execute(
            """
            INSERT INTO navigation_db_metadata(key, value) VALUES ('ontology_patch_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (PATCH_VERSION,),
        )
        connection.commit()
        integrity_after = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity_after != "ok":
            raise RuntimeError(f"database integrity check failed after patch: {integrity_after}")
        return {
            "database": str(database),
            "patch_version": PATCH_VERSION,
            "inserted_aliases": inserted,
            "unchanged_aliases": unchanged,
            "inserted_signatures": inserted_signatures,
            "unchanged_signatures": unchanged_signatures,
            "integrity_check": integrity_after,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply idempotent, evidence-backed Navigation Decision DB patches"
    )
    parser.add_argument("--database", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    print(json.dumps(apply_patches(parse_args().database), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
