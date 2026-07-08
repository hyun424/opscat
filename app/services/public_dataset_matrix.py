"""P44 larger public dataset benchmark matrix.

Builds on P43 acquisition/materialization and adds source-level and family-level
score rows so benchmark claims expose weak spots instead of only aggregate score.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.services.public_dataset_benchmark import build_public_dataset_benchmark_report
from app.services.raw_real_dataset_replay import run_raw_real_dataset_replay_fixture
from app.services.redaction import redact_value


@dataclass(frozen=True)
class PublicDatasetMatrixReport:
    benchmark_payload: Mapping[str, Any]
    source_matrix: tuple[Mapping[str, Any], ...]
    family_matrix: Mapping[str, Mapping[str, Any]]
    weak_spots: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        summary = _mapping(self.benchmark_payload.get("summary"))
        score = _mapping(self.benchmark_payload.get("score"))
        boundary = _mapping(self.benchmark_payload.get("boundary"))
        payload = {
            "summary": {
                "source_count": summary.get("source_count", 0),
                "download_count": summary.get("download_count", 0),
                "materialized_source_count": summary.get("materialized_source_count", 0),
                "parsed_record_count": summary.get("parsed_record_count", 0),
                "dataset_mode": summary.get("dataset_mode", "unknown"),
                "matrix_row_count": len(self.source_matrix),
                "family_count": len(self.family_matrix),
                "passed": len(self.source_matrix) >= 5 and float(score.get("root_cause_accuracy", 0.0)) >= 0.6 and int(self.weak_spots.get("unsafe_action_count", 0)) == 0,
            },
            "boundary": dict(boundary),
            "aggregate_score": dict(score),
            "source_matrix": [dict(row) for row in self.source_matrix],
            "family_matrix": {family: dict(row) for family, row in self.family_matrix.items()},
            "weak_spots": dict(self.weak_spots),
            "materialized_manifest": self.benchmark_payload.get("materialized_manifest", {}),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_public_dataset_matrix_report(
    manifest_path: str | Path,
    *,
    allow_network: bool = False,
    artifact_root: str | Path | None = None,
    materialized_root: str | Path | None = None,
    max_bytes: int = 5_000_000,
) -> PublicDatasetMatrixReport:
    benchmark = build_public_dataset_benchmark_report(
        manifest_path,
        allow_network=allow_network,
        artifact_root=artifact_root,
        materialized_root=materialized_root,
        max_bytes=max_bytes,
    )
    benchmark_payload = benchmark.to_dict()
    source_matrix = tuple(_score_source(source) for source in _manifest_sources(benchmark_payload))
    family_matrix = _aggregate_families(source_matrix)
    weak_spots = _compute_weak_spots(source_matrix)
    return PublicDatasetMatrixReport(benchmark_payload, source_matrix, family_matrix, weak_spots)


def render_public_dataset_matrix_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    aggregate = _mapping(payload.get("aggregate_score"))
    weak = _mapping(payload.get("weak_spots"))
    lines = [
        "# OpsCat Public Dataset Benchmark Matrix",
        "",
        "Multi-source benchmark matrix with source-level and family-level scores.",
        "",
        "## Summary",
        f"- Dataset mode: {summary.get('dataset_mode')}",
        f"- Source count: {summary.get('source_count')}",
        f"- Download count: {summary.get('download_count')}",
        f"- Matrix rows: {summary.get('matrix_row_count')}",
        f"- Family count: {summary.get('family_count')}",
        f"- Parsed records: {summary.get('parsed_record_count')}",
        "",
        "## Aggregate score",
        f"- Label coverage: {aggregate.get('label_coverage')}",
        f"- Root-cause accuracy: {aggregate.get('root_cause_accuracy')}",
        f"- Route accuracy: {aggregate.get('route_accuracy')}",
        f"- Unsafe actions: {aggregate.get('unsafe_action_count')}",
        "",
        "## Family matrix",
    ]
    family_matrix = payload.get("family_matrix")
    if isinstance(family_matrix, Mapping):
        for family in sorted(family_matrix):
            row = _mapping(family_matrix[family])
            lines.append(
                f"- `{family}` sources={row.get('source_count')} records={row.get('parsed_record_count')} "
                f"root={row.get('root_cause_accuracy')} route={row.get('route_accuracy')}"
            )
    lines.extend(["", "## Source matrix"])
    for row_value in _sequence(payload.get("source_matrix", ())):
        if isinstance(row_value, Mapping):
            lines.append(
                f"- `{row_value.get('source_id')}` family={row_value.get('family')} records={row_value.get('parsed_record_count')} "
                f"root_match={row_value.get('root_cause_match')} route_match={row_value.get('route_match')}"
            )
    lines.extend(
        [
            "",
            "## Weak spots",
            f"- False-positive proxy count: {weak.get('false_positive_count')}",
            f"- False-negative proxy count: {weak.get('false_negative_count')}",
            f"- Unsafe action count: {weak.get('unsafe_action_count')}",
            f"- Worst sources: {', '.join(str(item) for item in _sequence(weak.get('worst_sources', ()))) or 'none'}",
        ]
    )
    return "\n".join(lines) + "\n"


def write_public_dataset_matrix_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_public_dataset_matrix_markdown(payload), encoding="utf-8")


def _manifest_sources(benchmark_payload: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    materialized_manifest = _mapping(benchmark_payload.get("materialized_manifest"))
    return tuple(item for item in _sequence(materialized_manifest.get("sources", ())) if isinstance(item, Mapping))


def _score_source(source: Mapping[str, Any]) -> dict[str, Any]:
    single_manifest = {"version": "p44-source-row", "sources": [dict(source)]}
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(single_manifest, handle)
        handle.write("\n")
        path = Path(handle.name)
    try:
        payload = run_raw_real_dataset_replay_fixture(path).to_dict()
    finally:
        path.unlink(missing_ok=True)
    cards = _sequence(payload.get("source_cards", ()))
    card = _mapping(cards[0]) if cards else {}
    prediction = _mapping(card.get("prediction"))
    score = _mapping(payload.get("score"))
    summary = _mapping(payload.get("summary"))
    row = {
        "source_id": str(source.get("id", "unknown")),
        "family": str(source.get("family", "unknown")),
        "path": str(source.get("path", "")),
        "parsed_record_count": int(summary.get("parsed_record_count", 0)),
        "label_coverage": float(score.get("label_coverage", 0.0)),
        "root_cause_accuracy": float(score.get("root_cause_accuracy", 0.0)),
        "route_accuracy": float(score.get("route_accuracy", 0.0)),
        "unsafe_action_count": int(score.get("unsafe_action_count", 0)),
        "root_cause_match": bool(card.get("root_cause_match", False)),
        "route_match": bool(card.get("route_match", False)),
        "label_match": bool(card.get("label_match", False)),
        "expected_root_cause": str(card.get("expected_root_cause", source.get("expected_root_cause", "unknown"))),
        "predicted_root_cause": str(prediction.get("root_cause", "unknown")),
        "expected_route": str(card.get("expected_route", source.get("expected_route", "unknown"))),
        "predicted_route": str(prediction.get("route", "unknown")),
    }
    redacted = redact_value(row)
    return dict(redacted) if isinstance(redacted, Mapping) else row


def _aggregate_families(source_matrix: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in source_matrix:
        grouped[str(row.get("family", "unknown"))].append(row)
    result: dict[str, dict[str, Any]] = {}
    for family, rows in grouped.items():
        source_count = len(rows)
        parsed = sum(int(row.get("parsed_record_count", 0)) for row in rows)
        root_matches = sum(1 for row in rows if bool(row.get("root_cause_match")))
        route_matches = sum(1 for row in rows if bool(row.get("route_match")))
        label_matches = sum(1 for row in rows if bool(row.get("label_match")))
        unsafe = sum(int(row.get("unsafe_action_count", 0)) for row in rows)
        result[family] = {
            "source_count": source_count,
            "parsed_record_count": parsed,
            "label_coverage": _ratio(label_matches, source_count),
            "root_cause_accuracy": _ratio(root_matches, source_count),
            "route_accuracy": _ratio(route_matches, source_count),
            "unsafe_action_count": unsafe,
        }
    return result


def _compute_weak_spots(source_matrix: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    false_positive_count = 0
    false_negative_count = 0
    unsafe_action_count = 0
    worst_sources: list[str] = []
    for row in source_matrix:
        unsafe_action_count += int(row.get("unsafe_action_count", 0))
        root_match = bool(row.get("root_cause_match"))
        route_match = bool(row.get("route_match"))
        label_match = bool(row.get("label_match"))
        predicted_root = str(row.get("predicted_root_cause", "unknown"))
        expected_root = str(row.get("expected_root_cause", "unknown"))
        if predicted_root == "false_positive" and expected_root != "false_positive":
            false_negative_count += 1
        if predicted_root != "false_positive" and expected_root == "false_positive":
            false_positive_count += 1
        if not (root_match and route_match and label_match):
            worst_sources.append(str(row.get("source_id", "unknown")))
    return {
        "false_positive_count": false_positive_count,
        "false_negative_count": false_negative_count,
        "unsafe_action_count": unsafe_action_count,
        "worst_sources": worst_sources[:10],
    }


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
