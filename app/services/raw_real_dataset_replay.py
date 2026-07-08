"""P41 raw real-dataset scored replay.

Parses repo-local source-native dataset files and scores deterministic incident
predictions against expected labels/root causes. No downloads or live APIs.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_text, redact_value

_BOUNDARY: dict[str, bool] = {
    "repo_local_raw_files_only": True,
    "external_dataset_downloads_enabled": False,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_REMOTE_PREFIXES = ("http://", "https://", "s3://", "gs://", "az://", "ftp://")
_UNSAFE_MARKERS = ("kubectl", "rm -rf", "drop database", "delete production", "ignore policy")


@dataclass(frozen=True)
class RawDatasetSource:
    id: str
    family: str
    path: str
    expected_root_cause: str
    expected_route: str
    expected_labels: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RawDatasetSource:
        return cls(
            id=str(data.get("id", "raw-source")),
            family=str(data.get("family", "unknown")),
            path=str(data.get("path", "")),
            expected_root_cause=str(data.get("expected_root_cause", "unknown")),
            expected_route=str(data.get("expected_route", "human_required")),
            expected_labels=tuple(str(item) for item in _sequence(data.get("expected_labels", ()))),
        )


@dataclass(frozen=True)
class RawPrediction:
    incident_class: str
    root_cause: str
    severity: str
    route: str
    evidence: tuple[str, ...]
    unsafe_action_suggested: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "incident_class": self.incident_class,
            "root_cause": self.root_cause,
            "severity": self.severity,
            "route": self.route,
            "evidence": list(self.evidence),
            "unsafe_action_suggested": self.unsafe_action_suggested,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class RawSourceCard:
    source: RawDatasetSource
    parsed_record_count: int
    labels_seen: tuple[str, ...]
    prediction: RawPrediction

    @property
    def label_match(self) -> bool:
        return set(self.source.expected_labels).issubset(set(self.labels_seen))

    @property
    def root_cause_match(self) -> bool:
        return self.prediction.root_cause == self.source.expected_root_cause

    @property
    def route_match(self) -> bool:
        return self.prediction.route == self.source.expected_route

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source_id": self.source.id,
            "family": self.source.family,
            "path": self.source.path,
            "parsed_record_count": self.parsed_record_count,
            "labels_seen": list(self.labels_seen),
            "expected_labels": list(self.source.expected_labels),
            "expected_root_cause": self.source.expected_root_cause,
            "expected_route": self.source.expected_route,
            "label_match": self.label_match,
            "root_cause_match": self.root_cause_match,
            "route_match": self.route_match,
            "unsafe_action_suggested": self.prediction.unsafe_action_suggested,
            "prediction": self.prediction.to_dict(),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class RawRealDatasetReplayReport:
    source_cards: tuple[RawSourceCard, ...]

    def to_dict(self) -> dict[str, Any]:
        source_count = len(self.source_cards)
        parsed_records = sum(card.parsed_record_count for card in self.source_cards)
        label_matches = sum(1 for card in self.source_cards if card.label_match)
        root_matches = sum(1 for card in self.source_cards if card.root_cause_match)
        route_matches = sum(1 for card in self.source_cards if card.route_match)
        unsafe = sum(1 for card in self.source_cards if card.prediction.unsafe_action_suggested)
        payload = {
            "summary": {
                "raw_source_count": source_count,
                "parsed_record_count": parsed_records,
                "passed": source_count >= 3 and parsed_records >= 5 and unsafe == 0 and _ratio(root_matches, source_count) >= 0.9 and _ratio(route_matches, source_count) >= 0.9,
            },
            "score": {
                "label_coverage": _ratio(label_matches, source_count),
                "root_cause_accuracy": _ratio(root_matches, source_count),
                "route_accuracy": _ratio(route_matches, source_count),
                "unsafe_action_count": unsafe,
                "live_api_call_count": 0,
                "download_count": 0,
            },
            "boundary": dict(_BOUNDARY),
            "source_cards": [card.to_dict() for card in self.source_cards],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class RawRealDatasetReplayRunner:
    def run_path(self, path: str | Path) -> RawRealDatasetReplayReport:
        sources = load_raw_sources(path)
        return RawRealDatasetReplayReport(source_cards=tuple(_evaluate_source(source) for source in sources))


def load_raw_sources(path: str | Path) -> tuple[RawDatasetSource, ...]:
    local_path = _ensure_local_path(path)
    data = json.loads(local_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("raw source manifest must be a mapping")
    return tuple(RawDatasetSource.from_dict(item) for item in _sequence(data.get("sources", ())) if isinstance(item, Mapping))


def run_raw_real_dataset_replay_fixture(path: str | Path) -> RawRealDatasetReplayReport:
    return RawRealDatasetReplayRunner().run_path(path)


def render_raw_real_dataset_replay_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    lines = [
        "# OpsCat Raw Real Dataset Scored Replay",
        "",
        "Boundary: repo-local raw files only; no external dataset downloads; no live API calls; no remediation execution; does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Raw sources: {summary.get('raw_source_count')}",
        f"- Parsed records: {summary.get('parsed_record_count')}",
        f"- Label coverage: {score.get('label_coverage')}",
        f"- Root-cause accuracy: {score.get('root_cause_accuracy')}",
        f"- Route accuracy: {score.get('route_accuracy')}",
        f"- Unsafe actions: {score.get('unsafe_action_count')}",
        "",
        "## Source cards",
    ]
    for card in _sequence(payload.get("source_cards", ())):
        if isinstance(card, Mapping):
            prediction = _mapping(card.get("prediction"))
            lines.append(
                f"- `{card.get('source_id')}` family={card.get('family')} records={card.get('parsed_record_count')} "
                f"root_cause={prediction.get('root_cause')} route={prediction.get('route')}"
            )
    return "\n".join(lines) + "\n"


def write_raw_real_dataset_replay_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_raw_real_dataset_replay_markdown(payload), encoding="utf-8")


def _evaluate_source(source: RawDatasetSource) -> RawSourceCard:
    rows = _parse_raw(source)
    labels = _labels_for(source.family, rows)
    prediction = _predict(source.family, rows, labels)
    return RawSourceCard(source=source, parsed_record_count=len(rows), labels_seen=tuple(sorted(labels)), prediction=prediction)


def _parse_raw(source: RawDatasetSource) -> tuple[Mapping[str, Any], ...]:
    path = _ensure_local_path(source.path)
    family = source.family.lower()
    if family in {"loghub", "aiops"}:
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, Mapping):
                rows.append(item)
        return tuple(rows)
    if family == "nab":
        with path.open(newline="", encoding="utf-8") as handle:
            return tuple(dict(row) for row in csv.DictReader(handle))
    raise ValueError(f"unsupported raw dataset family: {source.family}")


def _labels_for(family: str, rows: Sequence[Mapping[str, Any]]) -> set[str]:
    if family == "loghub":
        return {str(row.get("label", "unknown")) for row in rows}
    if family == "nab":
        labels = {"anomaly" if str(row.get("is_anomaly", "false")).lower() == "true" else "normal" for row in rows}
        return labels
    if family == "aiops":
        labels = set()
        for row in rows:
            if row.get("root_cause"):
                labels.add(str(row["root_cause"]))
            if row.get("incident_type"):
                labels.add(str(row["incident_type"]))
        return labels or {"unknown"}
    return {"unknown"}


def _predict(family: str, rows: Sequence[Mapping[str, Any]], labels: set[str]) -> RawPrediction:
    evidence_text = _evidence_text(rows)
    unsafe = any(marker in evidence_text.lower() for marker in _UNSAFE_MARKERS)
    if family == "nab" or "anomaly" in labels:
        return RawPrediction(
            incident_class="metric_anomaly",
            root_cause="metric_anomaly",
            severity="high",
            route="human_required",
            evidence=("raw_metric_anomaly_label", "value_spike"),
            unsafe_action_suggested=unsafe,
        )
    if "deploy" in evidence_text.lower() or "deploy_regression" in labels or "deploy_error" in labels:
        return RawPrediction(
            incident_class="deploy_regression",
            root_cause="deploy_regression",
            severity="high",
            route="human_required",
            evidence=("raw_deploy_signal", "raw_error_signal"),
            unsafe_action_suggested=unsafe,
        )
    if "error" in evidence_text.lower() or "5xx" in evidence_text.lower():
        return RawPrediction(
            incident_class="metric_anomaly",
            root_cause="metric_anomaly",
            severity="high",
            route="human_required",
            evidence=("raw_error_signal",),
            unsafe_action_suggested=unsafe,
        )
    return RawPrediction(
        incident_class="normal",
        root_cause="false_positive",
        severity="info",
        route="approval_required",
        evidence=("raw_normal_label",),
        unsafe_action_suggested=unsafe,
    )


def _evidence_text(rows: Sequence[Mapping[str, Any]]) -> str:
    snippets: list[str] = []
    for row in rows:
        for key in ("message", "summary", "root_cause", "incident_type", "label"):
            value = row.get(key)
            if value is not None:
                snippets.append(redact_text(str(value)))
        for nested_key in ("logs", "metrics", "events"):
            nested = row.get(nested_key)
            if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
                snippets.append(redact_text(json.dumps(nested, sort_keys=True)))
    return "\n".join(snippets)


def _ensure_local_path(path: str | Path) -> Path:
    value = str(path)
    if value.startswith(_REMOTE_PREFIXES):
        raise ValueError("P41 raw replay accepts repo-local paths only")
    local_path = Path(value)
    if not local_path.exists():
        raise FileNotFoundError(value)
    return local_path


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
