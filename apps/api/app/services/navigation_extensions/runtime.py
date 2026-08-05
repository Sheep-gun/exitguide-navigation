from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evaluation_store import NavigationEvaluationStore
from .models import (
    ExtensionMode,
    PolicyDecision,
    PolicyVerdict,
    ProcedureHint,
    ProcedureObservation,
)
from .policy_verifier import LogicPolicyVerifier
from .predicates import PredicateError, all_conditions, evaluate_predicate
from .procedure_catalog import ProcedureCatalog
from .procedure_catalog import procedure_fast_path_eligibility


class NavigationExtensionRuntime:
    """Feature-flagged facade for N100 runtime hooks.

    OFF leaves the base runtime untouched. SHADOW records hypothetical results.
    ENFORCE applies procedure hints and policy action replacement.
    """

    def __init__(
        self,
        *,
        mode: ExtensionMode | str,
        catalog: ProcedureCatalog,
        verifier: LogicPolicyVerifier,
        store: NavigationEvaluationStore,
    ) -> None:
        self.mode = ExtensionMode(mode)
        self.catalog = catalog
        self.verifier = verifier
        self.store = store

    @classmethod
    def from_paths(
        cls,
        *,
        mode: ExtensionMode | str,
        procedure_catalog_path: str | Path,
        policy_path: str | Path,
        extension_db_path: str | Path,
    ) -> "NavigationExtensionRuntime":
        return cls(
            mode=mode,
            catalog=ProcedureCatalog(procedure_catalog_path),
            verifier=LogicPolicyVerifier(policy_path),
            store=NavigationEvaluationStore(extension_db_path),
        )

    def prepare_decision(
        self,
        *,
        session_id: str,
        goal_id: str | None,
        app_package: str,
        app_version: str = "",
        locale: str = "ko-KR",
        facts: Mapping[str, Any],
        parameters: Mapping[str, Any] | None = None,
    ) -> ProcedureHint | None:
        if self.mode == ExtensionMode.OFF or not goal_id:
            return None
        active = self.store.active_procedure(session_id)
        if active is None:
            statuses = (
                ("active", "validated", "draft")
                if self.mode == ExtensionMode.SHADOW
                else ("active",)
            )
            selection = self.catalog.select(
                goal_id=goal_id,
                app_package=app_package,
                app_version=app_version,
                locale=locale,
                facts=facts,
                parameters=parameters,
                statuses=statuses,
            )
            if selection is None:
                return None
            invocation_id = self.store.begin_procedure(
                session_id=session_id,
                selection=selection,
                facts=facts,
            )
            procedure = selection.procedure
            step_ordinal = 0
            bound_parameters = selection.parameters
        else:
            invocation_id = str(active["invocation_id"])
            procedure = self.catalog.get(str(active["procedure_id"]))
            step_ordinal = int(active["current_step_ordinal"])
            bound_parameters = dict(active["bound_parameters"])
        if step_ordinal >= len(procedure.steps):
            return None
        step = procedure.steps[step_ordinal]
        preferred_role_id = _preferred_role(step.preferred_role_id, step.fallback_policy, bound_parameters)
        fast_path_eligible, fast_path_reason = procedure_fast_path_eligibility(
            procedure,
            app_package=app_package,
            app_version=app_version,
            locale=locale,
        )
        return ProcedureHint(
            invocation_id=invocation_id,
            procedure_id=procedure.procedure_id,
            generation_id=procedure.generation_id,
            step_ordinal=step.ordinal,
            immediate_subgoal=_render_subgoal(step.immediate_subgoal, bound_parameters),
            expected_concept_id=step.expected_concept_id,
            preferred_role_id=preferred_role_id,
            completion_check=step.completion_check,
            fallback_policy=step.fallback_policy,
            parameters=bound_parameters,
            enforced=self.mode == ExtensionMode.ENFORCE,
            fast_path_eligible=(
                self.mode == ExtensionMode.ENFORCE and fast_path_eligible
            ),
            fast_path_reason=fast_path_reason,
        )

    def observe_procedure(
        self,
        *,
        session_id: str,
        decision_id: str | None,
        observation_id: str | None,
        facts: Mapping[str, Any],
    ) -> ProcedureObservation | None:
        if self.mode == ExtensionMode.OFF:
            return None
        active = self.store.active_procedure(session_id)
        if active is None:
            return None
        procedure = self.catalog.get(str(active["procedure_id"]))
        previous = int(active["current_step_ordinal"])
        if previous >= len(procedure.steps):
            return None
        step = procedure.steps[previous]
        try:
            step_completed = bool(step.completion_check) and evaluate_predicate(
                _predicate_only(step.completion_check), facts
            )
        except PredicateError:
            step_completed = False
        current = previous
        event_type = "observed"
        reason = "procedure step completion predicate not satisfied"
        procedure_completed = False
        if step_completed:
            if previous + 1 < len(procedure.steps):
                current = previous + 1
                event_type = "advanced"
                reason = "procedure step completion predicate satisfied"
            else:
                try:
                    procedure_completed = not procedure.completion_conditions or all_conditions(
                        procedure.completion_conditions, facts
                    )
                except PredicateError:
                    procedure_completed = False
                if procedure_completed:
                    event_type = "completed"
                    reason = "final step and procedure completion predicates satisfied"
                else:
                    reason = "final step satisfied but procedure completion predicate is pending"
        self.store.record_procedure_observation(
            invocation_id=str(active["invocation_id"]),
            decision_id=decision_id,
            observation_id=observation_id,
            previous_step_ordinal=previous,
            current_step_ordinal=current,
            event_type=event_type,
            reason=reason,
            facts=facts,
        )
        return ProcedureObservation(
            invocation_id=str(active["invocation_id"]),
            procedure_id=procedure.procedure_id,
            previous_step_ordinal=previous,
            current_step_ordinal=current,
            step_completed=step_completed,
            procedure_completed=procedure_completed,
            reason=reason,
        )

    def verify_action(
        self,
        *,
        session_id: str,
        decision_id: str,
        proposed_action: Mapping[str, Any],
        facts: Mapping[str, Any],
        planner_action: Mapping[str, Any] | None = None,
        grounded_action: Mapping[str, Any] | None = None,
        grounding_status: str = "unknown",
        grounding_reason: str = "",
        confirmation_id: str | None = None,
        task_run_id: str | None = None,
    ) -> tuple[dict[str, Any], PolicyDecision | None]:
        action = dict(proposed_action)
        if self.mode == ExtensionMode.OFF:
            return action, None
        policy_facts = _deep_copy(facts)
        confirmation_valid = self.store.consume_confirmation(
            confirmation_id,
            session_id=session_id,
            action=action,
        )
        policy_facts.setdefault("confirmation", {})["valid"] = confirmation_valid
        decision = self.verifier.verify(
            proposed_action=action,
            facts=policy_facts,
            confirmation_id=confirmation_id if confirmation_valid else None,
        )
        decision = replace(
            decision,
            planner_action=dict(planner_action or action),
            grounded_action=dict(grounded_action or action),
            grounding_status=grounding_status,
            grounding_reason=grounding_reason,
        )
        if (
            self.mode == ExtensionMode.ENFORCE
            and decision.verdict == PolicyVerdict.REQUIRE_CONFIRMATION
            and not confirmation_valid
        ):
            challenge_id = self.store.create_confirmation_challenge(
                session_id=session_id,
                action=action,
            )
            decision = replace(decision, confirmation_id=challenge_id)
        grounded = dict(grounded_action or action)
        actual_action = (
            grounded
            if self.mode == ExtensionMode.SHADOW
            else _more_restrictive_action(grounded, decision.final_action)
        )
        if self.mode == ExtensionMode.SHADOW:
            decision = replace(decision, shadow=True)
        else:
            # The extension is an additional safety layer. It must never turn
            # a wait/stop selected by the existing grounding gate back into a
            # click merely because the logic policy returned ALLOW.
            decision = replace(decision, final_action=actual_action)
        self.store.record_verifier_decision(
            session_id=session_id,
            decision_id=decision_id,
            task_run_id=task_run_id,
            decision=decision,
            actual_action=actual_action,
        )
        return actual_action, decision
    def record_memory_retrievals(
        self,
        *,
        session_id: str,
        decision_id: str | None,
        task_run_id: str | None,
        rows: Sequence[Mapping[str, Any]],
    ) -> tuple[str, ...]:
        if self.mode != ExtensionMode.OFF:
            return self.store.record_memory_retrievals(
                session_id=session_id,
                decision_id=decision_id,
                task_run_id=task_run_id,
                rows=rows,
            )
        return ()


_ACTION_RESTRICTION_RANK = {
    "wait_and_observe": 1,
    "stop_for_user": 2,
}


def _more_restrictive_action(
    grounded_action: Mapping[str, Any],
    policy_action: Mapping[str, Any],
) -> dict[str, Any]:
    grounded = dict(grounded_action)
    policy = dict(policy_action)
    grounded_rank = _ACTION_RESTRICTION_RANK.get(str(grounded.get("name", "")), 0)
    policy_rank = _ACTION_RESTRICTION_RANK.get(str(policy.get("name", "")), 0)
    return policy if policy_rank > grounded_rank else grounded


def _render_subgoal(template: str, parameters: Mapping[str, Any]) -> str:
    rendered = template
    for name, value in parameters.items():
        rendered = rendered.replace("{" + name + "}", str(value))
    return rendered


def _preferred_role(
    default_role: str | None,
    fallback_policy: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> str | None:
    parameter_name = fallback_policy.get("preferred_role_parameter")
    role_mapping = fallback_policy.get("preferred_role_by_value")
    if isinstance(parameter_name, str) and isinstance(role_mapping, Mapping):
        parameter_value = parameters.get(parameter_name)
        mapped = role_mapping.get(str(parameter_value))
        if isinstance(mapped, str) and mapped:
            return mapped
    return default_role


def _predicate_only(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if "predicate" in value and isinstance(value["predicate"], Mapping):
        return value["predicate"]
    return value


def _deep_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            result[str(key)] = _deep_copy(item)
        elif isinstance(item, list):
            result[str(key)] = list(item)
        else:
            result[str(key)] = item
    return result
