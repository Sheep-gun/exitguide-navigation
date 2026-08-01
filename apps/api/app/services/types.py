from dataclasses import dataclass
from typing import Literal


Direction = Literal["supports_goal", "conflicts_with_goal", "needs_check"]


@dataclass(frozen=True)
class ExtractedElement:
    id: str
    label: str
    element_type: str
    prominence: int = 1
    default_selected: bool = False
    monetary_impact: bool = False
    optional: bool = False


@dataclass(frozen=True)
class ExtractedScreen:
    title: str
    text: str
    elements: list[ExtractedElement]


@dataclass(frozen=True)
class ElementJudgment:
    element: ExtractedElement
    direction: Direction
    reason: str
