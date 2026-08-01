import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.services import llm as llm_service
from app.services import ocr as ocr_service
from app.services.model_output import parse_model_judgments
from app.services.provider_runtime import RuntimeProviderOptions, resolve_runtime_provider
from app.services.types import ExtractedElement, ExtractedScreen


ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_LEGAL_TERMS = {"illegal", "unlawful", "scam", "fraud", "violation"}


def main() -> None:
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    status = client.get("/v1/status").json()
    assert status["ocr_provider"] == "mock"
    assert status["provider_ready"] is True
    assert {"google", "gpt", "exaone"}.issubset(set(status["supported_ai_providers"]))
    providers = client.get("/v1/providers").json()
    assert {provider["id"] for provider in providers} >= {"server", "google", "gpt", "exaone"}
    google_provider = next(provider for provider in providers if provider["id"] == "google")
    assert google_provider["model"] == "gemini-3-flash-preview"
    assert google_provider["base_url"].endswith("/v1beta")
    google_runtime = resolve_runtime_provider(
        Settings(),
        RuntimeProviderOptions(
            provider_id="google",
            api_key="test-key",
            model="gemini-3-flash-preview",
            base_url="https://generativelanguage.googleapis.com/v1",
        ),
    )
    assert google_runtime.settings.google_base_url == "https://generativelanguage.googleapis.com/v1beta"
    readiness = client.get("/v1/readiness").json()
    assert readiness["status"] == "ready"
    assert all(check["passed"] for check in readiness["checks"])
    assert "catalog_integrity" in {check["id"] for check in readiness["checks"]}
    demo_quality = client.get("/v1/demo-quality").json()
    assert demo_quality["status"] == "pass"
    assert demo_quality["summary"]["readiness_passed"] == demo_quality["summary"]["readiness_total"]
    assert demo_quality["summary"]["scenarios_passed"] == 10
    assert demo_quality["summary"]["flows_passed"] == 4
    assert demo_quality["summary"]["synthetic_passed"] == 15
    goals = client.get("/v1/goals").json()
    assert len(goals) >= 4
    assert all(goal["description"] for goal in goals)
    assert len(client.get("/v1/demo-scenarios").json()) == 10
    demo_flows = client.get("/v1/demo-flows").json()
    assert len(demo_flows) == 4
    assert all(len(flow["scenario_ids"]) >= 2 for flow in demo_flows)
    synthetic_catalog = client.get("/v1/synthetic-screens").json()
    assert synthetic_catalog["screen_count"] == 15
    assert len(synthetic_catalog["screens"]) == 15
    consent_catalog = client.get("/v1/consent-cases").json()
    assert consent_catalog["metadata"]["dataset_schema_version"] == "1.0"
    assert consent_catalog["metadata"]["label_rubric_version"] == "1.0"
    assert consent_catalog["summary"]["case_count"] == 14
    assert consent_catalog["summary"]["source_counts"]["synthetic"] == 13
    assert consent_catalog["summary"]["source_counts"]["field_candidate"] == 1
    assert consent_catalog["summary"]["risk_counts"]["high"] == 7
    assert consent_catalog["summary"]["risk_counts"]["medium"] == 2
    assert consent_catalog["summary"]["tag_counts"]["false_positive_guard"] == 3
    assert "prompt_injection" in consent_catalog["summary"]["tag_counts"]
    assert all(case["source"]["raw_artifact_in_repo"] is False for case in consent_catalog["cases"])
    assert all(case["source"]["contains_raw_screenshot"] is False for case in consent_catalog["cases"])
    field_case = next(case for case in consent_catalog["cases"] if case["source_type"] == "field_candidate")
    assert field_case["source"]["redaction_status"] == "redacted"
    assert field_case["source"]["review_status"] == "approved"
    assert field_case["source"]["public_fixture_allowed"] is True
    consent_quality = client.get("/v1/consent-cases/quality").json()
    assert consent_quality["status"] == "pass"
    assert consent_quality["evaluation_scope"] == "deterministic_rule_calibration"
    assert "ocr_extraction" in consent_quality["not_evaluated"]
    assert any("does not measure OCR" in item for item in consent_quality["limitations"])
    assert consent_quality["metadata"]["dataset_version"] == consent_catalog["metadata"]["dataset_version"]
    assert consent_quality["calibration_summary"]["total"] == 14
    assert consent_quality["calibration_summary"]["passed"] == 14
    assert consent_quality["calibration_summary"]["failed"] == 0
    assert consent_quality["calibration_summary"]["passed_by_risk"]["medium"] == 2
    assert consent_quality["coverage"]["status"] == "pass"
    assert not consent_quality["coverage"]["warnings"]
    coverage_targets = {target["id"]: target for target in consent_quality["coverage"]["targets"]}
    assert coverage_targets["risk_medium"]["actual"] == 2
    assert coverage_targets["false_positive_guard"]["actual"] == 3
    assert len(consent_quality["calibrations"]) == 14
    assert all(item["passed"] for item in consent_quality["calibrations"])
    terms_catalog = client.get("/v1/terms-corpus").json()
    assert terms_catalog["summary"]["document_count"] == 3
    assert terms_catalog["summary"]["section_count"] == 9
    assert terms_catalog["summary"]["document_type_counts"]["subscription_terms"] == 1
    terms_search = client.get("/v1/terms-corpus/search", params={"q": "자동 갱신 해지 결제", "top_k": 3}).json()
    assert terms_search["total"] >= 1
    assert terms_search["results"][0]["chunk"]["document_id"] == "seed_streaming_subscription_terms"
    terms_quality = client.get("/v1/terms-corpus/quality").json()
    assert terms_quality["status"] == "pass"
    assert not terms_quality["warnings"]
    collection_registry = client.get("/v1/collection-registry").json()
    assert collection_registry["summary"]["service_count"] == 3
    assert collection_registry["summary"]["document_source_count"] == 6
    assert collection_registry["summary"]["review_task_count"] == 2
    assert collection_registry["summary"]["flow_count"] == 2
    assert collection_registry["summary"]["flow_step_count"] == 5
    assert collection_registry["summary"]["document_type_counts"]["terms"] == 2
    assert collection_registry["summary"]["document_type_counts"]["privacy"] == 2
    collection_quality = client.get("/v1/collection-registry/quality").json()
    assert collection_quality["status"] == "pass"
    assert not collection_quality["warnings"]
    fixture_dir = ROOT / "fixtures" / "synthetic-screens"
    cataloged_fixture_files = {screen["filename"] for screen in synthetic_catalog["screens"]}
    actual_fixture_files = {path.name for path in fixture_dir.glob("*.png")}
    assert actual_fixture_files == cataloged_fixture_files
    for screen in synthetic_catalog["screens"]:
        assert (fixture_dir / screen["filename"]).exists()
        response = client.post(
            "/v1/analyze",
            data={"goal_id": screen["recommended_goal_id"]},
            files={"screenshot": (screen["filename"], b"fake", "image/png")},
        )
        assert response.status_code == 200
        assert response.json()["analysis_id"].startswith("an_")
        assert response.json()["overall_risk"] == screen["risk_fixture"], screen["filename"]

    prompt_response = client.post(
        "/v1/prompt/demo",
        json={"goal_id": "buy_without_addons", "scenario_id": "checkout_addons"},
    )
    assert prompt_response.status_code == 200
    assert "output_schema" in prompt_response.json()["user_prompt"]

    custom_goal_response = client.post(
        "/v1/analyze/demo",
        json={"goal_text": "추가 결제 없이 가입하고 싶어요", "scenario_id": "checkout_addons"},
    )
    assert custom_goal_response.status_code == 200
    assert custom_goal_response.json()["goal_id"] == "custom_goal"
    assert custom_goal_response.json()["goal_label"] == "추가 결제 없이 가입하고 싶어요"
    assert custom_goal_response.json()["overall_risk"] == "high"

    inferred_goal_response = client.post(
        "/v1/analyze/demo",
        json={"infer_goal": True, "scenario_id": "marketing_consent"},
    )
    assert inferred_goal_response.status_code == 200
    assert inferred_goal_response.json()["goal_id"] == "reject_marketing"
    assert inferred_goal_response.json()["overall_risk"] == "high"

    missing_runtime_provider_response = client.post(
        "/v1/analyze/demo",
        json={"provider_id": "google", "scenario_id": "checkout_addons", "infer_goal": True},
    )
    assert missing_runtime_provider_response.status_code == 503

    cases = [
        ("cancel_subscription", "subscription.png", "primary_retention_button", "subscription_cancel"),
        ("cancel_subscription", "subscription-cancel-confirmation.png", "complete_cancellation_button", "subscription_confirmation"),
        ("cancel_trial", "trial.png", "cancel_trial_button", "trial_renewal"),
        ("cancel_trial", "trial-cancel-success.png", "confirm_button", "trial_success"),
        ("buy_without_addons", "checkout.png", "shipping_insurance", "checkout_addons"),
        ("buy_without_addons", "checkout-no-preselected-addon.png", "pay_now", "checkout_clean"),
        ("reject_marketing", "consent.png", "agree_all", "marketing_consent"),
        ("reject_marketing", "consent-required-only.png", "continue_button", "required_terms_only"),
        ("delete_account", "delete.png", "delete_account_button", "account_deletion"),
        ("delete_account", "account-delete-confirmation.png", "complete_account_deletion_button", "account_deletion_confirmation"),
    ]

    for goal_id, filename, expected_element_id, scenario_id in cases:
        response = client.post(
            "/v1/analyze",
            data={"goal_id": goal_id},
            files={"screenshot": (filename, b"fake", "image/png")},
        )
        assert response.status_code == 200
        assert response.json()["analysis_id"].startswith("an_")
        assert response.json()["analysis_mode"] == "upload"
        assert 0 <= response.json()["alignment_score"] <= 100
        assert all("signals" in element for element in response.json()["elements"])
        element_ids = {element["id"] for element in response.json()["elements"]}
        assert expected_element_id in element_ids

        demo_response = client.post(
            "/v1/analyze/demo",
            json={"goal_id": goal_id, "scenario_id": scenario_id},
        )
        assert demo_response.status_code == 200
        assert_no_forbidden_legal_terms(demo_response.json())
        assert demo_response.json()["analysis_id"].startswith("an_")
        assert demo_response.json()["analysis_mode"] == "demo"
        demo_element_ids = {element["id"] for element in demo_response.json()["elements"]}
        assert expected_element_id in demo_element_ids
        if scenario_id == "trial_renewal":
            evidence = " ".join(demo_response.json()["proof_card"]["key_evidence"])
            assert "12,900" in evidence
        if scenario_id in {"subscription_confirmation", "trial_success", "checkout_clean", "required_terms_only", "account_deletion_confirmation"}:
            assert demo_response.json()["overall_risk"] == "low"

    neutral_upload_response = client.post(
        "/v1/analyze",
        data={"goal_id": "protect_user_intent"},
        files={"screenshot": ("community-comment.png", b"fake", "image/png")},
    )
    assert neutral_upload_response.status_code == 200
    assert neutral_upload_response.json()["overall_risk"] == "low"
    assert neutral_upload_response.json()["screen_title"] == "일반 콘텐츠"

    invalid_goal_response = client.post(
        "/v1/analyze/demo",
        json={"goal_id": "become_a_wizard", "scenario_id": "subscription_cancel"},
    )
    assert invalid_goal_response.status_code == 400

    empty_upload_response = client.post(
        "/v1/analyze",
        data={"goal_id": "cancel_subscription"},
        files={"screenshot": ("empty.png", b"", "image/png")},
    )
    assert empty_upload_response.status_code == 400

    unsupported_type_response = client.post(
        "/v1/analyze",
        data={"goal_id": "cancel_subscription"},
        files={"screenshot": ("note.txt", b"fake", "text/plain")},
    )
    assert unsupported_type_response.status_code == 400

    too_large_upload_response = client.post(
        "/v1/analyze",
        data={"goal_id": "cancel_subscription"},
        files={"screenshot": ("large.png", b"x" * (get_settings().max_upload_bytes + 1), "image/png")},
    )
    assert too_large_upload_response.status_code == 400

    flow_response = client.post(
        "/v1/analyze/flow",
        json={"goal_id": "buy_without_addons", "scenario_ids": ["checkout_addons", "checkout_clean"]},
    )
    assert flow_response.status_code == 200
    assert flow_response.json()["flow_id"].startswith("fl_")
    assert len(flow_response.json()["screens"]) == 2
    assert flow_response.json()["screen_count"] == 2
    assert flow_response.json()["highest_risk_screen_number"] == 1
    assert flow_response.json()["overall_risk"] == "high"
    assert flow_response.json()["risk_counts"]["high"] >= 1
    assert flow_response.json()["risk_path"] == ["high", "low"]

    one_scenario_flow_response = client.post(
        "/v1/analyze/flow",
        json={"goal_id": "buy_without_addons", "scenario_ids": ["checkout_addons"]},
    )
    assert one_scenario_flow_response.status_code == 422

    upload_flow_response = client.post(
        "/v1/analyze/flow/upload",
        data={"goal_id": "buy_without_addons"},
        files=[
            ("screenshots", ("checkout-preselected-addon.png", b"fake", "image/png")),
            ("screenshots", ("checkout-no-preselected-addon.png", b"fake", "image/png")),
        ],
    )
    assert upload_flow_response.status_code == 200
    assert upload_flow_response.json()["flow_id"].startswith("fl_")
    assert len(upload_flow_response.json()["screens"]) == 2
    assert upload_flow_response.json()["screen_count"] == 2
    assert upload_flow_response.json()["highest_risk_screen_number"] == 1
    assert upload_flow_response.json()["overall_risk"] == "high"
    assert upload_flow_response.json()["risk_path"] == ["high", "low"]

    one_screen_flow_response = client.post(
        "/v1/analyze/flow/upload",
        data={"goal_id": "buy_without_addons"},
        files=[("screenshots", ("checkout-preselected-addon.png", b"fake", "image/png"))],
    )
    assert one_screen_flow_response.status_code == 400

    old_ocr_provider = os.environ.get("OCR_PROVIDER")
    try:
        for provider in ("naver_clova_ocr", "gemini_vision", "openai_vision", "exaone_vision"):
            os.environ["OCR_PROVIDER"] = provider
            get_settings.cache_clear()
            provider_status = client.get("/v1/status").json()
            assert provider_status["provider_ready"] is False
            provider_readiness = client.get("/v1/readiness").json()
            assert provider_readiness["status"] == "needs_setup"
            provider_quality = client.get("/v1/demo-quality").json()
            assert provider_quality["status"] == "fail"
            recognized_provider_response = client.post(
                "/v1/analyze",
                data={"goal_id": "cancel_subscription"},
                files={"screenshot": ("subscription.png", b"fake", "image/png")},
            )
            assert recognized_provider_response.status_code == 503

        os.environ["OCR_PROVIDER"] = "unknown_provider"
        get_settings.cache_clear()
        response = client.post(
            "/v1/analyze",
            data={"goal_id": "cancel_subscription"},
            files={"screenshot": ("subscription.png", b"fake", "image/png")},
        )
        assert response.status_code == 503
    finally:
        if old_ocr_provider is None:
            os.environ.pop("OCR_PROVIDER", None)
        else:
            os.environ["OCR_PROVIDER"] = old_ocr_provider
        get_settings.cache_clear()

    old_llm_provider = os.environ.get("LLM_PROVIDER")
    try:
        for provider in ("hyperclova", "upstage", "gemini", "openai", "exaone"):
            os.environ["LLM_PROVIDER"] = provider
            get_settings.cache_clear()
            provider_status = client.get("/v1/status").json()
            assert provider_status["provider_ready"] is False
            provider_readiness = client.get("/v1/readiness").json()
            assert provider_readiness["status"] == "needs_setup"
            provider_quality = client.get("/v1/demo-quality").json()
            assert provider_quality["status"] == "fail"
            response = client.post(
                "/v1/analyze/demo",
                json={"goal_id": "cancel_subscription", "scenario_id": "subscription_cancel"},
            )
            assert response.status_code == 503
    finally:
        if old_llm_provider is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = old_llm_provider
        get_settings.cache_clear()

    parsed_judgments = parse_model_judgments(
        raw_json='{"judgments":[{"element_id":"known","direction":"supports_goal","reason":"Looks aligned."}]}',
        screen=ExtractedScreen(
            title="Parser fixture",
            text="Known and missing",
            elements=[
                ExtractedElement(id="known", label="Known", element_type="button"),
                ExtractedElement(id="missing", label="Missing", element_type="button"),
            ],
        ),
    )
    assert [judgment.direction for judgment in parsed_judgments] == ["supports_goal", "needs_check"]

    assert_gemini_rest_payloads_match_google_docs()
    assert_gemini_plain_text_fallbacks_do_not_fail_uploads()
    assert_gemini_partial_terms_payload_becomes_terms_element()
    assert_gemini_broken_terms_json_retries_before_fallback()
    assert_gemini_broken_ui_json_retries_without_terms_keywords()
    assert_gemini_retry_failure_keeps_best_broken_ui_content()
    assert_choice_row_extraction_handles_terms_patterns()
    assert_exaone_payloads_disable_thinking()

    print("api smoke ok")


def assert_no_forbidden_legal_terms(payload: object) -> None:
    text = str(payload).lower()
    assert not any(term in text for term in FORBIDDEN_LEGAL_TERMS)


def assert_exaone_payloads_disable_thinking() -> None:
    captured_payloads = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_post(*_args, **kwargs):
        captured_payloads.append(kwargs["json"])
        if len(captured_payloads) == 1:
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"title":"계정","text":"멤버십 및 구매",'
                                    '"elements":[{"id":"membership","label":"멤버십 및 구매",'
                                    '"element_type":"button"}]}'
                                )
                            }
                        }
                    ]
                }
            )
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"judgments":[{"element_id":"membership",'
                                '"direction":"supports_goal","reason":"해지 메뉴로 이어집니다."}]}'
                            )
                        }
                    }
                ]
            }
        )

    old_ocr_post = ocr_service.httpx.post
    old_llm_post = llm_service.httpx.post
    try:
        ocr_service.httpx.post = fake_post
        llm_service.httpx.post = fake_post
        settings = Settings(exaone_api_key="test-key", exaone_model="EXAONE-4.5-33B")
        screen = ocr_service.ExaoneVisionOcrProvider(settings).extract(
            image_bytes=b"fake-image",
            filename="account.png",
            goal_id="cancel_subscription",
        )
        llm_service.ExaoneLlmProvider(settings).judge_elements(
            goal_id="cancel_subscription",
            screen=screen,
        )
    finally:
        ocr_service.httpx.post = old_ocr_post
        llm_service.httpx.post = old_llm_post

    assert len(captured_payloads) == 2
    assert captured_payloads[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured_payloads[1]["chat_template_kwargs"] == {"enable_thinking": False}


def assert_gemini_rest_payloads_match_google_docs() -> None:
    captured_payloads = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_post(*_args, **kwargs):
        captured_payloads.append(kwargs["json"])
        if len(captured_payloads) == 1:
            return FakeResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": (
                                            '```json\n{"title":"Comment","text":"Passive content",'
                                            '"elements":[{"id":"comment","label":"Comment","element_type":"text"}]}\n```'
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                }
            )
        return FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '판정 결과입니다.\n{"judgments":[{"element_id":"comment","direction":"needs_check",'
                                        '"reason":"Check context."}]}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        )

    old_ocr_post = ocr_service.httpx.post
    old_llm_post = llm_service.httpx.post
    try:
        ocr_service.httpx.post = fake_post
        llm_service.httpx.post = fake_post
        settings = Settings(google_api_key="test-key", gemini_model="gemini-3-flash-preview")
        screen = ocr_service.GeminiVisionOcrProvider(settings).extract(
            image_bytes=b"fake-image",
            filename="community.png",
            goal_id="protect_user_intent",
        )
        llm_service.GeminiLlmProvider(settings).judge_elements(
            goal_id="protect_user_intent",
            screen=screen,
        )
    finally:
        ocr_service.httpx.post = old_ocr_post
        llm_service.httpx.post = old_llm_post

    ocr_payload = captured_payloads[0]
    image_part = ocr_payload["contents"][0]["parts"][1]["inline_data"]
    assert image_part["mime_type"] == "image/png"
    assert ocr_payload["generationConfig"]["response_mime_type"] == "application/json"
    assert ocr_payload["generationConfig"]["response_schema"]["type"] == "OBJECT"

    llm_payload = captured_payloads[1]
    assert "system_instruction" in llm_payload
    assert llm_payload["generationConfig"]["response_mime_type"] == "application/json"
    assert llm_payload["generationConfig"]["response_schema"]["properties"]["judgments"]["type"] == "ARRAY"


def assert_gemini_plain_text_fallbacks_do_not_fail_uploads() -> None:
    captured_payloads = []

    class FakeResponse:
        def __init__(self, text: str) -> None:
            self._text = text

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"candidates": [{"content": {"parts": [{"text": self._text}]}}]}

    def fake_post(*_args, **kwargs):
        captured_payloads.append(kwargs["json"])
        if len(captured_payloads) == 1:
            return FakeResponse("화면에는 커뮤니티 댓글만 보이고 가입, 결제, 약관 동의 버튼은 보이지 않습니다.")
        return FakeResponse("판정: 지금은 JSON이 아닙니다.")

    old_ocr_post = ocr_service.httpx.post
    old_llm_post = llm_service.httpx.post
    try:
        ocr_service.httpx.post = fake_post
        llm_service.httpx.post = fake_post
        settings = Settings(google_api_key="test-key", gemini_model="gemini-3-flash-preview")
        screen = ocr_service.GeminiVisionOcrProvider(settings).extract(
            image_bytes=b"fake-image",
            filename="community.png",
            goal_id="protect_user_intent",
        )
        judgments = llm_service.GeminiLlmProvider(settings).judge_elements(
            goal_id="protect_user_intent",
            screen=screen,
        )
    finally:
        ocr_service.httpx.post = old_ocr_post
        llm_service.httpx.post = old_llm_post

    assert screen.title == "화면 전체 분석"
    assert screen.elements[0].id == "screen_text"
    assert judgments[0].direction == "needs_check"


def assert_gemini_partial_terms_payload_becomes_terms_element() -> None:
    call_count = {"value": 0}

    class FakeResponse:
        def __init__(self, text: str) -> None:
            self._text = text

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": self._text}
                            ]
                        }
                    }
                ]
            }

    def fake_post(*_args, **_kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return FakeResponse('{"title":"PASS 인증서","text":"약관동의","elements":[]}')
        return FakeResponse(
            '{"title":"PASS 인증서","text":"약관동의","elements":['
            '{"id":"agree_all","label":"약관에 전체동의 (선택사항 포함)","element_type":"checkbox","prominence":3,"default_selected":true,"optional":true},'
            '{"id":"required_1","label":"(필수) PASS서비스이용약관","element_type":"checkbox","default_selected":true,"optional":false},'
            '{"id":"optional_1","label":"(선택) 이벤트 참여를 위한 개인정보 처리위탁 동의","element_type":"checkbox","default_selected":true,"optional":true},'
            '{"id":"optional_2","label":"(선택) 광고성정보수신동의","element_type":"checkbox","default_selected":true,"optional":true},'
            '{"id":"continue","label":"동의하고 계속하기","element_type":"button","prominence":3}'
            ']}'
        )

    old_ocr_post = ocr_service.httpx.post
    try:
        ocr_service.httpx.post = fake_post
        settings = Settings(google_api_key="test-key", gemini_model="gemini-3-flash-preview")
        screen = ocr_service.GeminiVisionOcrProvider(settings).extract(
            image_bytes=b"fake-image",
            filename="pass.png",
            goal_id="protect_user_intent",
        )
    finally:
        ocr_service.httpx.post = old_ocr_post

    assert screen.title == "PASS 인증서"
    assert screen.text == "약관동의"
    assert call_count["value"] == 2
    assert screen.elements[0].id == "agree_all"
    assert screen.elements[0].optional is True
    assert screen.elements[0].default_selected is True
    assert any(element.label.startswith("(선택)") for element in screen.elements)


def assert_gemini_broken_terms_json_retries_before_fallback() -> None:
    call_count = {"value": 0}

    class FakeResponse:
        def __init__(self, text: str) -> None:
            self._text = text

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"candidates": [{"content": {"parts": [{"text": self._text}]}}]}

    def fake_post(*_args, **_kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return FakeResponse('{"title":"PASS 인증서","text":"약관동의","elements":[{"id":"broken"')
        return FakeResponse(
            '{"title":"PASS 인증서","text":"약관동의","elements":['
            '{"id":"optional_1","label":"(선택) 광고성정보수신동의","element_type":"checkbox","default_selected":true,"optional":true}'
            ']}'
        )

    old_ocr_post = ocr_service.httpx.post
    try:
        ocr_service.httpx.post = fake_post
        settings = Settings(google_api_key="test-key", gemini_model="gemini-3-flash-preview")
        screen = ocr_service.GeminiVisionOcrProvider(settings).extract(
            image_bytes=b"fake-image",
            filename="pass.png",
            goal_id="protect_user_intent",
        )
    finally:
        ocr_service.httpx.post = old_ocr_post

    assert call_count["value"] == 2
    assert screen.elements[0].label == "(선택) 광고성정보수신동의"
    assert screen.elements[0].default_selected is True
    assert screen.elements[0].optional is True


def assert_gemini_broken_ui_json_retries_without_terms_keywords() -> None:
    call_count = {"value": 0}

    class FakeResponse:
        def __init__(self, text: str) -> None:
            self._text = text

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"candidates": [{"content": {"parts": [{"text": self._text}]}}]}

    def fake_post(*_args, **_kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return FakeResponse('{"title":"Settings","text":"","elements":[{"label":"Enable paid add-on","element_type":"toggle"')
        return FakeResponse(
            '{"title":"Settings","text":"Review choices","elements":['
            '{"id":"addon","label":"Enable paid add-on","element_type":"toggle","default_selected":false,"optional":true}'
            ']}'
        )

    old_ocr_post = ocr_service.httpx.post
    try:
        ocr_service.httpx.post = fake_post
        settings = Settings(google_api_key="test-key", gemini_model="gemini-3-flash-preview")
        screen = ocr_service.GeminiVisionOcrProvider(settings).extract(
            image_bytes=b"fake-image",
            filename="settings.png",
            goal_id="protect_user_intent",
        )
    finally:
        ocr_service.httpx.post = old_ocr_post

    assert call_count["value"] == 2
    assert screen.elements[0].label == "Enable paid add-on"
    assert screen.elements[0].default_selected is False
    assert screen.elements[0].optional is True


def assert_gemini_retry_failure_keeps_best_broken_ui_content() -> None:
    call_count = {"value": 0}

    class FakeResponse:
        def __init__(self, text: str) -> None:
            self._text = text

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"candidates": [{"content": {"parts": [{"text": self._text}]}}]}

    def fake_post(*_args, **_kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return FakeResponse(
                '{"title":"PASS","elements":['
                '{"label":"(필수) PASS서비스이용약관","element_type":"checkbox","default_selected":false,"optional":false},'
                '{"label":"(선택) 광고성정보수신동의","element_type":"checkbox","default_selected":true,"optional":true}'
            )
        return FakeResponse("still not json")

    old_ocr_post = ocr_service.httpx.post
    try:
        ocr_service.httpx.post = fake_post
        settings = Settings(google_api_key="test-key", gemini_model="gemini-3-flash-preview")
        screen = ocr_service.GeminiVisionOcrProvider(settings).extract(
            image_bytes=b"fake-image",
            filename="pass.png",
            goal_id="protect_user_intent",
        )
    finally:
        ocr_service.httpx.post = old_ocr_post

    assert call_count["value"] == 2
    assert [element.label for element in screen.elements] == ["(필수) PASS서비스이용약관", "(선택) 광고성정보수신동의"]
    assert screen.elements[0].default_selected is False
    assert screen.elements[0].optional is False
    assert screen.elements[1].default_selected is True
    assert screen.elements[1].optional is True


def assert_choice_row_extraction_handles_terms_patterns() -> None:
    source = "\n".join(
        [
            "전체동의 - 필수 약관과 프로모션 정보 수신에 모두 동의합니다",
            "[필수] 이용약관 동의",
            "개인정보 수집 및 이용동의[선택]",
            "[선택] 영리목적 광고성 정보 수신 및 마케팅 목적 개인정보 이용 동의",
            "전체 동의는 선택 정보에 대한 동의도 포함됩니다",
            "전체 동의는 필수 및 선택사항에 대한 동의도 포함됩니다",
            "[필수]개인정보 수집동의",
            "[선택]프로모션 정보 수신 동의",
            "정보/이벤트 SMS 수신에 동의합니다",
            "동의하고 계속하기",
        ]
    )

    rows = ocr_service._extract_choice_rows(source)
    labels = [row["label"] for row in rows]

    assert "전체동의 - 필수 약관과 프로모션 정보 수신에 모두 동의합니다" in labels
    assert "필수 이용약관 동의" in labels
    assert "개인정보 수집 및 이용동의 선택" in labels
    assert "선택 영리목적 광고성 정보 수신 및 마케팅 목적 개인정보 이용 동의" in labels
    assert "선택 프로모션 정보 수신 동의" in labels
    assert "정보/이벤트 SMS 수신에 동의합니다" in labels
    assert "동의하고 계속하기" in labels
    assert next(row for row in rows if "프로모션" in row["label"])["optional"] is True
    assert next(row for row in rows if row["label"].startswith("필수"))["optional"] is False
    assert next(row for row in rows if row["label"].startswith("선택"))["optional"] is True
    assert next(row for row in rows if row["label"] == "동의하고 계속하기")["element_type"] == "button"


if __name__ == "__main__":
    main()
