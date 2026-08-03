from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ActionName = Literal["click", "scroll", "back", "wait_and_observe", "stop_for_user"]
RiskLevel = Literal["low", "medium", "high", "blocked"]
ConnectivityStatus = Literal["observed", "device_disconnected", "transport_error"]


class AccessibilityNodeSummary(BaseModel):
    """Privacy-safe semantic node tree captured by AccessibilityService.

    Absolute bounds are intentionally omitted. The node/candidate identifier
    remains the only executable grounding and coordinates never reach a model.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1, max_length=200)
    parent_id: str | None = Field(default=None, min_length=1, max_length=200)
    child_ids: list[str] = Field(default_factory=list, max_length=100)
    text: str = Field(default="", max_length=500)
    content_description: str = Field(default="", max_length=500)
    view_id: str = Field(default="", max_length=300)
    role: str = Field(default="unknown", max_length=120)
    position_bucket: Literal["top", "middle", "bottom", "overlay", "unknown"] = "unknown"
    clickable: bool = False
    enabled: bool = True
    visible: bool = True
    scrollable: bool = False
    checkable: bool = False
    selected: bool = False
    checked: bool | None = None
    private_input: bool = False


class NavigationCandidate(BaseModel):
    """A candidate that was actually observed on the current screen.

    Coordinates are deliberately absent and unknown fields are rejected. The
    planner therefore cannot invent a tap target outside this candidate set.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=200)
    label: str = Field(default="", max_length=500)
    role: str = Field(default="unknown", max_length=120)
    risk_level: RiskLevel = "low"
    icon_semantics: str = Field(default="", max_length=200)
    nearby_text: str = Field(default="", max_length=500)
    parent_semantics: str = Field(default="", max_length=300)
    child_semantics: str = Field(default="", max_length=500)
    visual_role: str = Field(default="", max_length=200)
    visual_region: str = Field(default="", max_length=200)
    visual_relevance: float | None = Field(default=None, ge=0.0, le=1.0)
    position_bucket: Literal["top", "middle", "bottom", "overlay", "unknown"] = "unknown"
    clickable: bool = True
    enabled: bool = True
    selected: bool = False
    checked: bool | None = None


class ScreenObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_package: str = Field(default="", max_length=240)
    window_title: str = Field(default="", max_length=500)
    activity_name: str = Field(default="", max_length=500)
    navigation_depth: int | None = Field(default=None, ge=0, le=100)
    nodes: list[AccessibilityNodeSummary] = Field(default_factory=list, max_length=500)
    candidates: list[NavigationCandidate] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def candidate_ids_are_unique(self) -> "ScreenObservation":
        identifiers = [candidate.candidate_id for candidate in self.candidates]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("candidate_id values must be unique within one screen")
        if self.nodes:
            node_ids = [node.node_id for node in self.nodes]
            known_ids = set(node_ids)
            if len(node_ids) != len(known_ids):
                raise ValueError("node_id values must be unique within one screen")
            if not set(identifiers).issubset(known_ids):
                raise ValueError("every candidate_id must ground to a captured node_id")
            for node in self.nodes:
                references = set(node.child_ids)
                if node.parent_id is not None:
                    references.add(node.parent_id)
                if not references.issubset(known_ids):
                    raise ValueError("node relationships must reference captured node_id values")
        return self


class NavigationAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ActionName
    candidate_id: str | None = None
    direction: Literal["up", "down"] | None = None

    @model_validator(mode="after")
    def action_arguments_match_name(self) -> "NavigationAction":
        if self.name == "click":
            if not self.candidate_id or self.direction is not None:
                raise ValueError("click requires candidate_id and forbids direction")
        elif self.name == "scroll":
            if self.direction is None or self.candidate_id is not None:
                raise ValueError("scroll requires direction and forbids candidate_id")
        elif self.candidate_id is not None or self.direction is not None:
            raise ValueError(f"{self.name} does not accept arguments")
        return self


class DecideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=200)
    session_id: str | None = Field(default=None, min_length=1, max_length=200)
    app_package: str = Field(default="", max_length=240)
    app_version: str = Field(default="", max_length=120)
    locale: str = Field(default="ko-KR", min_length=2, max_length=32)
    goal_text: str = Field(min_length=1, max_length=1000)
    step_ordinal: int = Field(default=0, ge=0, le=1000)
    visual_reasoning_required: bool = False
    screenshot_data_url: str | None = Field(default=None, max_length=12_000_000)
    screen: ScreenObservation


class GoalResolution(BaseModel):
    status: Literal["recognized", "ambiguous", "out_of_scope"]
    goal_id: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    provider: str = "unknown"
    validated_against_db: bool = False
    fallback_used: bool = False


class HierarchicalPlan(BaseModel):
    goal_id: str | None
    stage: Literal[
        "goal_disambiguation",
        "hub_discovery",
        "destination_entry",
        "destination_verification",
        "terminal_boundary",
        "selective_recovery",
    ]
    target_roles: list[str]
    immediate_subgoal: str
    expected_outcome: str
    completion_rule: str
    source: Literal[
        "solar_pro3", "solar_pro4", "decision_memory_fallback", "python_safety_gate"
    ]


class CandidateValue(BaseModel):
    candidate_id: str
    value: float = Field(ge=0.0, le=1.0)
    memory_score: float = Field(ge=0.0, le=1.0)
    role_score: float = Field(ge=0.0, le=1.0)
    verifier_score: float | None = Field(default=None, ge=0.0, le=1.0)
    final_score: float = Field(default=0.0, ge=0.0, le=1.0)
    score_source: Literal["planner_model_verifier", "decision_memory_fallback", "safety_blocked"] = (
        "decision_memory_fallback"
    )
    verifier_reason: str = ""
    memory_support_tier: str = "unknown"
    supporting_cases: int = Field(default=0, ge=0)
    supporting_apps: int = Field(default=0, ge=0)
    conflicting_cases: int = Field(default=0, ge=0)
    provenance_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    fast_path_eligible: bool = False
    confidence_reasons: list[str] = Field(default_factory=list)
    forbidden: bool
    risk_level: RiskLevel


class DecideResponse(BaseModel):
    request_id: str
    session_id: str
    decision_id: str
    goal: GoalResolution
    plan: HierarchicalPlan
    action: NavigationAction
    confidence: float = Field(ge=0.0, le=1.0)
    perception_provider: str
    planner_provider: str
    verifier_provider: str
    planner_fallback_used: bool
    safety_status: Literal["allowed", "replaced_with_safe_action"]
    safety_reason: str
    destination_match: float = Field(ge=0.0, le=1.0)
    candidate_values: list[CandidateValue]
    evidence_case_ids: list[str]
    visual_reobserve_required: bool = False
    visual_reobserve_reason: str = ""
    vlm_recommended_candidate_id: str | None = None


class ObserveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=200)
    decision_id: str = Field(min_length=1, max_length=200)
    connectivity_status: ConnectivityStatus
    observed_signal: Literal[
        "none",
        "external_app",
        "login_required",
        "popup",
        "infinite_feed",
        "network_error",
        "blocked",
    ] = "none"
    execution_succeeded: bool | None = None
    before_screenshot_data_url: str | None = Field(default=None, max_length=12_000_000)
    after_screenshot_data_url: str | None = Field(default=None, max_length=12_000_000)
    next_screen: ScreenObservation | None = None

    @model_validator(mode="after")
    def connectivity_and_screen_are_not_conflated(self) -> "ObserveRequest":
        if self.connectivity_status == "observed" and self.next_screen is None:
            raise ValueError("observed connectivity requires next_screen")
        if self.connectivity_status != "observed" and self.next_screen is not None:
            raise ValueError("transport/device failures must not include a fabricated next_screen")
        return self


class ObserveResponse(BaseModel):
    request_id: str
    session_id: str
    decision_id: str
    outcome_type: Literal[
        "navigated",
        "destination_reached",
        "no_change",
        "wrong_destination",
        "external_app",
        "login_required",
        "popup",
        "infinite_feed",
        "network_error",
        "blocked",
        "unknown",
    ]
    connectivity_status: ConnectivityStatus
    state_changed: bool | None
    progress_label: Literal["reached", "advanced", "unchanged", "regressed", "unknown"]
    destination_match_before: float | None
    destination_match_after: float | None
    failure_class: str
    recovery_action: NavigationAction | None
    candidate_forbidden: bool
    reflection_triggered: bool
    reflection_level: Literal["none", "action", "trajectory", "global"]
    reflection_reason: str
    knowledge_revision_queued: bool
    session_status: Literal["active", "stopped", "reached", "failed"]
    planner_decision_succeeded: bool
    executor_action_succeeded: bool | None
    screen_changed: bool | None
    navigation_progressed: bool | None
    connection_error: bool
