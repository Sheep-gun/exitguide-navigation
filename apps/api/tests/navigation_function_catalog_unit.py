import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.navigation_function_catalog import (
    CatalogValidationError,
    NavigationFunctionCatalog,
    validate_catalog_payload,
)


def _metadata_catalog_payload() -> dict[str, object]:
    return {
        "catalog_version": "test-unicode-metadata",
        "functions": [
            {
                "function_id": "locale.japanese",
                "domain": "settings",
                "name_ko": "설정",
                "name_en": "Settings",
                "description": "Japanese-locale destination.",
                "risk_level": "low",
                "automation_policy": "safe_navigation",
                "terminal": True,
                "state_changing": False,
                "aliases": {
                    "ja": ["設定"],
                    "en": ["settings"],
                    "fr": ["Réglages"],
                    "zh-CN": ["设置"],
                },
                "scope": "application",
                "node_kind": "destination",
                "stop_policy": "at_destination",
                "role_hints": ["button"],
                "state_cues": {
                    "selected": True,
                    "enabled": True,
                    "checkable": True,
                    "checked": True,
                },
                "risk_cues": ["external handoff"],
            },
            {
                "function_id": "locale.chinese",
                "domain": "settings",
                "name_ko": "구성",
                "name_en": "Configuration",
                "description": "Traditional-Chinese locale destination.",
                "risk_level": "low",
                "automation_policy": "safe_navigation",
                "terminal": True,
                "state_changing": False,
                "aliases": {"zh-TW": ["設定"], "en": ["configuration"]},
                "role_hints": ["menuitem"],
                "state_cues": {
                    "selected": False,
                    "checkable": True,
                    "checked": False,
                    "off": ["사용 안 함", "Disabled"],
                },
            },
            {
                "function_id": "danger.confirm",
                "domain": "account",
                "name_ko": "위험 작업 확정",
                "name_en": "Confirm dangerous action",
                "description": "User-only state change.",
                "risk_level": "high",
                "automation_policy": "never_auto",
                "terminal": True,
                "state_changing": True,
                "aliases": [
                    {"locale": "ko-KR", "phrase": "확정"},
                    {"locale": "en", "phrase": "confirm"},
                ],
                "stop_policy": "user_confirmation",
                "risk_cues": ["irreversible", "billing"],
                "semantic_concepts": ["confirmation"],
                "semantic_terminal_concepts": ["confirmation"],
            },
        ],
        "intents": [
            {
                "intent_id": "open_settings",
                "terminal_function": "locale.japanese",
                "patterns": ["설정 열기"],
                "goal_rules": [
                    {
                        "all_of": ["最終", "設定"],
                        "score": 1.0,
                        "terminal_function": "locale.chinese",
                    }
                ],
                "route": [{"function_id": "locale.japanese", "weight": 1.0}],
                "avoid_functions": ["danger.confirm"],
            }
        ],
        "gateway_rules": [],
        "supplemental_goal_rules": [
            {
                "intent_id": "open_settings",
                "all_of": ["system preferences", "supplemental cue"],
                "score": 1.0,
                "source_pack": "unit_test",
            }
        ],
        "semantic_lexicon": {
            "confirmation": {
                "ko-KR": ["최종 확인"],
                "en-US": ["final confirmation"],
            }
        },
    }


def _assert_unicode_locale_and_metadata_runtime(temporary_directory: str) -> None:
    payload = _metadata_catalog_payload()
    catalog_path = Path(temporary_directory) / "metadata-catalog.json"
    database_path = Path(temporary_directory) / "metadata-catalog.sqlite"
    catalog_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    catalog = NavigationFunctionCatalog(database_path, catalog_path)
    catalog.validate()
    metadata_stats = catalog.stats()
    assert metadata_stats["role_hint_count"] == 2
    assert metadata_stats["state_cue_count"] == 9
    assert metadata_stats["risk_cue_count"] == 3
    assert metadata_stats["semantic_concept_count"] == 1
    assert metadata_stats["semantic_terminal_concept_count"] == 1
    assert metadata_stats["semantic_lexicon_phrase_count"] == 2

    assert catalog.match_candidate(label="設定", locale="ja-JP")[0].function_id == "locale.japanese"
    assert catalog.match_candidate(label="設定", locale="zh_TW")[0].function_id == "locale.chinese"
    assert catalog.match_candidate(label="设置", locale="zh-CN")[0].function_id == "locale.japanese"
    assert catalog.match_candidate(label="ＲÉＧＬＡＧＥＳ", locale="fr-FR")[0].function_id == "locale.japanese"
    assert catalog.match_candidate(label="ＳＥＴＴＩＮＧＳ", locale="de-DE")[0].function_id == "locale.japanese"
    assert catalog.match_candidate(label="設定", role="button")[0].function_id == "locale.japanese"
    assert catalog.match_candidate(label="設定", role="menuitem")[0].function_id == "locale.chinese"

    selected = catalog.match_candidate(
        label="設定", selected=True, enabled=True, checkable=True, checked=True
    )
    unselected = catalog.match_candidate(
        label="設定", selected=False, enabled=True, checkable=True, checked=False
    )
    assert selected[0].function_id == "locale.japanese"
    assert selected[0].state_score > 0
    assert unselected[0].function_id == "locale.chinese"
    assert "selected:false" in unselected[0].state_evidence
    text_state = catalog.match_candidate(
        label="設定", nearby_text="Disabled", locale="zh-TW", enabled=False
    )[0]
    assert any(value.startswith("text:off:") for value in text_state.state_evidence)

    definition = catalog.function("locale.japanese")
    assert definition is not None
    assert definition.scope == "application"
    assert definition.node_kind == "destination"
    assert definition.stop_policy == "at_destination"
    assert definition.role_hints == ("button",)
    assert set(definition.state_cues) == {
        "enabled:true",
        "selected:true",
        "checkable:true",
        "checked:true",
    }
    assert definition.risk_cues == ("external handoff",)
    assert {(alias.locale, alias.phrase) for alias in definition.aliases} >= {
        ("ja", "設定"),
        ("fr", "Réglages"),
    }
    search_result = catalog.search("Réglages")[0]
    assert search_result["aliases_by_locale"]["fr"] == ["Réglages"]
    danger = catalog.function("danger.confirm")
    assert danger is not None
    assert danger.semantic_concepts == ("confirmation",)
    assert danger.semantic_terminal_concepts == ("confirmation",)
    assert catalog.semantic_concepts_for_text("final confirmation") == frozenset({"confirmation"})
    variant_plan = catalog.plan_goal("最終の設定を開く")
    assert variant_plan.intent == "open_settings"
    assert variant_plan.terminal_function == "locale.chinese"
    assert variant_plan.preferred_functions[-1] == ("locale.chinese", 1.0)
    assert all(function_id != "locale.japanese" for function_id, _ in variant_plan.preferred_functions)
    supplemental_plan = catalog.plan_goal(
        "please show the supplemental cue for system preferences"
    )
    assert supplemental_plan.intent == "open_settings"
    assert supplemental_plan.confidence == 1.0

    connection = sqlite3.connect(database_path)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(navigation_functions)")}
        assert {"scope", "node_kind", "stop_policy"}.issubset(columns)
        goal_rule_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(navigation_intent_goal_rules)")
        }
        assert "terminal_function" in goal_rule_columns
        assert connection.execute("SELECT COUNT(*) FROM navigation_function_state_cues").fetchone()[0] == 9
        assert connection.execute("SELECT COUNT(*) FROM navigation_function_semantic_concepts").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM navigation_function_semantic_terminal_concepts").fetchone()[0] == 1
    finally:
        connection.close()

    legacy_database_path = Path(temporary_directory) / "legacy-schema.sqlite"
    connection = sqlite3.connect(legacy_database_path)
    try:
        connection.execute(
            """
            CREATE TABLE navigation_functions (
              function_id TEXT PRIMARY KEY, domain TEXT NOT NULL, name_ko TEXT NOT NULL,
              name_en TEXT NOT NULL, description TEXT NOT NULL, risk_level TEXT NOT NULL,
              automation_policy TEXT NOT NULL, terminal INTEGER NOT NULL,
              state_changing INTEGER NOT NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()
    migrated = NavigationFunctionCatalog(legacy_database_path, catalog_path)
    assert migrated.function("locale.japanese").scope == "application"


def _assert_validation_and_fail_fast(temporary_directory: str) -> None:
    valid = _metadata_catalog_payload()
    validate_catalog_payload(valid)

    invalid_cases: list[tuple[str, dict[str, object], str]] = []
    duplicate_function = deepcopy(valid)
    duplicate_function["functions"].append(deepcopy(duplicate_function["functions"][0]))
    invalid_cases.append(("duplicate", duplicate_function, "duplicate function_id"))

    empty_alias = deepcopy(valid)
    empty_alias["functions"][0]["aliases"]["ja"].append(" ")
    invalid_cases.append(("empty-alias", empty_alias, "empty phrase"))

    unknown_reference = deepcopy(valid)
    unknown_reference["intents"][0]["route"][0]["function_id"] = "missing.function"
    invalid_cases.append(("unknown-reference", unknown_reference, "unknown function_id"))

    unknown_rule_terminal = deepcopy(valid)
    unknown_rule_terminal["intents"][0]["goal_rules"][0]["terminal_function"] = "missing.function"
    invalid_cases.append(("unknown-rule-terminal", unknown_rule_terminal, "unknown function_id"))

    unknown_supplemental_intent = deepcopy(valid)
    unknown_supplemental_intent["supplemental_goal_rules"][0]["intent_id"] = "missing.intent"
    invalid_cases.append(
        ("unknown-supplemental-intent", unknown_supplemental_intent, "unknown intent_id")
    )

    empty_supplemental_terms = deepcopy(valid)
    empty_supplemental_terms["supplemental_goal_rules"][0]["all_of"] = []
    invalid_cases.append(
        ("empty-supplemental-terms", empty_supplemental_terms, "non-empty cue terms")
    )

    unsafe_state_change = deepcopy(valid)
    unsafe_state_change["functions"][2]["automation_policy"] = "conditional"
    invalid_cases.append(("state-change-policy", unsafe_state_change, "state_changing functions must use never_auto"))

    unsafe_high = deepcopy(valid)
    unsafe_high["functions"][2]["state_changing"] = False
    unsafe_high["functions"][2]["automation_policy"] = "safe_navigation"
    invalid_cases.append(("high-risk-policy", unsafe_high, "high-risk functions must use never_auto"))

    unsafe_stop = deepcopy(valid)
    unsafe_stop["functions"][2]["stop_policy"] = "continue"
    invalid_cases.append(("state-change-stop", unsafe_stop, "stop before activation"))

    unknown_terminal_concept = deepcopy(valid)
    unknown_terminal_concept["functions"][2]["semantic_terminal_concepts"] = ["missing_concept"]
    invalid_cases.append(("terminal-concept", unknown_terminal_concept, "terminal concept is not declared"))

    for _, payload, expected_message in invalid_cases:
        try:
            validate_catalog_payload(payload)
        except CatalogValidationError as error:
            assert expected_message in str(error)
        else:
            raise AssertionError(f"expected CatalogValidationError containing {expected_message!r}")

    catalog_path = Path(temporary_directory) / "fail-fast-catalog.json"
    database_path = Path(temporary_directory) / "fail-fast-catalog.sqlite"
    catalog_path.write_text(json.dumps(valid, ensure_ascii=False), encoding="utf-8")
    baseline = NavigationFunctionCatalog(database_path, catalog_path).stats()
    catalog_path.write_text(json.dumps(unsafe_stop, ensure_ascii=False), encoding="utf-8")
    try:
        NavigationFunctionCatalog(database_path, catalog_path)
    except CatalogValidationError:
        pass
    else:
        raise AssertionError("invalid catalog must fail before replacing SQLite")
    connection = sqlite3.connect(database_path)
    try:
        function_count = connection.execute("SELECT COUNT(*) FROM navigation_functions").fetchone()[0]
    finally:
        connection.close()
    assert function_count == baseline["function_count"]


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(Path(temporary_directory) / "functions.sqlite")
        stats = catalog.stats()
        source_version = json.loads(catalog.catalog_path.read_text(encoding="utf-8"))["catalog_version"]
        assert stats["catalog_version"] == source_version
        assert len(str(stats["catalog_sha256"])) == 64
        assert stats["function_count"] >= 132
        assert stats["alias_count"] >= 1120
        assert stats["context_count"] >= 870
        assert stats["intent_count"] >= 68
        assert stats["goal_rule_count"] >= 55
        assert stats["edge_count"] >= 175
        assert stats["semantic_concept_count"] >= 100
        assert stats["semantic_terminal_concept_count"] >= 2
        assert stats["semantic_lexicon_phrase_count"] >= 250

        plan = catalog.plan_goal("유튜브 프리미엄 구독을 해지하고 싶어")
        assert plan.intent == "subscription_cancellation"
        assert plan.terminal_function == "subscription.cancel.entry"
        assert dict(plan.preferred_functions)["subscription.detail"] > 0.9
        assert catalog.plan_goal("유튜브 프리미엄 구독 관리").terminal_function == "subscription.manage"
        assert catalog.plan_goal("언어를 한국어로 변경").terminal_function == "settings.language"
        assert catalog.plan_goal("주문 취소").terminal_function == "order.cancel.entry"
        assert catalog.plan_goal("시청 기록을 보고 싶어").terminal_function == "content.history"
        assert catalog.plan_goal("맞춤 광고를 끄고 싶어").terminal_function == "privacy.personalization"
        assert catalog.plan_goal("새 계정을 만들고 싶어").terminal_function == "auth.signup.entry"
        content_feed_plan = catalog.plan_goal(
            "돈 내는 상품 말고 내가 챙겨 보는 채널의 새 영상 모음으로 가고 싶어"
        )
        assert content_feed_plan.terminal_function == "content.subscriptions"
        assert content_feed_plan.terminal_function not in content_feed_plan.avoid_functions
        assert catalog.plan_goal(
            "신규 계정 절차 중 처음 사용할 암호를 정하는 단계로 가고 싶어"
        ).terminal_function == "auth.password.create"
        assert catalog.plan_goal(
            "계정이나 대화를 건드리지 말고 선택한 문서만 휴지통으로 옮길래"
        ).terminal_function == "files.trash"
        assert catalog.plan_goal(
            "친구에게 메시지를 보내는 게 아니라 상담원과 실시간으로 이야기하고 싶어"
        ).terminal_function == "support.chat"
        assert catalog.plan_goal(
            "앱 오류를 운영팀에 정식으로 문의할 수 있는 연락 방법을 찾고 있어"
        ).terminal_function == "support.contact"
        assert catalog.plan_goal("이메일로 회원가입").terminal_function == "auth.signup.email"
        assert catalog.plan_goal("휴대폰 번호로 가입").terminal_function == "auth.signup.phone"
        assert catalog.plan_goal("Google로 가입").terminal_function == "auth.signup.social"
        assert catalog.plan_goal("회원가입 약관 확인").terminal_function == "legal.signup_terms"
        assert catalog.plan_goal("가입 필수 동의").terminal_function == "consent.required"
        assert catalog.plan_goal("가입 선택 동의").terminal_function == "consent.optional"
        assert catalog.plan_goal("가입 없이 둘러보기").terminal_function == "auth.guest"
        assert catalog.plan_goal("로그인하고 싶어").terminal_function == "auth.login"
        assert catalog.plan_goal("보험금 청구하고 싶어").terminal_function == "insurance.claim.entry"
        assert catalog.plan_goal("보험금 청구 결과 확인").terminal_function == "insurance.claim.status"
        assert catalog.plan_goal("보험료 납부").terminal_function == "insurance.premium.payment"
        assert catalog.plan_goal("보험료 납입증명서 발급").terminal_function == "insurance.certificate.issue"
        assert catalog.plan_goal("보험 해지환급금 조회").terminal_function == "insurance.surrender_value"
        assert catalog.plan_goal("내 보험 약관을 보고 싶어").terminal_function == "insurance.policy.terms"
        assert catalog.plan_goal("보험계약 해지").terminal_function == "insurance.contract.cancel.entry"
        assert catalog.plan_goal("자동차 고장출동").terminal_function == "insurance.emergency.roadside"
        assert catalog.plan_goal("The건강보험에서 자격득실확인서 발급").terminal_function == "insurance.certificate.issue"
        # Exact reviewed patterns and fully qualified semantic phrases must
        # survive broader sibling rules (payment vs certificate, backup vs
        # restore, app-wide messaging search vs one conversation search).
        assert catalog.plan_goal("건강보험료 납부확인서 발급").terminal_function == "insurance.certificate.issue"
        assert catalog.plan_goal(
            "기기 백업 및 복원 기기 데이터 백업"
        ).terminal_function == "android_backup.device_backup"
        assert catalog.plan_goal(
            "기기 백업 및 복원 기기 데이터 복원"
        ).terminal_function == "android_backup.restore_device"
        assert catalog.plan_goal(
            "메시지 앱 전체가 아니라 이 대화 안에서 메시지를 검색하고 싶어"
        ).terminal_function == "communication.conversation.search"
        # A reviewed pattern wrapped in a short app/request phrase remains
        # authoritative; the embedded Korean word "캐스트" in "팟캐스트"
        # must not redirect the goal to Android media casting.
        assert catalog.plan_goal(
            "유튜브에서 팟캐스트 구독"
        ).terminal_function == "podcast.subscriptions"
        assert catalog.plan_goal("올해 건강검진 대상인지 확인").terminal_function == "health_insurance.screening"

        insurance_claim = catalog.match_candidate(
            label="보험금 청구",
            nearby_text="질병 상해 보상 진행 필요서류",
            role="button",
            position="middle",
        )
        assert insurance_claim[0].function_id == "insurance.claim.entry"

        roadside = catalog.function("insurance.emergency.roadside")
        assert roadside is not None
        assert roadside.automation_policy == "never_auto"
        assert roadside.state_changing is False
        assert roadside.risk_level == "high"

        jeju_signup = catalog.plan_goal("제주항공 회원가입")
        assert jeju_signup.terminal_function == "auth.signup.entry"
        jeju_steps = dict(jeju_signup.preferred_functions)
        assert jeju_steps["navigation.menu"] >= 0.40
        assert jeju_steps["account.entry"] >= 0.54
        assert jeju_steps["auth.entry"] >= 0.86
        assert jeju_steps["auth.login.entry"] >= 0.72

        baemin_club = catalog.match_candidate(
            label="배민클럽 이용 중",
            nearby_text="마이배민 주문내역 고객센터 환경설정",
            role="button",
            position="middle",
        )
        assert baemin_club[0].function_id == "subscription.manage"

        content = catalog.match_candidate(
            label="구독",
            nearby_text="홈 Shorts 보관함 내 페이지",
            position="bottom",
        )
        assert content[0].function_id == "content.subscriptions"

        billing = catalog.match_candidate(
            label="Payments and subscriptions",
            nearby_text="Account Settings Payment method",
            position="middle",
        )
        assert billing[0].function_id == "billing.manage"
        assert next(match for match in billing if match.function_id == "content.subscriptions").score < 0.7

        composed_email = catalog.match_candidate(
            label="계정에 연결된 메일 교체",
            parent_label="로그인 정보",
            locale="ko-KR",
            limit=12,
        )
        assert composed_email[0].function_id == "account.email.change"
        assert set(composed_email[0].matched_concepts) >= {"account", "email", "change"}
        assert composed_email[0].concept_score >= 0.40

        composed_statement = catalog.match_candidate(
            label="월간 청구 내역서",
            parent_label="카드 이용",
            locale="ko-KR",
            limit=12,
        )
        statement = next(match for match in composed_statement if match.function_id == "finance.statements")
        assert set(statement.matched_concepts) >= {"finance", "monthly", "statement"}

        final_action = catalog.function("subscription.cancel.confirm")
        assert final_action is not None
        assert final_action.automation_policy == "never_auto"
        assert final_action.state_changing is True
        assert final_action.risk_level == "high"

        signup_entry = catalog.function("auth.signup.entry")
        assert signup_entry is not None
        assert signup_entry.automation_policy == "safe_navigation"
        assert signup_entry.state_changing is False

        signup_confirm = catalog.function("auth.signup.confirm")
        assert signup_confirm is not None
        assert signup_confirm.automation_policy == "never_auto"
        assert signup_confirm.state_changing is True
        assert signup_confirm.risk_level == "high"

        signup_matches = catalog.match_candidate(
            label="회원가입",
            nearby_text="로그인 또는 새 계정 만들기",
            role="button",
            position="middle",
        )
        assert signup_matches[0].function_id == "auth.signup.entry"

        combined_auth = catalog.match_candidate(
            label="로그인 / 회원가입",
            nearby_text="비회원 예약조회",
            role="button",
            position="middle",
        )
        assert combined_auth[0].function_id == "auth.entry"

        results = catalog.search("회원 탈퇴")
        assert results[0]["function_id"] in {"account.delete.entry", "account.delete.confirm"}
        assert catalog.database_path.exists()

        _assert_unicode_locale_and_metadata_runtime(temporary_directory)
        _assert_validation_and_fail_fast(temporary_directory)

    print("navigation function catalog checks ok")


if __name__ == "__main__":
    main()
