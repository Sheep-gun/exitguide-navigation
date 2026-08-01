import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.services.types import ElementJudgment, ExtractedScreen


ModelDirection = Literal["supports_goal", "conflicts_with_goal", "needs_check"]


class ModelElementJudgment(BaseModel):
    element_id: str
    direction: ModelDirection
    reason: str = Field(min_length=1, max_length=240)


class ModelJudgmentPayload(BaseModel):
    judgments: list[ModelElementJudgment] = Field(default_factory=list)


class ModelOutputError(ValueError):
    pass


def parse_model_judgments(raw_json: str, screen: ExtractedScreen) -> list[ElementJudgment]:
    try:
        payload = ModelJudgmentPayload.model_validate(json.loads(raw_json))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ModelOutputError("LLM provider가 올바르지 않은 판정 JSON을 반환했습니다.") from exc

    elements_by_id = {element.id: element for element in screen.elements}
    judgments_by_id: dict[str, ModelElementJudgment] = {}

    for judgment in payload.judgments:
        if judgment.element_id in elements_by_id:
            judgments_by_id[judgment.element_id] = judgment

    return [
        ElementJudgment(
            element=element,
            direction=judgments_by_id[element.id].direction,
            reason=judgments_by_id[element.id].reason,
        )
        if element.id in judgments_by_id
        else ElementJudgment(
            element=element,
            direction="needs_check",
            reason="모델이 이 화면 요소에 대해 확실한 판정을 반환하지 않았습니다.",
        )
        for element in screen.elements
    ]


def serialize_model_judgments(judgments: list[ElementJudgment]) -> str:
    payload = {
        "judgments": [
            {
                "element_id": judgment.element.id,
                "direction": judgment.direction,
                "reason": judgment.reason,
            }
            for judgment in judgments
        ]
    }
    return json.dumps(payload, ensure_ascii=False)
