import json

from app.services.types import ExtractedScreen


SYSTEM_PROMPT = """You are ExitGuide AI.
Compare the user's integrated safety goal with visible UI elements.
Do not make legal conclusions.
Return only controlled JSON that follows the requested schema.
Write user-facing reasons in Korean."""


def build_element_judgment_prompt(goal_id: str, goal_label: str, screen: ExtractedScreen) -> str:
    payload = {
        "goal": {
            "id": goal_id,
            "label": goal_label,
        },
        "screen": {
            "title": screen.title,
            "text": screen.text,
            "elements": [
                {
                    "id": element.id,
                    "label": element.label,
                    "type": element.element_type,
                    "prominence": element.prominence,
                    "default_selected": element.default_selected,
                    "monetary_impact": element.monetary_impact,
                    "optional": element.optional,
                }
                for element in screen.elements
            ],
        },
        "output_schema": {
            "judgments": [
                {
                    "element_id": "string",
                    "direction": "supports_goal | conflicts_with_goal | needs_check",
                    "reason": "short user-facing reason",
                }
            ]
        },
        "rules": [
            "Classify by the user's selected goal, not by generic UI quality.",
            "If the image is passive content such as a community comment, feed, article, or normal photo, avoid high risk unless there is a concrete signup, payment, cancellation, consent, or account-deletion action.",
            "Use conflicts_with_goal when tapping or leaving the element selected may pull the user away from the goal.",
            "Use supports_goal when the element appears to advance the goal.",
            "Use needs_check for required steps, ambiguous wording, or insufficient evidence.",
            "Avoid words like illegal, unlawful, scam, fraud, or violation.",
            "Write reason values in Korean.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
