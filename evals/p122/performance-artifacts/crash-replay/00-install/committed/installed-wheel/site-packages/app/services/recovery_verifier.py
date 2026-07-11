"""P9 recovery verifier v2 for local/mock post-action checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.services.redaction import redact_text, redact_value

RecoveryStatus = Literal["recovered", "partial_recovery", "false_recovery", "pending", "escalated"]
RecoveryRoute = Literal["report_recovered", "monitor_or_escalate", "escalate", "collect_more_evidence"]


@dataclass(frozen=True)
class RecoveryVerification:
    status: RecoveryStatus
    recovered: bool
    route: RecoveryRoute
    checks: tuple[dict[str, Any], ...]
    missing_checks: tuple[str, ...]
    blockers: tuple[str, ...]
    message: str
    local_mock_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "recovered": self.recovered,
            "route": self.route,
            "checks": [dict(check) for check in self.checks],
            "missing_checks": list(self.missing_checks),
            "blockers": list(self.blockers),
            "message": redact_text(self.message),
            "local_mock_only": self.local_mock_only,
        }


def verify_recovery(incident: Any, *, required_checks: Sequence[str] | None = None) -> RecoveryVerification:
    evidence = _evidence(incident)
    required = tuple(required_checks or ("metric", "log", "state"))
    checks = tuple(_check(kind, evidence) for kind in required)
    missing = tuple(check["kind"] for check in checks if check["status"] == "missing")
    blockers = tuple(sorted({str(reason) for check in checks for reason in check.get("blockers", [])}))
    statuses = {str(check["status"]) for check in checks}
    text = " ".join(str(_get(item, "content", "")) for item in evidence).lower()

    if blockers or any(marker in text for marker in ("false recovery", "still failing", "new errors continue", "degraded")):
        return RecoveryVerification("false_recovery", False, "escalate", checks, missing, blockers or ("negative_recovery_signal",), "Recovery claim contradicted by local/mock evidence.")
    if not evidence or len(missing) == len(required):
        return RecoveryVerification("pending", False, "collect_more_evidence", checks, missing, (), "Not enough local/mock evidence to verify recovery.")
    if "failed" in statuses or "partial" in statuses or missing:
        return RecoveryVerification("partial_recovery", False, "monitor_or_escalate", checks, missing, (), "Only partial local/mock recovery evidence is present.")
    return RecoveryVerification("recovered", True, "report_recovered", checks, (), (), "Metrics, logs, and state agree that recovery is complete.")


def _check(kind: str, evidence: list[Any]) -> dict[str, Any]:
    matching = [item for item in evidence if str(_get(item, "type", "")).lower() == kind or kind in str(_get(item, "content", "")).lower()]
    if not matching:
        return {"kind": kind, "status": "missing", "evidence_ids": [], "blockers": []}
    text = " ".join(str(_get(item, "content", "")) for item in matching).lower()
    ids = [str(_get(item, "id", "")) for item in matching]
    blockers: list[str] = []
    if any(token in text for token in ("still failing", "new errors continue", "errors continue", "degraded", "failed", "false recovery")):
        blockers.append(f"{kind}_negative_signal")
        status = "failed"
    elif "partial" in text:
        status = "partial"
    elif any(token in text for token in ("recovered", "healthy", "baseline", "no new errors", "ok")):
        status = "passed"
    else:
        status = "partial"
    return {"kind": kind, "status": status, "evidence_ids": ids, "blockers": blockers}


def _evidence(incident: Any) -> list[Any]:
    value = _get(incident, "evidence", [])
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(redact_value(value) if isinstance(value, list) else value)
    return []


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)
