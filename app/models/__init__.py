"""Domain model exports.

Keep exports lazy so policy/risk modules can import action dataclasses without
requiring every persistence model to be importable during lightweight checks.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "ActionProposal": ("app.models.action", "ActionProposal"),
    "ActionExecutionResult": ("app.models.action", "ActionExecutionResult"),
    "ActionMetadata": ("app.models.action", "ActionMetadata"),
    "ActionProposal": ("app.models.action", "ActionProposal"),
    "ActionRequest": ("app.models.action", "ActionRequest"),
    "ActionStatus": ("app.models.action", "ActionStatus"),
    "ApprovalRecord": ("app.models.action", "ApprovalRecord"),
    "PolicyDecision": ("app.models.action", "PolicyDecision"),
    "PolicyEvaluation": ("app.models.action", "PolicyEvaluation"),
    "RiskLevel": ("app.models.action", "RiskLevel"),
    "ApprovalDecision": ("app.models.policy", "ApprovalDecision"),
    "Evidence": ("app.models.evidence", "Evidence"),
    "Incident": ("app.models.incident", "Incident"),
    "TimelineEvent": ("app.models.timeline", "TimelineEvent"),
}

__all__ = sorted(_EXPORTS)


def _load_persistence_models() -> None:
    # SQLAlchemy relationship strings require all mapped classes to be imported
    # before mapper configuration. Keep this centralized while preserving lazy
    # exports for lightweight policy modules.
    for module_name in (
        "app.models.action",
        "app.models.evidence",
        "app.models.incident",
        "app.models.policy",
        "app.models.timeline",
    ):
        import_module(module_name)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name in {"ActionProposal", "ApprovalDecision", "Evidence", "Incident", "TimelineEvent"}:
        _load_persistence_models()
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
