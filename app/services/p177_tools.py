"""P177 bounded read-only evidence tool registry and budgets."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.services.p147_p152_contracts import stable_hash
from app.services.p176_evidence import SOURCE_CLASSES
from app.services.redaction import redact_value

TOOL_RESULT_SCHEMA_VERSION = "p177.tool_evidence_result.v1"
REGISTRY_SCHEMA_VERSION = "p177.read_only_tool_registry.v1"
_TEMPLATE_FIELD_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_FORBIDDEN_TEMPLATE_RE = re.compile(
    r"https?://|www\.|(?:^|\s)(kubectl|terraform|gcloud|aws|az|curl|bash|sh|python|rm|delete|restart|scale|apply|exec)\b",
    re.IGNORECASE,
)


class P177ToolError(ValueError):
    """Raised when P177 tool selection or budget accounting fails closed."""


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    source_class: str
    provider: str
    template: str
    freshness_bound_seconds: int
    max_calls: int

    def __post_init__(self) -> None:
        if not self.tool_id or not re.fullmatch(r"[a-z][a-z0-9_.-]*", self.tool_id):
            raise P177ToolError("invalid_tool_id")
        if self.source_class not in SOURCE_CLASSES:
            raise P177ToolError("unsupported_source_class")
        if self.provider != "p176_recorded":
            raise P177ToolError("provider_not_observed_read_only")
        if _FORBIDDEN_TEMPLATE_RE.search(self.template):
            if any(word in self.template.lower() for word in ("delete", "restart", "scale", "apply", "kubectl", "terraform", "gcloud", "aws", "az")):
                raise P177ToolError("mutating_tool_forbidden")
            raise P177ToolError("free_form_template_forbidden")
        fields = _TEMPLATE_FIELD_RE.findall(self.template)
        if not fields or len(fields) != len(set(fields)):
            raise P177ToolError("invalid_template")
        if self.freshness_bound_seconds <= 0 or self.max_calls <= 0:
            raise P177ToolError("invalid_tool_limits")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "source_class": self.source_class,
            "provider": self.provider,
            "template": self.template,
            "freshness_bound_seconds": self.freshness_bound_seconds,
            "max_calls": self.max_calls,
        }


@dataclass
class ToolBudget:
    max_queries: int
    max_tool_calls: int
    max_time_ms: int
    max_tokens: int
    queries_used: int = 0
    tool_calls_used: int = 0
    time_ms_used: int = 0
    tokens_used: int = 0
    exhausted: bool = False
    stop_reason: str | None = None

    def consume(self, *, elapsed_ms: int, tokens_used: int) -> None:
        if self.exhausted:
            raise P177ToolError("budget_exhausted")
        if min(self.max_queries, self.max_tool_calls, self.max_time_ms, self.max_tokens) <= 0:
            raise P177ToolError("invalid_budget")
        next_queries = self.queries_used + 1
        next_calls = self.tool_calls_used + 1
        next_time = self.time_ms_used + elapsed_ms
        next_tokens = self.tokens_used + tokens_used
        if next_queries > self.max_queries or next_calls > self.max_tool_calls or next_time > self.max_time_ms or next_tokens > self.max_tokens:
            self.exhausted = True
            self.stop_reason = "budget_exhausted"
            raise P177ToolError("budget_exhausted")
        self.queries_used = next_queries
        self.tool_calls_used = next_calls
        self.time_ms_used = next_time
        self.tokens_used = next_tokens
        if (
            self.queries_used == self.max_queries
            or self.tool_calls_used == self.max_tool_calls
            or self.time_ms_used == self.max_time_ms
            or self.tokens_used == self.max_tokens
        ):
            self.exhausted = True
            self.stop_reason = "budget_exhausted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_queries": self.max_queries,
            "max_tool_calls": self.max_tool_calls,
            "max_time_ms": self.max_time_ms,
            "max_tokens": self.max_tokens,
            "queries_used": self.queries_used,
            "tool_calls_used": self.tool_calls_used,
            "time_ms_used": self.time_ms_used,
            "tokens_used": self.tokens_used,
            "exhausted": self.exhausted,
            "stop_reason": self.stop_reason,
        }


class ToolRegistry:
    """Closed registry for observed P176 read tools."""

    def __init__(self, *, version: str, tools: Sequence[ToolSpec]) -> None:
        if not version:
            raise P177ToolError("missing_registry_version")
        if not tools:
            raise P177ToolError("empty_registry")
        self.version = version
        self._tools = {tool.tool_id: tool for tool in tools}
        if len(self._tools) != len(tools):
            raise P177ToolError("duplicate_tool")
        self._call_counts = {tool.tool_id: 0 for tool in tools}

    def execute(
        self,
        *,
        tool_id: str,
        params: Mapping[str, str],
        observed_at: str,
        received_at: str,
        content: Mapping[str, Any],
        budget: ToolBudget,
        elapsed_ms: int,
        tokens_used: int,
    ) -> dict[str, Any]:
        tool = self._tools.get(tool_id)
        if tool is None:
            raise P177ToolError("unknown_tool")
        if self._call_counts[tool_id] >= tool.max_calls:
            raise P177ToolError("tool_call_limit_exhausted")
        rendered_query = _render_template(tool.template, params)
        _validate_freshness(observed_at, received_at, tool.freshness_bound_seconds)
        budget.consume(elapsed_ms=elapsed_ms, tokens_used=tokens_used)
        self._call_counts[tool_id] += 1
        redacted_content = redact_value(deepcopy(dict(content)))
        evidence: dict[str, Any] = {
            "schema_version": TOOL_RESULT_SCHEMA_VERSION,
            "registry_version": self.version,
            "tool_id": tool.tool_id,
            "source_class": tool.source_class,
            "provider": tool.provider,
            "rendered_query_hash": stable_hash(rendered_query),
            "observed_at": observed_at,
            "received_at": received_at,
            "freshness_bound_seconds": tool.freshness_bound_seconds,
            "fresh": True,
            "read_only": True,
            "redaction_applied": True,
            "content_hash": stable_hash(redacted_content),
            "summary": redacted_content,
            "budget_after": budget.to_dict(),
        }
        evidence["evidence_id"] = stable_hash({key: value for key, value in evidence.items() if key != "evidence_id"})
        return evidence

    def tool_source_class(self, tool_id: str) -> str:
        tool = self._tools.get(tool_id)
        if tool is None:
            raise P177ToolError("unknown_tool")
        return tool.source_class

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "version": self.version,
            "tools": [self._tools[key].to_dict() for key in sorted(self._tools)],
        }
        payload["registry_hash"] = stable_hash(payload)
        return payload


def _render_template(template: str, params: Mapping[str, str]) -> str:
    fields = _TEMPLATE_FIELD_RE.findall(template)
    missing = [field for field in fields if field not in params or not params[field]]
    if missing:
        raise P177ToolError("missing_template_param")
    rendered = template
    for field in fields:
        value = str(params[field])
        if _FORBIDDEN_TEMPLATE_RE.search(value) or "/" in value or ":" in value:
            raise P177ToolError("free_form_param_forbidden")
        rendered = rendered.replace("{" + field + "}", value)
    return rendered


def _validate_freshness(observed_at: str, received_at: str, bound_seconds: int) -> None:
    observed = _timestamp(observed_at, "observed_at")
    received = _timestamp(received_at, "received_at")
    age = (received - observed).total_seconds()
    if age < 0:
        raise P177ToolError("future_observation")
    if age > bound_seconds:
        raise P177ToolError("stale_evidence")


def _timestamp(value: str, field: str) -> datetime:
    try:
        if not value.endswith("Z"):
            raise ValueError
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P177ToolError(f"invalid_{field}") from exc
