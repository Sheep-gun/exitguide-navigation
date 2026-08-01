import base64
import json
import logging
import re
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import Settings, get_settings
from app.services.errors import ProviderUnavailableError
from app.services.provider_errors import compact_json, compact_text, load_model_json, response_error_detail
from app.services.screen_fixtures import SCREEN_FIXTURES
from app.services.types import ExtractedElement, ExtractedScreen

logger = logging.getLogger("exitguide.api")


class ExtractedElementPayload(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    element_type: str = Field(min_length=1, max_length=32)
    prominence: int = Field(default=1, ge=1, le=3)
    default_selected: bool = False
    monetary_impact: bool = False
    optional: bool = False


class ExtractedScreenPayload(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(default="", max_length=1200)
    elements: list[ExtractedElementPayload] = Field(default_factory=list, max_length=12)


class OcrProvider:
    def extract(self, image_bytes: bytes, filename: str | None, goal_id: str) -> ExtractedScreen:
        raise NotImplementedError


class MockOcrProvider(OcrProvider):
    def extract(self, image_bytes: bytes, filename: str | None, goal_id: str) -> ExtractedScreen:
        scenario = _infer_scenario(filename=filename, goal_id=goal_id)
        return SCREEN_FIXTURES[scenario]()


class ExaoneVisionOcrProvider(OcrProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def extract(self, image_bytes: bytes, filename: str | None, goal_id: str) -> ExtractedScreen:
        if not self.settings.exaone_api_key or not self.settings.exaone_model:
            raise ProviderUnavailableError("EXAONE vision OCR에는 EXAONE_API_KEY와 EXAONE_MODEL이 필요합니다.")

        content_type = _content_type_for(filename)
        image_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        payload = {
            "model": self.settings.exaone_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You extract concise mobile UI structure for ExitGuide AI. "
                        "Return only JSON. If the image is general content such as a community comment, "
                        "feed, article, or photo without signup, payment, cancellation, consent, or account-deletion "
                        "actions, mark it as passive content with informational elements only."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "이미지에서 사용자가 누를 수 있거나 확인해야 하는 UI 요소만 JSON으로 추출하세요. "
                                "스키마: {\"title\": string, \"text\": string, \"elements\": [{\"id\": string, "
                                "\"label\": string, \"element_type\": string, \"prominence\": 1|2|3, "
                                "\"default_selected\": boolean, \"monetary_impact\": boolean, \"optional\": boolean}]}. "
                                "가입/결제/해지/동의/탈퇴 행동이 없는 커뮤니티 댓글 사진이면 위험 요소를 만들지 말고 "
                                "일반 콘텐츠로 요약하세요."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            "temperature": 0.2,
            "max_tokens": 900,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        raw_content = ""
        try:
            response = httpx.post(
                f"{self.settings.exaone_base_url.rstrip('/')}/chat/completions",
                headers=_exaone_headers(self.settings),
                json=payload,
                timeout=self.settings.exaone_timeout_seconds,
            )
            response.raise_for_status()
            raw_content = response.json()["choices"][0]["message"]["content"]
            parsed = ExtractedScreenPayload.model_validate(json.loads(_strip_json_fence(raw_content)))
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"EXAONE vision OCR HTTP {exc.response.status_code}: {response_error_detail(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"EXAONE vision OCR 연결 오류: {compact_text(str(exc))}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError(f"EXAONE vision OCR 응답에 본문이 없습니다: {compact_text(str(exc))}") from exc
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ProviderUnavailableError(
                f"EXAONE vision OCR JSON을 읽지 못했습니다: {compact_text(raw_content)}"
            ) from exc

        elements = [
            ExtractedElement(
                id=element.id,
                label=element.label,
                element_type=element.element_type,
                prominence=element.prominence,
                default_selected=element.default_selected,
                monetary_impact=element.monetary_impact,
                optional=element.optional,
            )
            for element in parsed.elements
        ]
        if not elements:
            elements = SCREEN_FIXTURES["neutral_context"]().elements

        return ExtractedScreen(title=parsed.title, text=parsed.text, elements=elements)


class GeminiVisionOcrProvider(OcrProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def extract(self, image_bytes: bytes, filename: str | None, goal_id: str) -> ExtractedScreen:
        if not self.settings.google_api_key or not self.settings.gemini_model:
            raise ProviderUnavailableError("Gemini vision OCR에는 GOOGLE_API_KEY와 GEMINI_MODEL이 필요합니다.")

        payload = _gemini_ocr_payload(image_bytes=image_bytes, filename=filename, prompt=_ocr_prompt())

        raw_content = ""
        try:
            raw_content = _post_gemini_generate_content(self.settings, payload)
            parsed = _parse_extracted_screen_payload(raw_content)
            if _needs_detailed_ui_retry(parsed):
                detailed_payload = _gemini_ocr_payload(
                    image_bytes=image_bytes,
                    filename=filename,
                    prompt=_detailed_ui_ocr_prompt(),
                )
                raw_content = _post_gemini_generate_content(self.settings, detailed_payload)
                parsed = _parse_extracted_screen_payload(raw_content)
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"Gemini vision OCR HTTP {exc.response.status_code}: {response_error_detail(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Gemini vision OCR 연결 오류: {compact_text(str(exc))}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError(f"Gemini vision OCR 응답에 본문이 없습니다: {compact_text(str(exc))}") from exc
        except (json.JSONDecodeError, ValidationError) as exc:
            if _should_retry_detailed_ui_after_parse_failure(raw_content):
                first_raw_content = raw_content
                try:
                    detailed_payload = _gemini_ocr_payload(
                        image_bytes=image_bytes,
                        filename=filename,
                        prompt=_detailed_ui_ocr_prompt(),
                    )
                    raw_content = _post_gemini_generate_content(self.settings, detailed_payload)
                    parsed = _parse_extracted_screen_payload(raw_content)
                    return _to_extracted_screen(parsed)
                except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError):
                    logger.warning("Gemini detailed OCR retry failed: %s", compact_text(raw_content))
                    raw_content = _preferred_fallback_content(first_raw_content, raw_content)
            return _fallback_screen_from_model_text(raw_content)

        return _to_extracted_screen(parsed)


class OpenAiVisionOcrProvider(OcrProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def extract(self, image_bytes: bytes, filename: str | None, goal_id: str) -> ExtractedScreen:
        if not self.settings.openai_api_key or not self.settings.openai_model:
            raise ProviderUnavailableError("OpenAI vision OCR에는 OPENAI_API_KEY와 OPENAI_MODEL이 필요합니다.")

        content_type = _content_type_for(filename)
        image_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        payload = {
            "model": self.settings.openai_model,
            "instructions": (
                "You extract concise mobile UI structure for ExitGuide AI. "
                "Return only JSON matching the requested schema."
            ),
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": _ocr_prompt()},
                        {"type": "input_image", "image_url": image_url},
                    ],
                }
            ],
            "temperature": 0.2,
            "max_output_tokens": 900,
            "store": False,
        }

        raw_content = ""
        try:
            response = httpx.post(
                f"{self.settings.openai_base_url.rstrip('/')}/responses",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self.settings.ai_provider_timeout_seconds,
            )
            response.raise_for_status()
            raw_content = _openai_response_text(response.json())
            parsed = ExtractedScreenPayload.model_validate(json.loads(_strip_json_fence(raw_content)))
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"OpenAI vision OCR HTTP {exc.response.status_code}: {response_error_detail(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"OpenAI vision OCR 연결 오류: {compact_text(str(exc))}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError(f"OpenAI vision OCR 응답에 본문이 없습니다: {compact_text(str(exc))}") from exc
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ProviderUnavailableError(
                f"OpenAI vision OCR JSON을 읽지 못했습니다: {compact_text(raw_content)}"
            ) from exc

        return _to_extracted_screen(parsed)


class NaverClovaOcrProvider(OcrProvider):
    def extract(self, image_bytes: bytes, filename: str | None, goal_id: str) -> ExtractedScreen:
        raise ProviderUnavailableError("NAVER CLOVA OCR provider는 인식되지만 HTTP 클라이언트 연결은 아직 대기 중입니다.")


def get_ocr_provider(name: str, settings: Settings | None = None) -> OcrProvider:
    settings = settings or get_settings()
    if name == "mock":
        return MockOcrProvider()
    if name == "gemini_vision":
        return GeminiVisionOcrProvider(settings)
    if name == "openai_vision":
        return OpenAiVisionOcrProvider(settings)
    if name == "exaone_vision":
        return ExaoneVisionOcrProvider(settings)
    if name == "naver_clova_ocr":
        return NaverClovaOcrProvider()
    raise ProviderUnavailableError(f"지원되지 않는 OCR provider입니다: {name}")


def _infer_scenario(filename: str | None, goal_id: str) -> str:
    source = (filename or "").lower()
    if "subscription-cancel-confirmation" in source:
        return "cancel_confirmation"
    if "subscription-pause-offer" in source:
        return "cancel_pause_offer"
    if "trial-cancel-success" in source:
        return "trial_success"
    if "trial-discount-retention" in source:
        return "trial_discount_retention"
    if "account-delete-confirmation" in source:
        return "account_delete_confirmation"
    if "checkout-donation-addon" in source:
        return "checkout_donation"
    if "checkout-warranty-addon" in source:
        return "checkout_warranty"
    if "marketing-separated-optional" in source:
        return "marketing_separated"
    if "trial" in source or "renewal" in source or goal_id == "cancel_trial":
        return "trial"
    if "clean_checkout" in source or "no-preselected" in source:
        return "checkout_clean"
    if "checkout" in source or "addon" in source or "buy_without" in source:
        return "checkout"
    if "required_terms_only" in source or "required-only" in source:
        return "required_terms"
    if "consent" in source or "marketing" in source or "reject_marketing" in source:
        return "consent"
    if "delete" in source or "withdrawal" in source:
        return "account_delete"
    if "subscription" in source or "cancel" in source:
        return "cancel"
    if any(token in source for token in ("community", "comment", "feed", "post", "reply", "thread")):
        return "neutral_context"
    return "neutral_context"


def _content_type_for(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return "image/jpeg"


def _ocr_prompt() -> str:
    return (
        "이미지에서 사용자가 누를 수 있거나 확인해야 하는 UI 요소만 JSON으로 추출하세요. "
        '스키마: {"title": string, "text": string, "elements": [{"id": string, '
        '"label": string, "element_type": string, "prominence": 1|2|3, '
        '"default_selected": boolean, "monetary_impact": boolean, "optional": boolean}]}. '
        "전체동의, 필수/선택 약관, 프로모션/광고성/마케팅/정보이벤트 수신, 제3자 제공, 처리위탁 행은 "
        "각각 따로 추출하세요. "
        "가입/결제/해지/동의/탈퇴 행동이 없는 커뮤니티 댓글 사진이면 위험 요소를 만들지 말고 "
        "일반 콘텐츠로 요약하세요."
    )


def _detailed_ui_ocr_prompt() -> str:
    return (
        "모바일 화면을 요약하지 말고 조작 가능한 UI 행 단위로 추출하세요. "
        "체크박스, 토글, 라디오, 선택 가능한 목록 행, 주요 버튼을 각각 elements 배열에 하나씩 넣으세요. "
        "화면에 보이는 한국어 라벨을 그대로 보존하세요. "
        "(필수), required 행은 optional=false, (선택), optional, 선택사항 포함 행은 optional=true입니다. "
        "프로모션 정보 수신, 광고성 정보 수신, 마케팅 활용, 정보/이벤트 SMS/메일 수신, 제3자 제공, 처리위탁처럼 "
        "사용자가 거부할 수 있는 동의 항목은 별도 행으로 추출하고 optional=true로 표시하세요. "
        "체크 표시, 활성 토글, 이미 선택된 행은 default_selected=true입니다. "
        "추가 비용, 보험, 부가상품, 무료체험 후 결제, 구독 갱신처럼 돈에 영향이 있으면 monetary_impact=true입니다. "
        "전체동의, 계속, 결제, 해지, 탈퇴 같은 핵심 실행 버튼/행은 prominence=3입니다. "
        "JSON 스키마: {\"title\": string, \"text\": string, \"elements\": [{\"id\": string, "
        "\"label\": string, \"element_type\": string, \"prominence\": 1|2|3, "
        "\"default_selected\": boolean, \"monetary_impact\": boolean, \"optional\": boolean}]}."
    )


def _gemini_ocr_payload(image_bytes: bytes, filename: str | None, prompt: str) -> dict:
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": _content_type_for(filename),
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1600,
            "response_mime_type": "application/json",
            "response_schema": _gemini_ocr_response_schema(),
        },
    }


def _post_gemini_generate_content(settings: Settings, payload: dict) -> str:
    response = httpx.post(
        f"{settings.google_base_url.rstrip('/')}/models/{settings.gemini_model}:generateContent",
        headers={"x-goog-api-key": settings.google_api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=settings.ai_provider_timeout_seconds,
    )
    response.raise_for_status()
    return _gemini_text(response.json())


def _to_extracted_screen(parsed: ExtractedScreenPayload) -> ExtractedScreen:
    elements = [
        ExtractedElement(
            id=element.id,
            label=element.label,
            element_type=element.element_type,
            prominence=element.prominence,
            default_selected=element.default_selected,
            monetary_impact=element.monetary_impact,
            optional=element.optional,
        )
        for element in parsed.elements
    ]
    if not elements:
        elements = [
            ExtractedElement(
                id=element["id"],
                label=element["label"],
                element_type=element["element_type"],
                prominence=element.get("prominence", 1),
                default_selected=element.get("default_selected", False),
                monetary_impact=element.get("monetary_impact", False),
                optional=element.get("optional", False),
            )
            for element in _elements_from_screen_text(title=parsed.title, text=parsed.text)
        ]
    return _enhance_choice_screen(ExtractedScreen(title=parsed.title, text=parsed.text, elements=elements))


def _parse_extracted_screen_payload(raw_content: str) -> ExtractedScreenPayload:
    payload = load_model_json(raw_content)
    if _looks_like_nested_element_payload(payload):
        raise json.JSONDecodeError("OCR payload root is a nested element", raw_content, 0)
    normalized = _normalize_screen_payload(payload)
    return ExtractedScreenPayload.model_validate(normalized)


def _looks_like_nested_element_payload(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    screen_keys = {"title", "screen_title", "text", "description", "content", "elements", "ui_elements", "items"}
    element_keys = {"label", "element_type", "elementType", "type", "default_selected", "defaultSelected", "optional"}
    return not any(key in payload for key in screen_keys) and any(key in payload for key in element_keys)


def _normalize_screen_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("OCR payload must be an object")

    title = _coerce_short_text(payload.get("title") or payload.get("screen_title") or "화면 분석", 120)
    text = _coerce_short_text(payload.get("text") or payload.get("description") or payload.get("content") or "", 1200)
    elements = _normalize_elements(payload.get("elements") or payload.get("ui_elements") or payload.get("items") or [])
    elements = _enhance_choice_payload(title=title, text=text, elements=elements)
    if not elements:
        elements = _elements_from_screen_text(title=title, text=text)

    return {
        "title": title,
        "text": text,
        "elements": elements,
    }


def _normalize_elements(raw_elements: object) -> list[dict]:
    if isinstance(raw_elements, dict):
        raw_items = [raw_elements]
    elif isinstance(raw_elements, list):
        raw_items = raw_elements
    else:
        raw_items = []

    elements: list[dict] = []
    for index, raw_item in enumerate(raw_items[:12]):
        element = _normalize_element(raw_item, index)
        if element:
            elements.append(element)
    return elements


def _normalize_element(raw_item: object, index: int) -> dict | None:
    if isinstance(raw_item, str):
        label = _coerce_short_text(raw_item, 120)
        return {
            "id": _safe_element_id(label, index),
            "label": label,
            "element_type": "content",
        }
    if not isinstance(raw_item, dict):
        return None

    label = _coerce_short_text(
        raw_item.get("label") or raw_item.get("text") or raw_item.get("name") or raw_item.get("title") or "",
        120,
    )
    if not label or label.startswith("{"):
        label = "화면 전체 내용"

    element_type = _coerce_short_text(
        raw_item.get("element_type") or raw_item.get("elementType") or raw_item.get("type") or "content",
        32,
    )
    element = {
        "id": _coerce_short_text(raw_item.get("id") or _safe_element_id(label, index), 64),
        "label": label,
        "element_type": element_type,
        "prominence": _coerce_prominence(raw_item.get("prominence")),
        "default_selected": _coerce_bool(raw_item.get("default_selected") or raw_item.get("defaultSelected")),
        "monetary_impact": _coerce_bool(raw_item.get("monetary_impact") or raw_item.get("monetaryImpact")),
        "optional": _coerce_bool(raw_item.get("optional")),
    }
    return _apply_choice_element_hints(element)


def _elements_from_screen_text(title: str, text: str) -> list[dict]:
    combined = f"{title} {text}".lower()
    rows = _extract_choice_rows(f"{title}\n{text}")
    if rows:
        return rows
    if "약관" in combined and "동의" in combined:
        return [
            {
                "id": "terms_consent_content",
                "label": "약관 동의 내용",
                "element_type": "content",
                "prominence": 2,
            }
        ]
    if "동의" in combined:
        return [
            {
                "id": "consent_content",
                "label": "동의 내용",
                "element_type": "content",
                "prominence": 2,
            }
        ]
    return [
        {
            "id": "screen_text",
            "label": "화면 전체 내용",
            "element_type": "content",
            "prominence": 1,
        }
    ]


def _enhance_choice_payload(title: str, text: str, elements: list[dict]) -> list[dict]:
    source = "\n".join([title, text, *(element.get("label", "") for element in elements)])
    if not _looks_like_choice_screen(source):
        return elements

    enhanced = [_apply_choice_element_hints(element) for element in elements]
    extracted_rows = _extract_choice_rows(source)
    known_labels = {element["label"] for element in enhanced}
    for row in extracted_rows:
        if row["label"] not in known_labels:
            enhanced.append(row)
    return enhanced


def _enhance_choice_screen(screen: ExtractedScreen) -> ExtractedScreen:
    source = "\n".join([screen.title, screen.text, *(element.label for element in screen.elements)])
    if not _looks_like_choice_screen(source):
        return screen

    payload_elements = [
        _apply_choice_element_hints(
            {
                "id": element.id,
                "label": element.label,
                "element_type": element.element_type,
                "prominence": element.prominence,
                "default_selected": element.default_selected,
                "monetary_impact": element.monetary_impact,
                "optional": element.optional,
            }
        )
        for element in screen.elements
    ]
    known_labels = {element["label"] for element in payload_elements}
    for row in _extract_choice_rows(source):
        if row["label"] not in known_labels:
            payload_elements.append(row)

    return ExtractedScreen(
        title=screen.title,
        text=screen.text,
        elements=[
            ExtractedElement(
                id=element["id"],
                label=element["label"],
                element_type=element["element_type"],
                prominence=element["prominence"],
                default_selected=element["default_selected"],
                monetary_impact=element["monetary_impact"],
                optional=element["optional"],
            )
            for element in payload_elements[:12]
        ],
    )


def _apply_choice_element_hints(element: dict) -> dict:
    label = element["label"]
    compact_label = " ".join(label.split())
    source = compact_label.lower()
    if compact_label != label:
        element = {**element, "label": compact_label}
    if "전체동의" in source or "전체 동의" in source:
        element["element_type"] = "checkbox"
        element["prominence"] = 3
        if _looks_optional(source):
            element["optional"] = True
    if _looks_optional(source):
        element["optional"] = True
        element["element_type"] = "checkbox"
    if "(필수)" in source or "필수)" in source or "[필수]" in source or "필수]" in source:
        element["optional"] = False
        element["element_type"] = "checkbox"
    if any(token in source for token in ("동의하고 계속", "계속하기", "결제하기", "해지", "탈퇴", "취소")):
        element["element_type"] = "button"
        element["prominence"] = 3
    if any(token in source for token in ("추가 비용", "원", "결제", "보험", "보증", "무료 체험", "구독", "갱신")):
        element["monetary_impact"] = True
    if element.get("optional") and element["element_type"] == "checkbox" and _looks_selected(source):
        element["default_selected"] = True
    return element


def _extract_choice_rows(source: str) -> list[dict]:
    rows: list[dict] = []
    normalized = source.replace("\\n", "\n")
    for match in re.finditer(
        r"""["'](?:label|name)["']\s*:\s*["'](?P<label>[^"']{1,180})["']""",
        normalized,
        flags=re.IGNORECASE,
    ):
        fragment = normalized[match.start() : min(len(normalized), match.end() + 220)]
        _append_choice_row(rows, match.group("label"), fragment)
    if rows:
        return rows[:12]

    for raw_line in re.split(r"[\n\r]+|(?=\(필수\))|(?=\(선택\))", normalized):
        _append_choice_row(rows, raw_line, raw_line)
    return rows[:12]


def _append_choice_row(rows: list[dict], raw_label: str, raw_context: str) -> None:
    label = _clean_choice_label(raw_label)
    if not label:
        return
    label_source = f"{label} {raw_context}".lower()
    if not _looks_like_choice_row(label_source):
        return
    if any(row["label"] == label for row in rows):
        return
    rows.append(
        {
            "id": _choice_row_id(label, len(rows)),
            "label": label,
            "element_type": _choice_row_type(label_source),
            "prominence": 3 if _looks_primary_action(label_source) else 2,
            "default_selected": _looks_selected(label_source),
            "monetary_impact": _looks_monetary(label_source),
            "optional": _looks_optional(label_source),
        }
    )


def _clean_choice_label(value: str) -> str:
    text = re.sub(r"[>{}\[\]\"']", " ", value)
    text = re.sub(r"\s+", " ", text).strip(" ,-:;")
    if len(text) > 120:
        text = text[:120]
    return text


def _looks_like_choice_row(source: str) -> bool:
    control_signal = any(
        token in source
        for token in (
            "전체동의",
            "전체 동의",
            "(필수)",
            "(선택)",
            "[필수]",
            "[선택]",
            "선택사항",
            "선택항목",
            "선택 정보",
            "optional",
            "required",
            "checkbox",
            "default_selected",
            "checked",
            "동의 여부",
            "미동의",
            "거부",
        )
    )
    consent_signal = any(
        token in source
        for token in (
            "마케팅",
            "광고성",
            "프로모션",
            "정보/이벤트",
            "영리목적",
            "제3자",
            "처리위탁",
            "수집/이용",
            "개인정보",
        )
    )
    row_signal = control_signal or (consent_signal and any(token in source for token in ("동의", "수신", "제공", "이용", "선택", "필수")))
    return (
        row_signal
        or any(token in source for token in ("체크", "토글", "라디오", "보험", "보증", "부가", "추가 비용", "무료 체험"))
        or _looks_primary_action(source)
    )


def _looks_like_choice_screen(source: str) -> bool:
    lowered = source.lower()
    return (
        ("약관" in lowered and "동의" in lowered)
        or "선택사항 포함" in lowered
        or "선택항목" in lowered
        or "선택 정보" in lowered
        or any(
            token in lowered
            for token in (
                "(선택)",
                "(필수)",
                "[선택]",
                "[필수]",
                "optional",
                "required",
                "checkbox",
                "toggle",
                "토글",
                "체크박스",
                "부가",
                "추가 비용",
                "무료 체험",
                "동의 여부",
                "미동의",
                "거부",
                "마케팅",
                "광고성",
                "프로모션",
                "정보/이벤트",
                "영리목적",
                "제3자",
                "처리위탁",
            )
        )
    )


def _looks_selected(source: str) -> bool:
    lowered = source.lower()
    if (
        re.search(r'["\']?default[_\s-]*selected["\']?\s*[:=]\s*false', lowered)
        or re.search(r'["\']?checked["\']?\s*[:=]\s*false', lowered)
        or re.search(r'["\']?selected["\']?\s*[:=]\s*false', lowered)
    ):
        return False
    if (
        re.search(r'["\']?default[_\s-]*selected["\']?\s*[:=]\s*true', lowered)
        or re.search(r'["\']?checked["\']?\s*[:=]\s*true', lowered)
        or re.search(r'["\']?selected["\']?\s*[:=]\s*true', lowered)
    ):
        return True
    selected_tokens = ("선택됨", "체크됨", "checked", "✓", "✔")
    if any(token in lowered for token in selected_tokens):
        return True
    return bool(re.search(r"\bselected\b", lowered) and "default_selected" not in lowered)


def _looks_optional(source: str) -> bool:
    lowered = source.lower()
    if (
        re.search(r'["\']?optional["\']?\s*[:=]\s*false', lowered)
        or re.search(r'["\']?required["\']?\s*[:=]\s*true', lowered)
    ):
        return False
    if (
        "(선택)" in lowered
        or "[선택]" in lowered
        or "선택사항 포함" in lowered
        or "선택항목" in lowered
        or "선택 정보" in lowered
        or "선택 동의" in lowered
        or "동의거부" in lowered
        or "거부 가능" in lowered
        or "거부가능" in lowered
        or "미동의" in lowered
        or "마케팅" in lowered
        or "광고성" in lowered
        or "프로모션" in lowered
        or "정보/이벤트" in lowered
        or "영리목적" in lowered
        or re.search(r'["\']?optional["\']?\s*[:=]\s*true', lowered)
    ):
        return True
    return "optional" in lowered and "required" not in lowered


def _choice_row_id(label: str, index: int) -> str:
    if "전체동의" in label or "전체 동의" in label:
        return "agree_all_terms"
    if "(필수)" in label or "[필수]" in label:
        return f"required_terms_{index + 1}"
    if "(선택)" in label or "[선택]" in label:
        return f"optional_terms_{index + 1}"
    return _safe_element_id(label, index)


def _needs_detailed_ui_retry(parsed: ExtractedScreenPayload) -> bool:
    source = "\n".join([parsed.title, parsed.text, *(element.label for element in parsed.elements)])
    if not _looks_like_choice_screen(source):
        return False
    optional_count = sum(1 for element in parsed.elements if element.optional or "(선택)" in element.label)
    checkbox_count = sum(1 for element in parsed.elements if element.element_type == "checkbox")
    if len(parsed.elements) <= 1:
        return True
    if any(token in source for token in ("(선택)", "선택사항", "optional")) and optional_count == 0:
        return True
    if any(token in source for token in ("(필수)", "required")) and checkbox_count < 2:
        return True
    if "약관" in source and "동의" in source and checkbox_count < 3:
        return True
    return False


def _should_retry_detailed_ui_after_parse_failure(raw_content: str) -> bool:
    lowered = raw_content.lower()
    if not lowered.strip():
        return False
    if _extract_choice_rows(raw_content):
        return True
    return any(
        token in lowered
        for token in (
            '"elements"',
            "'elements'",
            '"element_type"',
            "'element_type'",
            '"default_selected"',
            "'default_selected'",
            '"label"',
            "'label'",
            '"title"',
            "'title'",
            "checkbox",
            "button",
            "toggle",
            "radio",
        )
    )


def _preferred_fallback_content(first_raw_content: str, retry_raw_content: str) -> str:
    first_rows = len(_extract_choice_rows(first_raw_content))
    retry_rows = len(_extract_choice_rows(retry_raw_content))
    if retry_rows > first_rows:
        return retry_raw_content
    if first_raw_content.strip():
        return first_raw_content
    return retry_raw_content


def _choice_row_type(source: str) -> str:
    if "전체동의" in source or "전체 동의" in source:
        return "checkbox"
    if _looks_primary_action(source):
        return "button"
    if any(token in source for token in ("토글", "toggle")):
        return "toggle"
    if any(token in source for token in ("라디오", "radio")):
        return "radio"
    return "checkbox"


def _looks_primary_action(source: str) -> bool:
    return any(token in source for token in ("전체동의", "전체 동의", "동의하고 계속", "계속하기", "결제하기", "해지", "탈퇴", "취소"))


def _looks_monetary(source: str) -> bool:
    return any(token in source for token in ("추가 비용", "원", "결제", "보험", "보증", "무료 체험", "구독", "갱신"))


def _fallback_screen_from_model_text(raw_content: str) -> ExtractedScreen:
    try:
        return _to_extracted_screen(_parse_extracted_screen_payload(raw_content))
    except (TypeError, json.JSONDecodeError, ValidationError):
        logger.warning("Gemini OCR fallback used: %s", compact_text(raw_content))

    text = compact_text(raw_content, limit=1100)
    rows = _extract_choice_rows(raw_content)
    if rows:
        return ExtractedScreen(
            title="화면 선택 항목",
            text=text,
            elements=[
                ExtractedElement(
                    id=row["id"],
                    label=row["label"],
                    element_type=row["element_type"],
                    prominence=row["prominence"],
                    default_selected=row["default_selected"],
                    monetary_impact=row["monetary_impact"],
                    optional=row["optional"],
                )
                for row in rows
            ],
        )

    label = _fallback_label_from_text(text)
    return ExtractedScreen(
        title="화면 전체 분석",
        text=text,
        elements=[
            ExtractedElement(
                id="screen_text",
                label=label,
                element_type="content",
                prominence=1,
            )
        ],
    )


def _fallback_label_from_text(text: str) -> str:
    if text == "empty response body":
        return "화면 전체 내용"
    lowered = text.lower()
    if "약관" in lowered and "동의" in lowered:
        return "약관 동의 내용"
    if "동의" in lowered:
        return "동의 내용"
    return "화면 전체 내용"


def _coerce_short_text(value: object, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _coerce_prominence(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(3, number))


def _safe_element_id(label: str, index: int) -> str:
    source = "".join(char.lower() if char.isalnum() else "_" for char in label if ord(char) < 128)
    source = "_".join(part for part in source.split("_") if part)
    return source[:48] or f"element_{index + 1}"


def _gemini_ocr_response_schema() -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "text": {"type": "STRING"},
            "elements": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "id": {"type": "STRING"},
                        "label": {"type": "STRING"},
                        "element_type": {"type": "STRING"},
                        "prominence": {"type": "INTEGER"},
                        "default_selected": {"type": "BOOLEAN"},
                        "monetary_impact": {"type": "BOOLEAN"},
                        "optional": {"type": "BOOLEAN"},
                    },
                    "required": ["id", "label", "element_type"],
                },
            },
        },
        "required": ["title", "text", "elements"],
    }


def _gemini_text(payload: dict) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise KeyError(f"Gemini candidates 없음: promptFeedback={compact_json(payload.get('promptFeedback'))}")

    for candidate in candidates:
        content = candidate.get("content") if isinstance(candidate, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue
        for part in parts:
            text = part.get("text") if isinstance(part, dict) else None
            if isinstance(text, str) and text.strip():
                return text

    first = candidates[0] if isinstance(candidates[0], dict) else {}
    raise KeyError(
        "Gemini text 없음: "
        f"finishReason={first.get('finishReason')}; "
        f"safetyRatings={compact_json(first.get('safetyRatings'))}"
    )


def _openai_response_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                return content["text"]
    raise KeyError("OpenAI response text not found")


def _exaone_headers(settings: Settings) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {settings.exaone_api_key}",
        "Content-Type": "application/json",
    }
    if settings.exaone_team:
        headers["X-Friendli-Team"] = settings.exaone_team
    return headers


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped
