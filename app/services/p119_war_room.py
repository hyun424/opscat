"""Hash-chained, redacted P119 local war-room timeline and read model."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p118_operation_contract import exact_zero_authority_counters

_SENSITIVE_KEY = re.compile(r"(password|secret|credential|token|command|shell|subprocess|connector_payload)", re.I)
_SENSITIVE_TEXT = re.compile(r"(prod(?:uction)?|staging|https?://|kubectl|ssh|curl|password|secret|credential)", re.I)


@dataclass
class P119WarRoomTimeline:
    incident_id: str
    events: list[dict[str, Any]] = field(default_factory=list)

    def append(self, event_type: str, payload: Mapping[str, Any], *, timestamp: int) -> dict[str, Any]:
        safe_payload, redaction_count = redact_p119_payload(payload)
        previous_hash = str(self.events[-1]["event_hash"]) if self.events else ""
        event: dict[str, Any] = {
            "incident_id": self.incident_id,
            "sequence": len(self.events),
            "timestamp": timestamp,
            "event_type": event_type,
            "payload": safe_payload,
            "redaction_count": redaction_count,
            "previous_hash": previous_hash,
            "authority_counter_snapshot": exact_zero_authority_counters(),
        }
        event["event_hash"] = stable_hash(event)
        self.events.append(event)
        return event

    def verify(self) -> bool:
        previous = ""
        for index, event in enumerate(self.events):
            if event.get("sequence") != index or event.get("previous_hash") != previous:
                return False
            claimed = event.get("event_hash")
            if claimed != stable_hash({key: value for key, value in event.items() if key != "event_hash"}):
                return False
            previous = str(claimed)
        return True

    def read_model(self) -> dict[str, Any]:
        if not self.verify():
            raise ValueError("timeline_hash_mismatch")
        latest: dict[str, Any] = {}
        for event in self.events:
            latest.update(_mapping(event.get("payload")))
        return {
            "incident_id": self.incident_id,
            "event_count": len(self.events),
            "current": latest,
            "timeline_hash": str(self.events[-1]["event_hash"]) if self.events else stable_hash([]),
            "replay_refs": [str(_mapping(event.get("payload")).get("replay_ref")) for event in self.events if _mapping(event.get("payload")).get("replay_ref")],
            "authority_counter_snapshot": exact_zero_authority_counters(),
        }


def build_p119_escalation(
    *,
    incident_id: str,
    missing_evidence: Sequence[str],
    contradictions: Sequence[str],
    risk: str,
    validation_status: str,
    rollback_status: str,
    budget_snapshot: Mapping[str, int],
    timeline_ref: str,
    replay_ref: str,
) -> dict[str, Any]:
    payload, redactions = redact_p119_payload(
        {
            "incident_id": incident_id,
            "missing_evidence": list(missing_evidence),
            "contradictions": list(contradictions),
            "risk": risk,
            "validation_status": validation_status,
            "rollback_status": rollback_status,
            "budget_snapshot": dict(budget_snapshot),
            "timeline_ref": timeline_ref,
            "replay_ref": replay_ref,
        }
    )
    payload["redaction_count"] = redactions
    payload["authority_counter_snapshot"] = exact_zero_authority_counters()
    payload["escalation_hash"] = stable_hash(payload)
    return payload


def redact_p119_payload(value: Any) -> tuple[Any, int]:
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        count = 0
        for key, item in value.items():
            if _SENSITIVE_KEY.search(str(key)):
                output[str(key)] = "[REDACTED]"
                count += 1
            else:
                output[str(key)], nested = redact_p119_payload(item)
                count += nested
        return output, count
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        output_list: list[Any] = []
        count = 0
        for item in value:
            safe, nested = redact_p119_payload(item)
            output_list.append(safe)
            count += nested
        return output_list, count
    if isinstance(value, str) and _SENSITIVE_TEXT.search(value):
        return "[REDACTED]", 1
    return value, 0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = ["P119WarRoomTimeline", "build_p119_escalation", "redact_p119_payload"]
