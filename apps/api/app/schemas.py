from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high"]
ElementDirection = Literal["supports_goal", "conflicts_with_goal", "needs_check"]
AnalysisMode = Literal["demo", "upload"]
DemoQualityStatus = Literal["pass", "fail"]
DemoQualitySource = Literal["scenario", "synthetic"]
AiProviderId = Literal["server", "google", "gpt", "exaone"]
ConsentCaseSource = Literal["synthetic", "field_candidate", "captured_redacted"]
ConsentCaseCaptureMethod = Literal[
    "manual_synthetic",
    "manual_field_observation",
    "user_submitted_screen",
    "user_submitted_text",
]
ConsentCaseArtifactType = Literal[
    "text_only",
    "redacted_text_only",
    "redacted_screenshot",
    "synthetic_screen",
]
ConsentCaseRedactionStatus = Literal["not_required", "pending_review", "redacted"]
ConsentCaseReviewStatus = Literal["not_required", "pending_review", "approved", "rejected"]
ConsentCaseEvaluationScope = Literal["deterministic_rule_calibration"]
TermsDocumentType = Literal[
    "terms_of_service",
    "privacy_policy",
    "subscription_terms",
    "location_terms",
    "marketing_terms",
    "cancellation_policy",
    "unknown",
]
TermsCollectionMethod = Literal["synthetic_seed", "openclaw", "manual", "imported"]
TermsRetrievalStatus = Literal["captured", "needs_review", "failed"]
TermsCaptureImportStatus = Literal["imported", "rejected", "duplicate"]
CollectionPlatform = Literal["ios", "android", "web"]
CollectionStatus = Literal["seed", "pending", "discovered", "active", "blocked", "retired"]
CollectionDocumentSourceType = Literal[
    "terms",
    "privacy",
    "refund_policy",
    "help",
    "faq",
    "platform_policy",
    "signup",
    "unknown",
]
CollectionReviewStatus = Literal["pending", "in_progress", "approved", "rejected", "needs_more_evidence", "not_required"]
CollectionFlowStatus = Literal["active", "outdated", "unverified", "blocked"]
CollectionVerificationMethod = Literal["bot", "human", "user_report", "official_doc", "synthetic_seed"]
CollectionPaymentChannel = Literal["apple", "google_play", "direct_card", "carrier", "unknown"]
CollectionUserGoal = Literal[
    "subscription_cancel",
    "free_trial_cancel",
    "account_delete",
    "refund_request",
    "marketing_opt_out",
]
SolarDemoRiskLevel = Literal["low", "medium", "high", "needs_check"]
SolarDemoRiskSignal = Literal[
    "cancel_friction",
    "refund_limit",
    "excessive_penalty",
    "cooling_off_block",
    "misleading_retention",
    "needs_check",
]
SolarDemoConfidence = Literal["low", "medium", "high"]
SolarDemoActor = Literal["user", "mobile_app", "api", "retrieval", "agent"]
SolarDemoEvidenceSource = Literal["screen", "consumer_reference_case"]


class UiElement(BaseModel):
    id: str
    label: str
    element_type: str
    direction: ElementDirection
    risk_level: RiskLevel
    reason: str
    signals: list[str] = Field(default_factory=list)


class RecommendedAction(BaseModel):
    title: str
    description: str
    target_element_id: str | None = None


class ProofCard(BaseModel):
    goal: str
    summary: str
    key_evidence: list[str] = Field(default_factory=list)
    disclaimer: str


class RiskBreakdown(BaseModel):
    low: int = 0
    medium: int = 0
    high: int = 0


class AnalysisResponse(BaseModel):
    analysis_id: str = Field(pattern=r"^an_[a-f0-9]{12}$")
    goal_id: str
    goal_label: str
    screen_title: str
    analysis_mode: AnalysisMode
    overall_risk: RiskLevel
    alignment_score: int = Field(ge=0, le=100)
    risk_counts: RiskBreakdown
    summary: str
    elements: list[UiElement]
    recommended_action: RecommendedAction
    proof_card: ProofCard


class GoalDefinition(BaseModel):
    id: str
    label: str
    description: str


class DemoScenarioDefinition(BaseModel):
    id: str
    label: str
    description: str
    recommended_goal_id: str
    fixture_filename: str


class DemoFlowDefinition(BaseModel):
    id: str
    label: str
    description: str
    goal_id: str
    scenario_ids: list[str]


class SyntheticScreenDefinition(BaseModel):
    filename: str
    category: str
    recommended_goal_id: str
    risk_fixture: RiskLevel
    notes: str


class SyntheticScreenCatalog(BaseModel):
    description: str
    screen_count: int
    screens: list[SyntheticScreenDefinition]


class ConsentCaseElement(BaseModel):
    id: str
    label: str
    element_type: str
    prominence: int = Field(default=1, ge=1, le=3)
    default_selected: bool = False
    optional: bool = False
    monetary_impact: bool = False
    expected_direction: ElementDirection
    expected_risk: RiskLevel
    notes: str = ""


class ConsentCaseDatasetMetadata(BaseModel):
    dataset_schema_version: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    label_rubric_version: str = Field(min_length=1)
    rule_set_version: str = Field(min_length=1)


class ConsentCaseProvenance(BaseModel):
    capture_method: ConsentCaseCaptureMethod
    artifact_type: ConsentCaseArtifactType
    redaction_status: ConsentCaseRedactionStatus
    review_status: ConsentCaseReviewStatus
    public_fixture_allowed: bool = False
    contains_raw_screenshot: bool = False
    contains_ocr_text: bool = False
    raw_artifact_in_repo: bool = False
    notes: str = Field(default="", max_length=300)


class ConsentCaseDefinition(BaseModel):
    id: str
    title: str
    category: str
    source_type: ConsentCaseSource
    source: ConsentCaseProvenance
    locale: str = "ko-KR"
    recommended_goal_id: str
    expected_risk: RiskLevel
    screen_title: str
    screen_text: str
    tags: list[str] = Field(default_factory=list)
    data_notes: str = Field(default="", max_length=500)
    elements: list[ConsentCaseElement] = Field(min_length=1)


class ConsentCaseSummary(BaseModel):
    case_count: int
    element_count: int
    source_counts: dict[str, int]
    category_counts: dict[str, int]
    risk_counts: dict[str, int]
    tag_counts: dict[str, int]


class ConsentCaseCatalog(BaseModel):
    description: str
    metadata: ConsentCaseDatasetMetadata
    summary: ConsentCaseSummary
    cases: list[ConsentCaseDefinition]


class ConsentCaseQualityCalibration(BaseModel):
    id: str
    title: str
    category: str
    source_type: ConsentCaseSource
    goal_id: str
    expected_risk: RiskLevel
    actual_risk: RiskLevel | None = None
    expected_element_risks: dict[str, RiskLevel] = Field(default_factory=dict)
    actual_element_risks: dict[str, RiskLevel] = Field(default_factory=dict)
    expected_element_directions: dict[str, ElementDirection] = Field(default_factory=dict)
    actual_element_directions: dict[str, ElementDirection] = Field(default_factory=dict)
    passed: bool
    detail: str


class ConsentCaseCalibrationSummary(BaseModel):
    total: int
    passed: int
    failed: int
    passed_by_risk: dict[str, int] = Field(default_factory=dict)
    failed_by_risk: dict[str, int] = Field(default_factory=dict)
    passed_by_source: dict[str, int] = Field(default_factory=dict)
    failed_by_source: dict[str, int] = Field(default_factory=dict)
    failed_case_ids: list[str] = Field(default_factory=list)


class ConsentCaseCoverageTarget(BaseModel):
    id: str
    label: str
    target: int = Field(ge=0)
    actual: int = Field(ge=0)
    passed: bool


class ConsentCaseCoverageReport(BaseModel):
    status: Literal["pass", "warn"]
    targets: list[ConsentCaseCoverageTarget]
    warnings: list[str] = Field(default_factory=list)


class ConsentCaseQualityResponse(BaseModel):
    status: DemoQualityStatus
    evaluation_scope: ConsentCaseEvaluationScope = "deterministic_rule_calibration"
    not_evaluated: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    metadata: ConsentCaseDatasetMetadata
    summary: ConsentCaseSummary
    calibration_summary: ConsentCaseCalibrationSummary
    coverage: ConsentCaseCoverageReport
    calibrations: list[ConsentCaseQualityCalibration]


class TermsCorpusMetadata(BaseModel):
    dataset_schema_version: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    collection_policy_version: str = Field(min_length=1)


class TermsSection(BaseModel):
    id: str = Field(min_length=1)
    heading: str = Field(min_length=1)
    text: str = Field(min_length=1)


class TermsDocument(BaseModel):
    id: str = Field(min_length=1)
    service_name: str = Field(min_length=1)
    provider_name: str = Field(min_length=1)
    document_type: TermsDocumentType
    locale: str = "ko-KR"
    source_url: str = Field(min_length=1)
    collected_at: str = Field(min_length=1)
    collection_method: TermsCollectionMethod
    retrieval_status: TermsRetrievalStatus
    public_fixture_allowed: bool = False
    raw_personal_data: bool = False
    license_notes: str = ""
    tags: list[str] = Field(default_factory=list)
    sections: list[TermsSection] = Field(min_length=1)


class TermsCorpusSummary(BaseModel):
    document_count: int
    section_count: int
    chunk_count: int
    document_type_counts: dict[str, int]
    collection_method_counts: dict[str, int]
    tag_counts: dict[str, int]


class TermsCorpusCatalog(BaseModel):
    description: str
    metadata: TermsCorpusMetadata
    summary: TermsCorpusSummary
    documents: list[TermsDocument]


class TermsChunk(BaseModel):
    id: str
    document_id: str
    section_id: str
    service_name: str
    document_type: TermsDocumentType
    heading: str
    text: str
    tags: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)


class TermsSearchResult(BaseModel):
    chunk: TermsChunk
    score: int
    matched_terms: list[str] = Field(default_factory=list)


class TermsSearchResponse(BaseModel):
    query: str
    total: int
    results: list[TermsSearchResult]


class TermsCoverageTarget(BaseModel):
    id: str
    label: str
    target: int = Field(ge=0)
    actual: int = Field(ge=0)
    passed: bool


class TermsCorpusQualityResponse(BaseModel):
    status: Literal["pass", "warn", "fail"]
    metadata: TermsCorpusMetadata
    summary: TermsCorpusSummary
    coverage_targets: list[TermsCoverageTarget]
    warnings: list[str] = Field(default_factory=list)


class TermsCaptureImportItem(BaseModel):
    capture_id: str
    source_path: str
    source_url: str = ""
    collection_method: TermsCollectionMethod | None = None
    content_sha256: str | None = None
    document_id: str | None = None
    status: TermsCaptureImportStatus
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TermsCaptureImportResponse(BaseModel):
    input_path: str
    output_path: str
    capture_count: int
    imported_document_count: int
    rejected_count: int
    duplicate_count: int
    items: list[TermsCaptureImportItem]


class CollectionRegistryMetadata(BaseModel):
    dataset_schema_version: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    collection_policy_version: str = Field(min_length=1)


class ServiceRegistryEntry(BaseModel):
    service_id: str = Field(min_length=1)
    service_name: str = Field(min_length=1)
    service_aliases: list[str] = Field(default_factory=list)
    country: str = Field(min_length=2)
    language: str = Field(min_length=2)
    platforms: list[CollectionPlatform] = Field(min_length=1)
    category: str = Field(min_length=1)
    official_website_url: str = Field(min_length=1)
    app_store_url: str = ""
    play_store_url: str = ""
    developer_name: str = ""
    priority_score: int = Field(ge=0, le=100)
    collection_status: CollectionStatus
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class DocumentSourceEntry(BaseModel):
    document_id: str = Field(min_length=1)
    service_id: str = Field(min_length=1)
    document_type: CollectionDocumentSourceType
    source_url: str = Field(min_length=1)
    source_domain: str = Field(min_length=1)
    language: str = Field(min_length=2)
    country_or_region: str = Field(min_length=2)
    first_seen_at: str = Field(min_length=1)
    last_seen_at: str = Field(min_length=1)
    last_fetched_at: str = ""
    http_status: int = Field(ge=0, le=599)
    content_hash: str = ""
    is_active: bool = True
    robots_allowed: bool = False
    manual_review_required: bool = True


class CancellationFlowEntry(BaseModel):
    flow_id: str = Field(min_length=1)
    service_id: str = Field(min_length=1)
    user_goal: CollectionUserGoal
    platform: CollectionPlatform
    payment_channel: CollectionPaymentChannel
    country_or_region: str = Field(min_length=2)
    app_version: str = ""
    last_verified_at: str = Field(min_length=1)
    verification_method: CollectionVerificationMethod
    confidence: float = Field(ge=0.0, le=1.0)
    status: CollectionFlowStatus
    requires_login: bool = True
    requires_customer_support: bool = False
    estimated_steps_count: int = Field(ge=0)
    notes: str = ""


class FlowStepEntry(BaseModel):
    step_id: str = Field(min_length=1)
    flow_id: str = Field(min_length=1)
    step_order: int = Field(ge=1)
    screen_name: str = Field(min_length=1)
    action_type: str = Field(min_length=1)
    instruction_text: str = Field(min_length=1)
    button_or_link_text: str = ""
    expected_result: str = ""
    screenshot_path: str = ""
    ocr_text: str = ""
    ux_friction_label: str = "none"
    risk_note: str = ""


class ReviewTaskEntry(BaseModel):
    review_task_id: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    service_id: str = Field(min_length=1)
    priority: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1)
    status: CollectionReviewStatus
    reviewer_note: str = ""
    created_at: str = Field(min_length=1)
    completed_at: str = ""


class CollectionRegistrySummary(BaseModel):
    service_count: int
    document_source_count: int
    review_task_count: int
    flow_count: int
    flow_step_count: int
    platform_counts: dict[str, int]
    document_type_counts: dict[str, int]
    review_status_counts: dict[str, int]
    collection_status_counts: dict[str, int]


class CollectionCoverageTarget(BaseModel):
    id: str
    label: str
    target: int = Field(ge=0)
    actual: int = Field(ge=0)
    passed: bool


class CollectionRegistryCatalog(BaseModel):
    description: str
    metadata: CollectionRegistryMetadata
    summary: CollectionRegistrySummary
    services: list[ServiceRegistryEntry]
    document_sources: list[DocumentSourceEntry]
    cancellation_flows: list[CancellationFlowEntry]
    flow_steps: list[FlowStepEntry]
    review_tasks: list[ReviewTaskEntry]


class CollectionRegistryQualityResponse(BaseModel):
    status: Literal["pass", "warn", "fail"]
    metadata: CollectionRegistryMetadata
    summary: CollectionRegistrySummary
    coverage_targets: list[CollectionCoverageTarget]
    warnings: list[str] = Field(default_factory=list)


class SolarDemoWorkflowMetadata(BaseModel):
    dataset_schema_version: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    source_dataset: str = Field(min_length=1)
    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    generated_at: str = Field(min_length=1)
    legal_advice_policy: Literal["not_legal_advice"]


class SolarDemoWorkflowSourceReference(BaseModel):
    dataset: str = Field(min_length=1)
    product: str = Field(min_length=1)
    category: str = Field(min_length=1)
    public_case_number: str = Field(min_length=1)


class SolarDemoWorkflowInput(BaseModel):
    user_goal: str = Field(min_length=1)
    screen_context: str = Field(min_length=1)
    visible_screen_text: list[str] = Field(min_length=1)


class SolarDemoGoalConflict(BaseModel):
    screen_text: str = Field(min_length=1)
    risk_signal: SolarDemoRiskSignal
    why_it_matters: str = Field(min_length=1)


class SolarDemoReferenceGuidance(BaseModel):
    matched_point: str = Field(min_length=1)
    safe_user_facing_summary: str = Field(min_length=1)
    not_legal_advice: bool = True


class SolarDemoRecommendedAction(BaseModel):
    primary: str = Field(min_length=1)
    avoid: str = Field(min_length=1)
    next_evidence_to_collect: list[str] = Field(default_factory=list)


class SolarDemoWorkflowStep(BaseModel):
    step: int = Field(ge=1)
    actor: SolarDemoActor
    output: str = Field(min_length=1)


class SolarDemoEvidenceQuote(BaseModel):
    source: SolarDemoEvidenceSource
    quote: str = Field(min_length=1)


class SolarDemoModelResult(BaseModel):
    model_provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    risk_level: SolarDemoRiskLevel
    confidence: SolarDemoConfidence
    screen_summary: str = Field(min_length=1)
    goal_conflicts: list[SolarDemoGoalConflict] = Field(min_length=1)
    reference_guidance: SolarDemoReferenceGuidance
    recommended_action: SolarDemoRecommendedAction
    demo_workflow_steps: list[SolarDemoWorkflowStep] = Field(min_length=1)
    evidence_quotes: list[SolarDemoEvidenceQuote] = Field(default_factory=list)


class SolarDemoWorkflow(BaseModel):
    id: str = Field(min_length=1)
    case_number: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_reference: SolarDemoWorkflowSourceReference
    demo_input: SolarDemoWorkflowInput
    model_result: SolarDemoModelResult


class SolarDemoWorkflowSummary(BaseModel):
    workflow_count: int
    risk_counts: dict[str, int]
    confidence_counts: dict[str, int]
    source_dataset_counts: dict[str, int]


class SolarDemoWorkflowCatalog(BaseModel):
    description: str
    metadata: SolarDemoWorkflowMetadata
    summary: SolarDemoWorkflowSummary
    workflows: list[SolarDemoWorkflow]


class ProviderRequestFields(BaseModel):
    provider_id: AiProviderId | None = None
    provider_api_key: str | None = Field(default=None, max_length=4096)
    provider_model: str | None = Field(default=None, max_length=160)
    provider_base_url: str | None = Field(default=None, max_length=512)


class DemoAnalysisRequest(BaseModel):
    provider_id: AiProviderId | None = None
    provider_api_key: str | None = Field(default=None, max_length=4096)
    provider_model: str | None = Field(default=None, max_length=160)
    provider_base_url: str | None = Field(default=None, max_length=512)
    goal_id: str | None = None
    goal_text: str | None = None
    infer_goal: bool = False
    scenario_id: str


class FlowAnalysisRequest(BaseModel):
    provider_id: AiProviderId | None = None
    provider_api_key: str | None = Field(default=None, max_length=4096)
    provider_model: str | None = Field(default=None, max_length=160)
    provider_base_url: str | None = Field(default=None, max_length=512)
    goal_id: str | None = None
    goal_text: str | None = None
    infer_goal: bool = False
    scenario_ids: list[str] = Field(min_length=2, max_length=6)


class FlowAnalysisResponse(BaseModel):
    flow_id: str = Field(pattern=r"^fl_[a-f0-9]{12}$")
    goal_id: str
    goal_label: str
    overall_risk: RiskLevel
    alignment_score: int = Field(ge=0, le=100)
    screen_count: int = Field(ge=0)
    highest_risk_screen_number: int | None = Field(default=None, ge=1)
    risk_counts: RiskBreakdown
    risk_path: list[RiskLevel] = Field(default_factory=list)
    summary: str
    screens: list[AnalysisResponse]
    proof_card: ProofCard


class PromptPreviewRequest(BaseModel):
    provider_id: AiProviderId | None = None
    provider_api_key: str | None = Field(default=None, max_length=4096)
    provider_model: str | None = Field(default=None, max_length=160)
    provider_base_url: str | None = Field(default=None, max_length=512)
    goal_id: str | None = None
    goal_text: str | None = None
    infer_goal: bool = False
    scenario_id: str


class PromptPreviewResponse(BaseModel):
    goal_id: str
    scenario_id: str
    system_prompt: str
    user_prompt: str


class ApiStatus(BaseModel):
    status: str
    ocr_provider: str
    llm_provider: str
    provider_ready: bool
    provider_notes: list[str] = Field(default_factory=list)
    supported_ai_providers: list[AiProviderId] = Field(default_factory=list)


class ApiProviderOption(BaseModel):
    id: AiProviderId
    label: str
    model: str = ""
    base_url: str = ""
    ready: bool = False


class ReadinessCheck(BaseModel):
    id: str
    label: str
    passed: bool
    detail: str


class DemoReadinessResponse(BaseModel):
    status: Literal["ready", "needs_setup"]
    checks: list[ReadinessCheck]


class DemoQualitySummary(BaseModel):
    readiness_passed: int
    readiness_total: int
    scenarios_passed: int
    scenarios_total: int
    flows_passed: int
    flows_total: int
    synthetic_passed: int
    synthetic_total: int


class DemoQualityCalibration(BaseModel):
    id: str
    label: str
    source: DemoQualitySource
    goal_id: str
    expected_risk: RiskLevel | None = None
    actual_risk: RiskLevel | None = None
    alignment_score: int | None = Field(default=None, ge=0, le=100)
    passed: bool
    detail: str


class DemoQualityFlowCalibration(BaseModel):
    id: str
    label: str
    goal_id: str
    expected_overall_risk: RiskLevel | None = None
    actual_overall_risk: RiskLevel | None = None
    expected_risk_path: list[RiskLevel] = Field(default_factory=list)
    actual_risk_path: list[RiskLevel] = Field(default_factory=list)
    alignment_score: int | None = Field(default=None, ge=0, le=100)
    passed: bool
    detail: str


class DemoQualityResponse(BaseModel):
    status: DemoQualityStatus
    summary: DemoQualitySummary
    checks: list[ReadinessCheck]
    scenario_calibrations: list[DemoQualityCalibration]
    flow_calibrations: list[DemoQualityFlowCalibration]
    synthetic_calibrations: list[DemoQualityCalibration]


NavigationGuideStatus = Literal["guided", "needs_review", "route_not_found", "goal_completed"]
NavigationState = Literal[
    "on_route",
    "reanchored",
    "recovery_required",
    "needs_review",
    "completed",
    "route_not_found",
]


class NavigationScreenElement(BaseModel):
    id: str = Field(min_length=1)
    text: str | None = None
    content_description: str | None = None
    view_id: str | None = None
    role: str = "unknown"
    clickable: bool = False
    bounds: list[int] | None = Field(default=None, min_length=4, max_length=4)
    prominence: int = Field(default=1, ge=1, le=3)
    default_selected: bool = False
    optional: bool = False
    monetary_impact: bool = False


class NavigationSession(BaseModel):
    last_confirmed_state_id: str | None = None
    failed_element_ids: list[str] = Field(default_factory=list)
    failed_candidate_meanings: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0, ge=0, le=10)


class NavigationGuideRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=120)
    app_package: str = Field(min_length=1, max_length=240)
    app_version: str = ""
    platform: Literal["android"] = "android"
    locale: str = "ko-KR"
    goal_id: str | None = None
    goal_text: str | None = Field(default=None, max_length=500)
    session: NavigationSession = Field(default_factory=NavigationSession)
    screen_elements: list[NavigationScreenElement] = Field(min_length=1, max_length=250)


class NavigationRecovery(BaseModel):
    type: Literal["back", "dismiss", "stop"]
    safe: bool
    expected_previous_state_id: str | None = None
    retry_after_recovery: bool = False


class NavigationTermsEvidence(BaseModel):
    heading: str
    text: str
    document_id: str


class NavigationTermsHint(BaseModel):
    query: str
    summary: str
    evidence: list[NavigationTermsEvidence] = Field(default_factory=list)
    disclaimer: str = "검증용 합성 약관 근거이며 법률 자문이 아닙니다."


DarkPatternType = Literal[
    "retention_misdirection",
    "preselected_cost",
    "bundled_consent",
    "asymmetric_prominence",
]


class DarkPatternScreenElement(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    role: str = "unknown"
    clickable: bool = False
    prominence: int = Field(default=1, ge=1, le=3)
    default_selected: bool = False
    optional: bool = False
    monetary_impact: bool = False


class DarkPatternInspectRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=120)
    goal_id: str | None = None
    goal_text: str | None = Field(default=None, max_length=500)
    screen_title: str = Field(min_length=1, max_length=300)
    screen_text: str = Field(default="", max_length=4000)
    elements: list[DarkPatternScreenElement] = Field(min_length=1, max_length=100)


class DarkPatternFinding(BaseModel):
    type: DarkPatternType
    label: str
    severity: RiskLevel
    element_id: str
    evidence: str
    explanation: str


class DarkPatternInspectResponse(BaseModel):
    request_id: str
    goal_id: str
    goal_label: str
    screen_title: str
    overall_risk: RiskLevel
    alignment_score: int = Field(ge=0, le=100)
    summary: str
    findings: list[DarkPatternFinding] = Field(default_factory=list)
    elements: list[UiElement]
    recommended_action: RecommendedAction
    proof_card: ProofCard


class NavigationGuideResponse(BaseModel):
    request_id: str
    route_id: str | None = None
    route_version: int | None = None
    goal_id: str | None = None
    current_step: int | None = None
    current_state_id: str | None = None
    target_element_id: str | None = None
    target_label: str | None = None
    instruction: str
    warning: str | None = None
    requires_user_confirmation: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    navigation_state: NavigationState
    recovery: NavigationRecovery | None = None
    terms_hint: NavigationTermsHint | None = None
    dark_pattern: DarkPatternInspectResponse | None = None
    source_files: list[str] = Field(default_factory=list)
    status: NavigationGuideStatus


class NavigationRouteSummary(BaseModel):
    route_id: str
    service_name: str
    app_package: str
    platform: str
    locale: str
    goal_id: str
    route_version: int
    state_count: int
    status: str
    source_file: str


class NavigationRouteCatalog(BaseModel):
    description: str
    route_count: int
    routes: list[NavigationRouteSummary]


UniversalNavigationRisk = Literal["low", "medium", "high", "blocked"]
UniversalNavigationStatus = Literal[
    "guided",
    "goal_completed",
    "needs_user_input",
    "no_safe_action",
    "recording",
]
UniversalNavigationDecisionMode = Literal[
    "exaone",
    "graph_cache",
    "route_cache",
    "function_graph_exploration",
    "deterministic_fallback",
    "human_recording",
]
UniversalNavigationTransitionOutcome = Literal[
    "navigated",
    "no_change",
    "failed",
    "unexpected",
    "cancelled",
]
UniversalNavigationOperationMode = Literal["guide", "explore", "record"]
UniversalNavigationPhase = Literal[
    "guide",
    "exploring",
    "returning_to_start",
    "guiding",
    "destination_reached",
    "stopped",
    "recording",
]
UniversalNavigationAutomationAction = Literal["none", "click", "scroll_forward", "back", "stop"]
UniversalNavigationMeasurementSource = Literal[
    "server_runtime",
    "synthetic",
    "real_device",
    "real_device_gold",
]
UniversalNavigationRouteLifecycle = Literal[
    "shadow",
    "verified_candidate",
    "approved",
    "rejected",
    "stale",
]


class UniversalNavigationElement(BaseModel):
    id: str = Field(min_length=1, max_length=240)
    parent_id: str | None = Field(default=None, max_length=240)
    text: str | None = Field(default=None, max_length=500)
    content_description: str | None = Field(default=None, max_length=500)
    view_id: str | None = Field(default=None, max_length=500)
    role: str = Field(default="unknown", max_length=80)
    clickable: bool = False
    enabled: bool = True
    visible: bool = True
    scrollable: bool = False
    checkable: bool = False
    checked: bool | None = None
    selected: bool = False
    password: bool = False
    bounds: list[int] | None = Field(default=None, min_length=4, max_length=4)


class UniversalNavigationScreen(BaseModel):
    activity_name: str = Field(default="", max_length=300)
    window_title: str = Field(default="", max_length=300)
    event_type: str = Field(default="window_state_changed", max_length=100)
    captured_at: str = Field(default="", max_length=80)
    elements: list[UniversalNavigationElement] = Field(min_length=1, max_length=500)


class UniversalNavigationTransition(BaseModel):
    from_screen_fingerprint: str = Field(pattern=r"^us_[a-f0-9]{16}$")
    performed_element_id: str = Field(min_length=1, max_length=240)
    action_kind: Literal["click", "scroll_forward", "back"] = "click"
    recommendation_id: str | None = Field(default=None, pattern=r"^ur_[a-f0-9]{16}$")
    outcome: UniversalNavigationTransitionOutcome = "navigated"


class UniversalNavigationClientTiming(BaseModel):
    # Client telemetry is always ordinary real-device timing. Gold provenance
    # can only be assigned by the server-controlled offline importer.
    measurement_source: Literal["real_device"] = "real_device"
    exploration_elapsed_ms: float | None = Field(default=None, ge=0.0, le=3_600_000.0)
    screen_capture_ms: float = Field(default=0.0, ge=0.0, le=300_000.0)
    action_execution_ms: float = Field(default=0.0, ge=0.0, le=300_000.0)
    ui_settle_ms: float = Field(default=0.0, ge=0.0, le=300_000.0)
    external_wait_ms: float = Field(default=0.0, ge=0.0, le=300_000.0)


class UniversalNavigationObserveRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=120)
    session_id: str = Field(min_length=1, max_length=120)
    app_package: str = Field(min_length=1, max_length=240)
    app_version: str = Field(default="", max_length=120)
    locale: str = Field(default="ko-KR", max_length=40)
    goal_text: str = Field(min_length=1, max_length=500)
    operation_mode: UniversalNavigationOperationMode = "guide"
    screen: UniversalNavigationScreen
    transition: UniversalNavigationTransition | None = None
    client_timing: UniversalNavigationClientTiming | None = None


class UniversalNavigationCandidate(BaseModel):
    element_id: str
    element_key: str
    label: str
    role: str
    risk_level: UniversalNavigationRisk
    risk_reason: str | None = None


class UniversalNavigationRecommendation(BaseModel):
    recommendation_id: str = Field(pattern=r"^ur_[a-f0-9]{16}$")
    selected_element_id: str | None = None
    selected_element_key: str | None = None
    selected_label: str | None = None
    target_function: str
    instruction: str
    reason: str
    expected_next_screen: str
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: UniversalNavigationRisk
    requires_user_confirmation: bool


class UniversalNavigationGraphUpdate(BaseModel):
    screen_created: bool
    actions_created: int = Field(ge=0)
    transition_recorded: bool
    known_screen_count: int = Field(ge=0)
    known_transition_count: int = Field(ge=0)


class UniversalNavigationAutomation(BaseModel):
    action: UniversalNavigationAutomationAction = "none"
    safe_to_execute: bool = False
    selected_element_id: str | None = None
    selected_element_key: str | None = None
    selected_label: str | None = None
    reason: str = ""
    action_count: int = Field(default=0, ge=0)
    action_limit: int = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0.0, ge=0.0)
    timeout_seconds: int = Field(default=0, ge=0)


class UniversalNavigationRouteStep(BaseModel):
    ordinal: int = Field(ge=0)
    kind: Literal["click", "back"] = "click"
    from_screen_fingerprint: str
    element_key: str
    label: str
    function_ids: list[str] = Field(default_factory=list)
    role: str = Field(default="", max_length=80)
    risk_level: UniversalNavigationRisk = "low"
    expected_to_screen_fingerprint: str | None = None
    terminal: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class UniversalNavigationDiscoveredRoute(BaseModel):
    route_id: str
    target_function: str
    start_screen_fingerprint: str
    destination_screen_fingerprint: str
    provisional: bool = True
    lifecycle_status: UniversalNavigationRouteLifecycle = "shadow"
    steps: list[UniversalNavigationRouteStep] = Field(default_factory=list)


class UniversalNavigationPerformance(BaseModel):
    stage_ordinal: int = Field(ge=0)
    measurement_source: UniversalNavigationMeasurementSource
    server_total_ms: float = Field(ge=0.0)
    model_decision_ms: float = Field(ge=0.0)
    db_lookup_ms: float = Field(ge=0.0)
    screen_analysis_ms: float = Field(ge=0.0)
    screen_capture_ms: float = Field(ge=0.0)
    action_execution_ms: float = Field(ge=0.0)
    ui_settle_ms: float = Field(ge=0.0)
    external_wait_ms: float = Field(ge=0.0)
    time_to_confirmed_destination_ms: float | None = Field(default=None, ge=0.0)
    route_reused: bool = False
    route_rank: int | None = Field(default=None, ge=1)
    executed_transition_outcome: UniversalNavigationTransitionOutcome | None = None
    wrong_guidance_delta: int = Field(default=0, ge=0, le=1)
    wrong_click_delta: int = Field(default=0, ge=0, le=1)
    failure_reason: str | None = Field(
        default=None,
        max_length=80,
        pattern=r"^[a-z0-9_]+$",
    )


class UniversalNavigationCompletionTiming(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)
    time_to_confirmed_destination_ms: float = Field(gt=0.0, le=3_600_000.0)
    measurement_source: Literal["real_device"] = "real_device"


NavigationGoldRecordingStatus = Literal[
    "recording",
    "review_pending",
    "human_gold",
    "rejected",
    "cancelled",
]


class NavigationGoldRecordingCompleteRequest(BaseModel):
    destination_correct: bool = True
    safe_stop: bool = True
    reviewer: str = Field(default="device_user", min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class NavigationGoldRecordingReviewRequest(BaseModel):
    decision: Literal["human_gold", "rejected"]
    reviewer: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class NavigationGoldRecordingResponse(BaseModel):
    recording_id: str
    status: NavigationGoldRecordingStatus
    app_package: str
    app_version: str
    locale: str
    goal_text: str
    target_function: str
    step_count: int = Field(ge=0)
    selected_step_count: int = Field(ge=0)
    destination_screen_fingerprint: str | None = None
    destination_correct: bool | None = None
    safe_stop: bool | None = None
    reviewer: str | None = None
    review_notes: str | None = None


class UniversalNavigationObserveResponse(BaseModel):
    request_id: str
    session_id: str
    status: UniversalNavigationStatus
    screen_fingerprint: str = Field(pattern=r"^us_[a-f0-9]{16}$")
    goal_interpretation: str
    decision_mode: UniversalNavigationDecisionMode
    phase: UniversalNavigationPhase = "guide"
    candidates: list[UniversalNavigationCandidate] = Field(default_factory=list)
    recommendation: UniversalNavigationRecommendation | None = None
    graph_update: UniversalNavigationGraphUpdate
    automation: UniversalNavigationAutomation = Field(default_factory=UniversalNavigationAutomation)
    discovered_route: UniversalNavigationDiscoveredRoute | None = None
    performance: UniversalNavigationPerformance | None = None
    failure_reason: str | None = Field(
        default=None,
        max_length=80,
        pattern=r"^[a-z0-9_]+$",
    )
    warnings: list[str] = Field(default_factory=list)


class NavigationFunctionCatalogResponse(BaseModel):
    catalog_version: str
    catalog_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    function_count: int = Field(ge=0)
    alias_count: int = Field(ge=0)
    context_count: int = Field(ge=0)
    intent_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    functions: list[dict[str, object]] = Field(default_factory=list)


class UniversalNavigationGraphScreen(BaseModel):
    screen_fingerprint: str
    activity_name: str
    title: str
    seen_count: int


class UniversalNavigationGraphTransition(BaseModel):
    from_screen_fingerprint: str
    element_key: str
    label: str
    to_screen_fingerprint: str
    success_count: int
    failure_count: int


class UniversalNavigationGraphResponse(BaseModel):
    app_package: str
    screen_count: int
    action_count: int
    transition_count: int
    screens: list[UniversalNavigationGraphScreen]
    transitions: list[UniversalNavigationGraphTransition]
