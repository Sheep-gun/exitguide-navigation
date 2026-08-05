from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


JsonObject = dict[str, Any]


class ExtensionMode(str, Enum):
    OFF = "off"
    SHADOW = "shadow"
    ENFORCE = "enforce"


class PolicyVerdict(str, Enum):
    ALLOW = "allow"
    REOBSERVE = "reobserve"
    REQUIRE_CONFIRMATION = "require_confirmation"
    BLOCK = "block"


@dataclass(frozen=True)
class ProcedureStep:
    ordinal: int
    immediate_subgoal: str
    expected_concept_id: str | None
    preferred_role_id: str | None
    transition_id: str | None
    preconditions: tuple[JsonObject, ...]
    completion_check: JsonObject
    fallback_policy: JsonObject


@dataclass(frozen=True)
class ProcedureDefinition:
    procedure_id: str
    primary_goal_id: str
    compatible_goal_ids: tuple[str, ...]
    capability_id: str | None
    app_package: str | None
    compatible_app_versions: tuple[str, ...]
    locales: tuple[str, ...]
    execution_mode: str
    validation_count: int
    fast_path_min_validation_count: int
    name: str
    description: str
    parameter_schema: JsonObject
    default_parameters: JsonObject
    entry_conditions: tuple[JsonObject, ...]
    completion_conditions: tuple[JsonObject, ...]
    steps: tuple[ProcedureStep, ...]
    confidence: float
    status: str
    generation_id: str


@dataclass(frozen=True)
class ProcedureSelection:
    procedure: ProcedureDefinition
    parameters: JsonObject
    score: float
    reason: str


@dataclass(frozen=True)
class ProcedureHint:
    invocation_id: str
    procedure_id: str
    generation_id: str
    step_ordinal: int
    immediate_subgoal: str
    expected_concept_id: str | None
    preferred_role_id: str | None
    completion_check: JsonObject
    fallback_policy: JsonObject
    parameters: JsonObject
    enforced: bool
    fast_path_eligible: bool
    fast_path_reason: str


@dataclass(frozen=True)
class ProcedureObservation:
    invocation_id: str
    procedure_id: str
    previous_step_ordinal: int
    current_step_ordinal: int
    step_completed: bool
    procedure_completed: bool
    reason: str


@dataclass(frozen=True)
class PolicyDecision:
    verdict: PolicyVerdict
    policy_version: str
    rule_ids: tuple[str, ...]
    reason: str
    planner_action: JsonObject
    proposed_action: JsonObject
    grounded_action: JsonObject
    final_action: JsonObject
    facts: JsonObject
    grounding_status: str = "unknown"
    grounding_reason: str = ""
    missing_facts: tuple[str, ...] = ()
    obligations: tuple[str, ...] = ()
    confirmation_id: str | None = None
    latency_ms: float = 0.0
    shadow: bool = False


@dataclass(frozen=True)
class ExtensionDecision:
    procedure_hint: ProcedureHint | None
    policy_decision: PolicyDecision | None
    final_action: JsonObject


@dataclass(frozen=True)
class TaskAttempt:
    task_run_id: str
    task_case_id: str
    session_id: str
    attempt_index: int
    memory_profile: str
    procedure_profile: str
    verifier_profile: str
    app_package: str
    app_version: str
    goal_id: str
    started_at: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
