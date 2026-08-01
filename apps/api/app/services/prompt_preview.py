from app.schemas import PromptPreviewResponse
from app.services.goal_resolution import DEFAULT_GOAL_ID, resolve_goal_context
from app.services.goals import GOAL_LABELS, normalize_goal_id
from app.services.ocr import get_ocr_provider
from app.services.prompting import SYSTEM_PROMPT, build_element_judgment_prompt
from app.services.scenarios import get_demo_scenario


def build_demo_prompt_preview(
    goal_id: str | None,
    scenario_id: str,
    goal_text: str | None = None,
    infer_goal: bool = False,
) -> PromptPreviewResponse:
    scenario = get_demo_scenario(scenario_id)
    screen = get_ocr_provider("mock").extract(
        image_bytes=b"demo prompt preview",
        filename=scenario.fixture_filename,
        goal_id=_ocr_goal_id(goal_id),
    )
    goal_context = resolve_goal_context(
        goal_id=goal_id,
        goal_text=goal_text,
        screen=screen,
        infer_goal=infer_goal,
    )

    return PromptPreviewResponse(
        goal_id=goal_context.id,
        scenario_id=scenario_id,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_element_judgment_prompt(
            goal_id=goal_context.llm_goal_id,
            goal_label=goal_context.label,
            screen=screen,
        ),
    )


def _ocr_goal_id(goal_id: str | None) -> str:
    if goal_id and goal_id.strip() in GOAL_LABELS:
        return normalize_goal_id(goal_id)
    return DEFAULT_GOAL_ID
