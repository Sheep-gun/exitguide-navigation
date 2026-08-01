import json

import httpx

from app.config import Settings, get_settings
from app.services.errors import ProviderUnavailableError
from app.services.goals import get_goal_label
from app.services.model_output import parse_model_judgments, serialize_model_judgments
from app.services.prompting import SYSTEM_PROMPT, build_element_judgment_prompt
from app.services.provider_errors import compact_json, compact_text, extract_model_json_text, response_error_detail
from app.services.types import ElementJudgment, ExtractedScreen


class LlmProvider:
    def judge_elements(
        self,
        goal_id: str,
        screen: ExtractedScreen,
        goal_label: str | None = None,
    ) -> list[ElementJudgment]:
        raise NotImplementedError


class MockLlmProvider(LlmProvider):
    def judge_elements(
        self,
        goal_id: str,
        screen: ExtractedScreen,
        goal_label: str | None = None,
    ) -> list[ElementJudgment]:
        raw_json = serialize_model_judgments([_judge_element(goal_id, element) for element in screen.elements])
        return parse_model_judgments(raw_json=raw_json, screen=screen)


class ExaoneLlmProvider(LlmProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def judge_elements(
        self,
        goal_id: str,
        screen: ExtractedScreen,
        goal_label: str | None = None,
    ) -> list[ElementJudgment]:
        if not self.settings.exaone_api_key or not self.settings.exaone_model:
            raise ProviderUnavailableError("EXAONE LLM에는 EXAONE_API_KEY와 EXAONE_MODEL이 필요합니다.")

        payload = {
            "model": self.settings.exaone_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_element_judgment_prompt(
                        goal_id=goal_id,
                        goal_label=goal_label or get_goal_label(goal_id),
                        screen=screen,
                    ),
                },
            ],
            "temperature": 0.2,
            "max_tokens": 800,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        content = ""
        try:
            response = httpx.post(
                f"{self.settings.exaone_base_url.rstrip('/')}/chat/completions",
                headers=_exaone_headers(self.settings),
                json=payload,
                timeout=self.settings.exaone_timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return parse_model_judgments(raw_json=_strip_json_fence(content), screen=screen)
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"EXAONE LLM 판정 HTTP {exc.response.status_code}: {response_error_detail(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"EXAONE LLM 연결 오류: {compact_text(str(exc))}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError(f"EXAONE LLM 응답에 본문이 없습니다: {compact_text(str(exc))}") from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise ProviderUnavailableError(f"EXAONE LLM JSON을 읽지 못했습니다: {compact_text(content)}") from exc


class GeminiLlmProvider(LlmProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def judge_elements(
        self,
        goal_id: str,
        screen: ExtractedScreen,
        goal_label: str | None = None,
    ) -> list[ElementJudgment]:
        if not self.settings.google_api_key or not self.settings.gemini_model:
            raise ProviderUnavailableError("Gemini LLM에는 GOOGLE_API_KEY와 GEMINI_MODEL이 필요합니다.")

        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": build_element_judgment_prompt(
                                goal_id=goal_id,
                                goal_label=goal_label or get_goal_label(goal_id),
                                screen=screen,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 800,
                "response_mime_type": "application/json",
                "response_schema": _gemini_judgment_response_schema(),
            },
        }

        content = ""
        try:
            response = httpx.post(
                f"{self.settings.google_base_url.rstrip('/')}/models/{self.settings.gemini_model}:generateContent",
                headers={"x-goog-api-key": self.settings.google_api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=self.settings.ai_provider_timeout_seconds,
            )
            response.raise_for_status()
            content = _gemini_text(response.json())
            return parse_model_judgments(raw_json=extract_model_json_text(content), screen=screen)
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"Gemini LLM 판정 HTTP {exc.response.status_code}: {response_error_detail(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Gemini LLM 연결 오류: {compact_text(str(exc))}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError(f"Gemini LLM 응답에 본문이 없습니다: {compact_text(str(exc))}") from exc
        except (json.JSONDecodeError, ValueError) as exc:
            return [_judge_element(goal_id, element) for element in screen.elements]


class OpenAiLlmProvider(LlmProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def judge_elements(
        self,
        goal_id: str,
        screen: ExtractedScreen,
        goal_label: str | None = None,
    ) -> list[ElementJudgment]:
        if not self.settings.openai_api_key or not self.settings.openai_model:
            raise ProviderUnavailableError("OpenAI LLM에는 OPENAI_API_KEY와 OPENAI_MODEL이 필요합니다.")

        payload = {
            "model": self.settings.openai_model,
            "instructions": SYSTEM_PROMPT,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": build_element_judgment_prompt(
                                goal_id=goal_id,
                                goal_label=goal_label or get_goal_label(goal_id),
                                screen=screen,
                            ),
                        }
                    ],
                }
            ],
            "temperature": 0.2,
            "max_output_tokens": 800,
            "store": False,
        }

        content = ""
        try:
            response = httpx.post(
                f"{self.settings.openai_base_url.rstrip('/')}/responses",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self.settings.ai_provider_timeout_seconds,
            )
            response.raise_for_status()
            content = _openai_response_text(response.json())
            return parse_model_judgments(raw_json=_strip_json_fence(content), screen=screen)
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"OpenAI LLM 판정 HTTP {exc.response.status_code}: {response_error_detail(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"OpenAI LLM 연결 오류: {compact_text(str(exc))}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError(f"OpenAI LLM 응답에 본문이 없습니다: {compact_text(str(exc))}") from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise ProviderUnavailableError(f"OpenAI LLM JSON을 읽지 못했습니다: {compact_text(content)}") from exc


class HyperClovaLlmProvider(LlmProvider):
    def judge_elements(
        self,
        goal_id: str,
        screen: ExtractedScreen,
        goal_label: str | None = None,
    ) -> list[ElementJudgment]:
        raise ProviderUnavailableError("HyperCLOVA provider는 인식되지만 HTTP 클라이언트 연결은 아직 대기 중입니다.")


class UpstageLlmProvider(LlmProvider):
    def judge_elements(
        self,
        goal_id: str,
        screen: ExtractedScreen,
        goal_label: str | None = None,
    ) -> list[ElementJudgment]:
        raise ProviderUnavailableError("Upstage provider는 인식되지만 HTTP 클라이언트 연결은 아직 대기 중입니다.")


def get_llm_provider(name: str, settings: Settings | None = None) -> LlmProvider:
    settings = settings or get_settings()
    if name == "mock":
        return MockLlmProvider()
    if name == "gemini":
        return GeminiLlmProvider(settings)
    if name == "openai":
        return OpenAiLlmProvider(settings)
    if name == "exaone":
        return ExaoneLlmProvider(settings)
    if name == "hyperclova":
        return HyperClovaLlmProvider()
    if name == "upstage":
        return UpstageLlmProvider()
    raise ProviderUnavailableError(f"지원되지 않는 LLM provider입니다: {name}")


def _judge_element(goal_id: str, element):
    label = element.label.lower()
    integrated_goal = goal_id == "protect_user_intent"

    if goal_id in {"protect_user_intent", "cancel_subscription", "cancel_trial"}:
        if element.id in {
            "primary_retention_button",
            "pause_subscription_button",
            "extend_trial_button",
            "discount_retention_button",
        } or any(token in label for token in ("keep", "유지", "더 무료", "계속 이용", "일시중지", "할인받고")):
            return ElementJudgment(
                element=element,
                direction="conflicts_with_goal",
                reason="목표와 반대로 머무르거나 연장하도록 유도합니다.",
            )
        if goal_id == "cancel_trial" or integrated_goal:
            if element.id in {"renewal_warning", "billing_resume_notice"} or any(
                token in label for token in ("renews", "billing", "per month", "결제", "갱신")
            ):
                return ElementJudgment(
                    element=element,
                    direction="needs_check",
                    reason="결제 시점이나 금액 안내를 확인해야 합니다.",
                )
        if element.id in {
            "secondary_cancel_button",
            "complete_cancellation_button",
            "cancel_trial_button",
        } or "continue cancellation" in label or "complete cancellation" in label or "cancel" in label or "해지" in label:
            return ElementJudgment(
                element=element,
                direction="supports_goal",
                reason="해지 진행에 직접 연결되는 선택지입니다.",
            )

    if goal_id in {"protect_user_intent", "buy_without_addons"}:
        if element.default_selected and element.optional and element.monetary_impact:
            return ElementJudgment(
                element=element,
                direction="conflicts_with_goal",
                reason="선택 항목이 기본 선택되어 추가 비용이 발생할 수 있습니다.",
            )
        if "pay" in label or "결제" in label:
            return ElementJudgment(
                element=element,
                direction="needs_check",
                reason="선택 부가 항목이 해제되었는지 확인한 뒤 진행해야 합니다.",
            )

    if goal_id in {"protect_user_intent", "reject_marketing"}:
        terms_like_label = any(token in label for token in ("약관", "동의", "마케팅", "광고", "terms", "consent", "(선택)"))
        if (
            "agree to all" in label
            or "전체동의" in label
            or "전체 동의" in label and "선택" in label
            or element.default_selected and element.optional and (goal_id == "reject_marketing" or terms_like_label)
        ):
            return ElementJudgment(
                element=element,
                direction="conflicts_with_goal",
                reason="선택 약관이나 선택 동의가 함께 포함될 수 있습니다.",
            )
        if "required" in label or "필수" in label:
            return ElementJudgment(
                element=element,
                direction="needs_check",
                reason="필수 약관인지, 선택 동의가 섞이지 않았는지 확인해야 합니다.",
            )

    if goal_id in {"protect_user_intent", "delete_account"}:
        if element.id == "keep_account_button" or "keep" in label or "stay" in label or "유지" in label:
            return ElementJudgment(
                element=element,
                direction="conflicts_with_goal",
                reason="탈퇴 대신 계정을 유지하도록 유도합니다.",
            )
        if element.id in {"delete_account_button", "complete_account_deletion_button"} or "delete account" in label or "탈퇴" in label:
            return ElementJudgment(
                element=element,
                direction="supports_goal",
                reason="계정 탈퇴 진행에 직접 연결되는 선택지입니다.",
            )
        if "data" in label or "removed" in label or "데이터" in label or "복구" in label:
            return ElementJudgment(
                element=element,
                direction="needs_check",
                reason="데이터 삭제나 복구 불가 안내를 확인해야 합니다.",
            )

    return ElementJudgment(
        element=element,
        direction="needs_check",
        reason="목표와 직접 충돌한다는 근거는 부족하지만 진행 전 확인이 필요합니다.",
    )


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


def _gemini_judgment_response_schema() -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "judgments": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "element_id": {"type": "STRING"},
                        "direction": {
                            "type": "STRING",
                            "enum": ["supports_goal", "conflicts_with_goal", "needs_check"],
                        },
                        "reason": {"type": "STRING"},
                    },
                    "required": ["element_id", "direction", "reason"],
                },
            }
        },
        "required": ["judgments"],
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
