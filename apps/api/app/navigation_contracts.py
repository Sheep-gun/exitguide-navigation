from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ActionName = Literal["click", "scroll", "back", "wait_and_observe", "stop_for_user"]
RiskLevel = Literal["low", "medium", "high", "blocked"]
ConnectivityStatus = Literal["observed", "device_disconnected", "transport_error"]
TerminalReason = Literal[
    "destination_reached",
    "safe_user_handoff",
    "manual_stop",
    "login_required",
    "sensitive_input_required",
    "permission_required",
    "out_of_scope",
    "step_limit",
    "network_error",
    "device_disconnected",
    "transport_error",
    "executor_error",
    "app_crashed",
    "unknown",
]
NormalizedCoordinate = Annotated[float, Field(ge=0.0, le=1.0)]
NormalizedBounds = tuple[
    NormalizedCoordinate,
    NormalizedCoordinate,
    NormalizedCoordinate,
    NormalizedCoordinate,
]


class CollectionRunContext(BaseModel):
    """Non-secret provenance that cannot be reconstructed after collection."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=200)
    collection_batch_id: str = Field(default="", max_length=200)
    collector_alias: str = Field(default="unassigned", max_length=100)
    device_instance_id: str = Field(default="legacy_unknown", max_length=200)
    manufacturer: str = Field(default="", max_length=120)
    model: str = Field(default="", max_length=120)
    android_api_level: int | None = Field(default=None, ge=1, le=10_000)
    android_release: str = Field(default="", max_length=60)
    display_width_px: int | None = Field(default=None, ge=1, le=100_000)
    display_height_px: int | None = Field(default=None, ge=1, le=100_000)
    density_dpi: int | None = Field(default=None, ge=1, le=10_000)
    font_scale: float | None = Field(default=None, ge=0.5, le=5.0)
    ui_mode: Literal["light", "dark", "unknown"] = "unknown"
    orientation: Literal["portrait", "landscape", "unknown"] = "unknown"
    locale: str = Field(default="", max_length=32)
    collector_app_version: str = Field(default="", max_length=120)
    collector_build_id: str = Field(default="", max_length=160)
    executor_version: str = Field(default="", max_length=120)
    executor_build_id: str = Field(default="", max_length=160)
    run_mode: Literal["agent", "human", "scripted", "replay"] = "agent"
    artifact_policy: Literal[
        "none", "redacted", "test_account_restricted", "raw_full_capture"
    ] = "none"
    test_account: bool = False
    started_at: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def restricted_artifacts_require_test_account(self) -> "CollectionRunContext":
        if self.artifact_policy == "test_account_restricted" and not self.test_account:
            raise ValueError("restricted screenshot retention requires a test account")
        return self


class TaskContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_source: Literal["human", "scripted", "benchmark", "replay"] = "human"
    task_id: str = Field(default="", max_length=200)
    goal_parameters_redacted: dict[str, object] = Field(default_factory=dict)
    task_constraints: list[str] = Field(default_factory=list, max_length=30)
    success_spec_id: str = Field(default="navigation_destination_v1", max_length=200)
    success_spec_version: str = Field(default="1", max_length=80)
    account_state: Literal[
        "logged_out", "logged_in", "reauthentication", "unknown"
    ] = "unknown"
    service_state: Literal[
        "none", "trial", "active", "paused", "cancelled", "unknown"
    ] = "unknown"


class AccessibilityNodeSummary(BaseModel):
    """Privacy-safe semantic node tree captured by AccessibilityService.

    Bounds are retained as normalized evidence for later reprocessing. The
    node/candidate identifier remains the only executable grounding and stored
    coordinates are never used as a fixed model answer.
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
    bounds_normalized: NormalizedBounds | None = None
    window_id: int | None = None
    traversal_index: int | None = Field(default=None, ge=0)
    drawing_order: int | None = Field(default=None, ge=0)
    supported_actions: list[str] = Field(default_factory=list, max_length=50)
    capture_source: Literal["accessibility", "ocr", "vision", "merged"] = "accessibility"
    text_privacy_class: Literal[
        "general", "redacted", "password", "sensitive_input"
    ] = "general"


class NavigationCandidate(BaseModel):
    """A candidate that was actually observed on the current screen.

    Normalized bounds are collection evidence only. The planner still cannot
    invent a tap target outside this candidate set.
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
    bounds_normalized: NormalizedBounds | None = None
    grounding_node_id: str | None = Field(default=None, max_length=200)
    candidate_source: Literal["accessibility", "ocr", "vision", "merged"] = (
        "accessibility"
    )
    candidate_generator_version: str = Field(default="", max_length=120)


class ScreenObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_package: str = Field(default="", max_length=240)
    window_title: str = Field(default="", max_length=500)
    activity_name: str = Field(default="", max_length=500)
    navigation_depth: int | None = Field(default=None, ge=0, le=100)
    frame_id: str | None = Field(default=None, min_length=1, max_length=200)
    frame_sequence_no: int | None = Field(default=None, ge=0)
    captured_device_monotonic_ms: int | None = Field(default=None, ge=0)
    focused_window_id: int | None = None
    window_type: Literal[
        "application", "input_method", "system", "accessibility_overlay", "unknown"
    ] = "unknown"
    surface_type: Literal["native", "webview", "hybrid", "system", "unknown"] = (
        "unknown"
    )
    web_origin_redacted: str | None = Field(default=None, max_length=300)
    screen_width_px: int | None = Field(default=None, ge=1, le=100_000)
    screen_height_px: int | None = Field(default=None, ge=1, le=100_000)
    density_dpi: int | None = Field(default=None, ge=1, le=10_000)
    orientation: Literal["portrait", "landscape", "unknown"] = "unknown"
    nodes_total: int | None = Field(default=None, ge=0)
    nodes_captured: int | None = Field(default=None, ge=0)
    nodes_truncated: bool = False
    candidates_total: int | None = Field(default=None, ge=0)
    candidates_captured: int | None = Field(default=None, ge=0)
    candidates_truncated: bool = False
    capture_capabilities: list[
        Literal["accessibility", "screenshot", "ocr", "vision"]
    ] = Field(default_factory=lambda: ["accessibility"], max_length=4)
    missing_parts: list[str] = Field(default_factory=list, max_length=20)
    screenshot_tree_delta_ms: int | None = Field(default=None, ge=0, le=120_000)
    nodes: list[AccessibilityNodeSummary] = Field(default_factory=list, max_length=500)
    candidates: list[NavigationCandidate] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def candidate_ids_are_unique(self) -> "ScreenObservation":
        if self.nodes_captured is None:
            self.nodes_captured = len(self.nodes)
        if self.nodes_total is None:
            self.nodes_total = self.nodes_captured
        if self.candidates_captured is None:
            self.candidates_captured = len(self.candidates)
        if self.candidates_total is None:
            self.candidates_total = self.candidates_captured
        if self.nodes_total < self.nodes_captured:
            raise ValueError("nodes_total must cover nodes_captured")
        if self.candidates_total < self.candidates_captured:
            raise ValueError("candidates_total must cover candidates_captured")
        if self.nodes_captured != len(self.nodes):
            raise ValueError("nodes_captured must equal the transmitted node count")
        if self.candidates_captured != len(self.candidates):
            raise ValueError("candidates_captured must equal the transmitted candidate count")
        if self.nodes_truncated and self.nodes_total <= self.nodes_captured:
            raise ValueError("nodes_truncated requires omitted nodes")
        if self.candidates_truncated and self.candidates_total <= self.candidates_captured:
            raise ValueError("candidates_truncated requires omitted candidates")
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


class ExecutionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actual_action: NavigationAction | None = None
    executor_method: Literal[
        "accessibility_action",
        "coordinate_tap",
        "gesture",
        "system_global_action",
        "wait",
        "human",
        "not_executed",
        "unknown",
    ] = "unknown"
    attempt_no: int = Field(default=1, ge=1, le=20)
    execution_started_device_monotonic_ms: int | None = Field(default=None, ge=0)
    execution_finished_device_monotonic_ms: int | None = Field(default=None, ge=0)
    failure_code: str = Field(default="", max_length=300)
    settle_duration_ms: int | None = Field(default=None, ge=0, le=120_000)
    settle_reason: str = Field(default="", max_length=300)
    external_package: str = Field(default="", max_length=240)
    human_intervention: bool = False

    @model_validator(mode="after")
    def execution_times_are_ordered(self) -> "ExecutionReport":
        if (
            self.execution_started_device_monotonic_ms is not None
            and self.execution_finished_device_monotonic_ms is not None
            and self.execution_finished_device_monotonic_ms
            < self.execution_started_device_monotonic_ms
        ):
            raise ValueError("execution finish must not precede execution start")
        return self


class DecideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=200)
    session_id: str | None = Field(default=None, min_length=1, max_length=200)
    app_package: str = Field(default="", max_length=240)
    origin_app_package: str = Field(default="", max_length=240)
    current_app_package: str = Field(default="", max_length=240)
    previous_app_package: str = Field(default="", max_length=240)
    transition_reason: Literal[
        "expected_handoff", "user_switch", "system_interstitial", "unknown"
    ] = "unknown"
    app_version: str = Field(default="", max_length=120)
    locale: str = Field(default="ko-KR", min_length=2, max_length=32)
    goal_text: str = Field(min_length=1, max_length=1000)
    step_ordinal: int = Field(default=0, ge=0, le=1000)
    visual_reasoning_required: bool = False
    confirmation_id: str | None = Field(default=None, min_length=1, max_length=200)
    screenshot_data_url: str | None = Field(default=None, max_length=12_000_000)
    raw_screenshot_data_url: str | None = Field(default=None, max_length=12_000_000)
    operator_action: NavigationAction | None = None
    operator_source: Literal["codex"] | None = None
    operator_command_id: str | None = Field(default=None, min_length=1, max_length=200)
    collection_run: CollectionRunContext | None = None
    task_context: TaskContext | None = None
    screen: ScreenObservation

    @model_validator(mode="after")
    def normalize_app_context(self) -> "DecideRequest":
        current = (
            self.current_app_package.strip()
            or self.screen.app_package.strip()
            or self.app_package.strip()
        )
        origin = self.origin_app_package.strip()
        if not origin and self.session_id is None:
            origin = current
        self.app_package = current
        self.current_app_package = current
        self.origin_app_package = origin
        self.previous_app_package = self.previous_app_package.strip()
        return self

    @model_validator(mode="after")
    def operator_command_is_complete(self) -> "DecideRequest":
        command_fields_present = self.operator_source is not None or self.operator_command_id is not None
        if self.operator_action is None and command_fields_present:
            raise ValueError("operator metadata requires operator_action")
        if self.operator_action is not None and (
            self.operator_source is None or self.operator_command_id is None
        ):
            raise ValueError("operator_action requires source and command id")
        return self


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


class SafetyContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str = Field(default="boundary-v2-shadow", max_length=120)
    procedure_stage: str = Field(default="unknown", max_length=160)
    effect_class: Literal[
        "navigate_only",
        "observe_only",
        "automatic_recovery",
        "user_handoff",
        "goal_reached",
        "unknown",
    ] = "unknown"
    boundary: bool = False
    confirmation_required: bool = False
    boundary_evidence: Literal[
        "none",
        "dangerous_candidate",
        "destination_signature",
        "authentication_boundary",
        "policy_block",
    ] = "none"
    boundary_candidate_id: str | None = Field(default=None, max_length=200)
    target_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_code: str = Field(default="", max_length=300)
    consulted_rule_ids: list[str] = Field(default_factory=list, max_length=10)
    rule_conflict: bool = False
    pending_revision: bool = False
    shadow_mode: bool = True


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
    procedure_id: str | None = None
    procedure_step_ordinal: int | None = Field(default=None, ge=0)
    procedure_fast_path_eligible: bool = False
    procedure_fast_path_used: bool = False
    policy_verdict: Literal["allow", "reobserve", "require_confirmation", "block"] | None = None
    policy_rule_ids: list[str] = Field(default_factory=list)
    confirmation_id: str | None = None
    safety_context: SafetyContext


class ConfirmNavigationActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    action: NavigationAction


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
    execution_report: ExecutionReport | None = None
    terminal_reason: TerminalReason | None = None
    handoff_reason: str = Field(default="", max_length=300)
    outcome_judge: Literal["deterministic_evaluator", "human", "agent", "system"] = (
        "deterministic_evaluator"
    )
    evaluator_id: str = Field(default="navigation_transition_verifier", max_length=200)
    evaluator_version: str = Field(default="1", max_length=80)
    before_screenshot_data_url: str | None = Field(default=None, max_length=12_000_000)
    after_screenshot_data_url: str | None = Field(default=None, max_length=12_000_000)
    after_raw_screenshot_data_url: str | None = Field(default=None, max_length=12_000_000)
    next_screen: ScreenObservation | None = None

    @model_validator(mode="after")
    def connectivity_and_screen_are_not_conflated(self) -> "ObserveRequest":
        if self.connectivity_status == "observed" and self.next_screen is None:
            raise ValueError("observed connectivity requires next_screen")
        if self.connectivity_status != "observed" and self.next_screen is not None:
            raise ValueError("transport/device failures must not include a fabricated next_screen")
        return self


class StopSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default="manual_stop", min_length=1, max_length=200)
    terminal_reason: TerminalReason = "manual_stop"
    handoff_reason: str = Field(default="", max_length=300)


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
    procedure_id: str | None = None
    procedure_step_ordinal: int | None = Field(default=None, ge=0)
    procedure_completed: bool = False
