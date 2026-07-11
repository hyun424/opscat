"""P47 safe read-only tool selection planner."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "read_only_tool_planning": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_BLOCKED_MARKERS = ("rollback", "restart", "delete", "shell", "write", "mutate", "scale", "kill")


@dataclass(frozen=True)
class ToolSelectionPlannerReport:
    cases: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        selected = [tool for case in self.cases for tool in case["selected_tools"]]
        blocked = [tool for case in self.cases for tool in case["blocked_tools"]]
        unsafe_selected = [tool for tool in selected if tool["mode"] != "read_only"]
        payload = {
            "summary": {
                "case_count": len(self.cases),
                "selected_tool_count": len(selected),
                "blocked_tool_count": len(blocked),
                "unsafe_selected_count": len(unsafe_selected),
                "read_only_ratio": _ratio(len(selected) - len(unsafe_selected), len(selected)),
                "passed": bool(self.cases) and selected and not unsafe_selected,
            },
            "boundary": dict(_BOUNDARY),
            "cases": list(self.cases),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_tool_selection_planner_report(cases_path: str | Path) -> ToolSelectionPlannerReport:
    cases = _load_cases(cases_path)
    return ToolSelectionPlannerReport(tuple(_plan_case(case) for case in cases))


def render_tool_selection_planner_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Tool Selection Planner",
        "",
        "Maps investigation needs to safe read-only observability tools and blocks unsafe tools.",
        "",
        "## Summary",
        f"- Cases: {summary.get('case_count')}",
        f"- Selected tools: {summary.get('selected_tool_count')}",
        f"- Blocked tools: {summary.get('blocked_tool_count')}",
        f"- Unsafe selected: {summary.get('unsafe_selected_count')}",
        f"- Read-only ratio: {summary.get('read_only_ratio')}",
        "",
        "## Plans",
    ]
    for case in _sequence(payload.get("cases", ())):
        if isinstance(case, Mapping):
            lines.append(f"- `{case.get('case_id')}` hypothesis={case.get('hypothesis')}")
            lines.append("  - Selected: " + ", ".join(str(tool.get("tool")) for tool in _sequence(case.get("selected_tools", ()))))
    lines.extend(["", "## Blocked tools"])
    for case in _sequence(payload.get("cases", ())):
        if isinstance(case, Mapping):
            for tool in _sequence(case.get("blocked_tools", ())):
                if isinstance(tool, Mapping):
                    lines.append(f"- `{case.get('case_id')}` blocked `{tool.get('request')}` reason={tool.get('reason')}")
    return "\n".join(lines) + "\n"


def write_tool_selection_planner_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_tool_selection_planner_markdown(payload), encoding="utf-8")


def _load_cases(path: str | Path) -> tuple[Mapping[str, Any], ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("P47 cases must be a mapping")
    return tuple(item for item in _sequence(data.get("cases", ())) if isinstance(item, Mapping))


def _plan_case(case: Mapping[str, Any]) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    evidence_refs = list(str(item) for item in _sequence(case.get("evidence_refs", ())))
    for request in _sequence(case.get("next_investigations", ())):
        request_text = str(request)
        if _is_blocked(request_text):
            blocked.append({"request": request_text, "reason": _block_reason(request_text), "route": "blocked"})
        else:
            selected.append(_tool_for_request(request_text, str(case.get("hypothesis", "unknown")), evidence_refs))
    if not selected:
        selected.append(
            {
                "request": "collect safe read-only evidence after blocked tool request",
                "tool": "logs.search_read_only",
                "mode": "read_only",
                "hypothesis": str(case.get("hypothesis", "unknown")),
                "evidence_refs": evidence_refs,
                "approval_required": False,
            }
        )
    return {
        "case_id": str(case.get("id", "p47-case")),
        "hypothesis": str(case.get("hypothesis", "unknown")),
        "confidence": float(case.get("confidence", 0.0)),
        "selected_tools": selected,
        "blocked_tools": blocked,
        "approval_required": bool(blocked) or float(case.get("confidence", 0.0)) < 0.65,
    }


def _is_blocked(request: str) -> bool:
    lowered = request.lower()
    return any(marker in lowered for marker in _BLOCKED_MARKERS)


def _block_reason(request: str) -> str:
    lowered = request.lower()
    for marker in _BLOCKED_MARKERS:
        if marker in lowered:
            return f"{marker} is not an allowed read-only investigation tool"
    return "not read-only"


def _tool_for_request(request: str, hypothesis: str, evidence_refs: Sequence[str]) -> dict[str, Any]:
    lowered = request.lower()
    if "pod" in lowered or "grafana" in lowered or "error" in lowered:
        tool = "grafana.query_range"
    elif "deploy" in lowered or "diff" in lowered:
        tool = "deploy.read_metadata"
    elif "db" in lowered or "pool" in lowered or "query" in lowered or "lock" in lowered:
        tool = "datadog.read_metric"
    elif "provider" in lowered or "dependency" in lowered:
        tool = "sentry.read_issues"
    else:
        tool = "logs.search_read_only"
    return {
        "request": request,
        "tool": tool,
        "mode": "read_only",
        "hypothesis": hypothesis,
        "evidence_refs": list(evidence_refs),
        "approval_required": False,
    }


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)
