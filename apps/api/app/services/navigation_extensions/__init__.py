"""Drop-in procedure, policy verification, and evaluation extensions.

The package has no dependency on the live Navigation API models.  The N100
adapter converts the existing Pydantic models into these stable dataclasses.
"""

from .evaluation_store import NavigationEvaluationStore
from .models import (
    ExtensionMode,
    PolicyDecision,
    PolicyVerdict,
    ProcedureHint,
    ProcedureObservation,
    ProcedureSelection,
)
from .policy_verifier import LogicPolicyVerifier
from .procedure_catalog import ProcedureCatalog, build_procedure_catalog
from .runtime import NavigationExtensionRuntime

__all__ = [
    "ExtensionMode",
    "LogicPolicyVerifier",
    "NavigationEvaluationStore",
    "NavigationExtensionRuntime",
    "PolicyDecision",
    "PolicyVerdict",
    "ProcedureCatalog",
    "ProcedureHint",
    "ProcedureObservation",
    "ProcedureSelection",
    "build_procedure_catalog",
]
