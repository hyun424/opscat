"""P10 incident judgment benchmark dataset schema.

This schema is intentionally dependency-light and local/mock only. It models
external-style logs/metrics as deterministic benchmark cases without downloading
or executing anything.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.services.redaction import redact_text, redact_value

ExpectedRoute = Literal["local_mock_auto_allowed", "approval_required", "human_required", "blocked"]
_ALLOWED_ROUTES = {"local_mock_auto_allowed", "approval_required", "human_required", "blocked"}


@dataclass(frozen=True)
class JudgmentRubric:
    expected_route: ExpectedRoute | str
    expected_hypotheses: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    verification_criteria: tuple[str, ...] = ()
    explanation_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.expected_route):
            raise ValueError("expected_route is required")
        if str(self.expected_route) not in _ALLOWED_ROUTES:
            raise ValueError(f"expected_route must be one of {sorted(_ALLOWED_ROUTES)}")
        for name in ("expected_hypotheses", "required_evidence", "forbidden_actions", "verification_criteria", "explanation_keywords"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_hypotheses": list(self.expected_hypotheses),
            "required_evidence": list(self.required_evidence),
            "forbidden_actions": list(self.forbidden_actions),
            "expected_route": str(self.expected_route),
            "verification_criteria": list(self.verification_criteria),
            "explanation_keywords": list(self.explanation_keywords),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> JudgmentRubric:
        return cls(
            expected_route=str(data.get("expected_route", "")),
            expected_hypotheses=_tuple(data.get("expected_hypotheses", ())),
            required_evidence=_tuple(data.get("required_evidence", ())),
            forbidden_actions=_tuple(data.get("forbidden_actions", ())),
            verification_criteria=_tuple(data.get("verification_criteria", ())),
            explanation_keywords=_tuple(data.get("explanation_keywords", ())),
        )


@dataclass(frozen=True)
class JudgmentCase:
    id: str
    title: str
    incident: Mapping[str, Any]
    evidence: Sequence[Mapping[str, Any]]
    rubric: JudgmentRubric
    source: str = "manual"
    signals: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    tags: tuple[str, ...] = ()
    local_mock_only: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id is required")
        object.__setattr__(self, "incident", dict(self.incident))
        object.__setattr__(self, "evidence", tuple(dict(item) for item in self.evidence))
        object.__setattr__(self, "signals", tuple(dict(item) for item in self.signals))
        object.__setattr__(self, "tags", _tuple(self.tags))

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "incident": dict(self.incident),
            "signals": [dict(item) for item in self.signals],
            "evidence": [dict(item) for item in self.evidence],
            "rubric": self.rubric.to_dict(),
            "tags": list(self.tags),
            "local_mock_only": self.local_mock_only,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> JudgmentCase:
        rubric_raw = data.get("rubric", {})
        if not isinstance(rubric_raw, Mapping):
            raise ValueError("rubric must be a mapping")
        incident = data.get("incident", {})
        evidence = data.get("evidence", [])
        signals = data.get("signals", [])
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            source=str(data.get("source", "manual")),
            incident=dict(incident) if isinstance(incident, Mapping) else {},
            signals=[dict(item) for item in signals if isinstance(item, Mapping)] if isinstance(signals, Sequence) and not isinstance(signals, (str, bytes, bytearray)) else [],
            evidence=[dict(item) for item in evidence if isinstance(item, Mapping)] if isinstance(evidence, Sequence) and not isinstance(evidence, (str, bytes, bytearray)) else [],
            rubric=JudgmentRubric.from_dict(rubric_raw),
            tags=_tuple(data.get("tags", ())),
        )


def load_judgment_cases(path: str | Path) -> list[JudgmentCase]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, Mapping):
        raw_cases = data.get("cases", [])
    else:
        raw_cases = data
    if not isinstance(raw_cases, Sequence) or isinstance(raw_cases, (str, bytes, bytearray)):
        raise ValueError("judgment case file must contain a list or {cases: [...]} mapping")
    return [JudgmentCase.from_dict(item) for item in raw_cases if isinstance(item, Mapping)]


def write_judgment_cases(path: str | Path, cases: Sequence[JudgmentCase]) -> None:
    payload = [case.to_dict() for case in sorted(cases, key=lambda item: item.id)]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if str(item))
    return (str(value),)


def normalized_text(value: Any) -> str:
    return redact_text(json.dumps(redact_value(value), sort_keys=True, default=str)).lower()
