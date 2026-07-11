"""P109 RCAEval normalization adapter.

The adapter keeps candidate-visible telemetry physically separate from
scorer-only truth. It supports fixture-shaped RCAEval case directories and the
official simple_data-style CSV as smoke-only telemetry when no official truth is
present.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "p109.rcaeval_case.v1"
SMOKE_ONLY_NOTE = "official_simple_data_has_no_official_truth"


class RCAEvalNormalizationError(ValueError):
    """Raised when a source cannot satisfy the P109 RCAEval contract."""


RCAEvalContractError = RCAEvalNormalizationError


@dataclass(frozen=True)
class RCAEvalCase:
    case_id: str
    source_id: str
    system_id: str
    fault_family: str
    incident_group_id: str
    time_range: Mapping[str, Any]
    topology: Mapping[str, Any]
    candidate_visible_evidence: tuple[Mapping[str, Any], ...]
    raw_hashes: Mapping[str, str]
    scorer_only_truth: Mapping[str, Any] | None
    dataset_id: str = "rcaeval"
    source_revision: str = "fixture"
    real_telemetry_smoke_only: bool = False

    @property
    def truth_available(self) -> bool:
        return self.scorer_only_truth is not None

    @property
    def release_qualifying_truth(self) -> bool:
        return self.truth_available and not self.real_telemetry_smoke_only and self.source_revision != "fixture"

    @property
    def scorer_truth_sha256(self) -> str | None:
        if self.scorer_only_truth is None:
            return None
        return _sha256_json(self.scorer_only_truth)

    @property
    def scorer_truth_ref(self) -> dict[str, str] | None:
        if self.scorer_truth_sha256 is None:
            return None
        return {"truth_id": f"{self.case_id}:truth", "sha256": self.scorer_truth_sha256}

    def to_candidate_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_id": self.dataset_id,
            "source_id": self.source_id,
            "source": {"immutable_revision": self.source_revision},
            "case_id": self.case_id,
            "system_id": self.system_id,
            "incident_group_id": self.incident_group_id,
            "time_range": dict(self.time_range),
            "topology": _stable(self.topology),
            "candidate_visible_evidence": [_stable(item) for item in self.candidate_visible_evidence],
            "raw_hashes": _candidate_visible_raw_hashes(self.raw_hashes, self.candidate_visible_evidence),
        }

    def to_normalized_dict(self) -> dict[str, Any]:
        payload = self.to_candidate_dict()
        payload.update(
            {
                "fault_family": self.fault_family,
                "raw_hashes": dict(sorted(self.raw_hashes.items())),
                "truth_available": self.truth_available,
                "release_qualifying_truth": self.release_qualifying_truth,
                "real_telemetry_smoke_only": self.real_telemetry_smoke_only,
                "scorer_truth_ref": self.scorer_truth_ref,
                "qualification": self.qualification,
            }
        )
        if self.scorer_only_truth is not None:
            payload["scorer_only_truth"] = _stable(self.scorer_only_truth)
        return payload

    @property
    def qualification(self) -> dict[str, Any]:
        if self.truth_available:
            if self.source_revision == "fixture":
                return {
                    "truth_available": True,
                    "real_telemetry_smoke_only": False,
                    "release_qualified": False,
                    "reason": "fixture_source_revision_not_release_qualified",
                }
            return {
                "truth_available": True,
                "real_telemetry_smoke_only": False,
                "release_qualified": True,
                "reason": None,
            }
        return {
            "truth_available": False,
            "real_telemetry_smoke_only": self.real_telemetry_smoke_only,
            "release_qualified": False,
            "reason": SMOKE_ONLY_NOTE if self.real_telemetry_smoke_only else "scorer_truth_missing",
        }


@dataclass(frozen=True)
class RCAEvalNormalizationResult:
    cases: tuple[RCAEvalCase, ...]
    normalized_corpus_sha256: str
    output_jsonl: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def case_count(self) -> int:
        return len(self.cases)

    @property
    def truth_available_count(self) -> int:
        return sum(1 for case in self.cases if case.truth_available)

    @property
    def release_qualified(self) -> bool:
        return bool(self.cases) and all(case.release_qualifying_truth for case in self.cases)

    @property
    def status(self) -> str:
        if self.release_qualified:
            return "release_qualified"
        if any(case.real_telemetry_smoke_only for case in self.cases):
            return "real_telemetry_smoke_only"
        return "unevaluable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "p109.rcaeval_normalization_report.v1",
            "case_count": self.case_count,
            "truth_available_count": self.truth_available_count,
            "release_qualified": self.release_qualified,
            "status": self.status,
            "normalized_corpus_sha256": self.normalized_corpus_sha256,
            "output_jsonl": self.output_jsonl,
            "notes": list(self.notes),
            "cases": [case.to_normalized_dict() for case in self.cases],
        }


def load_rcaeval_cases(
    root: str | Path,
    *,
    dataset_id: str = "rcaeval",
    source_revision: str = "fixture",
    real_telemetry_smoke_only: bool | None = None,
) -> tuple[RCAEvalCase, ...]:
    base = Path(root)
    if not base.exists():
        raise FileNotFoundError(f"RCAEval source path does not exist: {base}")
    if _is_simple_data_dir(base):
        return (_load_simple_data_case(base / "simple_data.csv", dataset_id=dataset_id, source_revision=source_revision),)
    if base.is_file() and base.name == "simple_data.csv":
        return (_load_simple_data_case(base, dataset_id=dataset_id, source_revision=source_revision),)

    case_dirs = [item for item in base.iterdir() if item.is_dir()]
    if (base / "case.json").exists() or any((base / name).exists() for name in ("metrics.csv", "logs.jsonl", "traces.jsonl", "truth.json")):
        case_dirs = [base]
    if not case_dirs:
        raise RCAEvalNormalizationError("missing_case_identity")

    cases = [_load_case_dir(case_dir, dataset_id=dataset_id, source_revision=source_revision) for case_dir in sorted(case_dirs, key=lambda item: item.name)]
    _reject_duplicate_case_ids(cases)
    return tuple(cases)


def normalize_rcaeval_cases(
    root: str | Path,
    *,
    output_jsonl: str | Path | None = None,
    dataset_id: str = "rcaeval",
    source_revision: str = "fixture",
    real_telemetry_smoke_only: bool | None = None,
) -> RCAEvalNormalizationResult:
    cases = load_rcaeval_cases(root, dataset_id=dataset_id, source_revision=source_revision, real_telemetry_smoke_only=real_telemetry_smoke_only)
    lines = [_dumps(case.to_normalized_dict()) for case in sorted(cases, key=lambda item: item.case_id)]
    content = "".join(f"{line}\n" for line in lines)
    if output_jsonl is not None:
        Path(output_jsonl).write_text(content, encoding="utf-8")
    notes = (SMOKE_ONLY_NOTE,) if any(case.real_telemetry_smoke_only for case in cases) and not any(case.truth_available for case in cases) else ()
    return RCAEvalNormalizationResult(
        cases=tuple(sorted(cases, key=lambda item: item.case_id)),
        normalized_corpus_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        output_jsonl=str(output_jsonl) if output_jsonl is not None else None,
        notes=notes,
    )


def serialize_candidate_input(case: RCAEvalCase | Mapping[str, Any]) -> dict[str, Any]:
    payload = case.to_candidate_dict() if isinstance(case, RCAEvalCase) else dict(case)
    return {
        "schema_version": str(payload.get("schema_version", SCHEMA_VERSION)),
        "case_id": str(payload.get("case_id", "")),
        "candidate_visible_evidence": _stable(payload.get("candidate_visible_evidence", [])),
    }


def candidate_context_jsonl(cases: Sequence[RCAEvalCase]) -> str:
    rows = [serialize_candidate_input(case) for case in sorted(cases, key=lambda item: item.case_id)]
    return "".join(f"{_dumps(row)}\n" for row in rows)


def write_candidate_jsonl(cases: Sequence[RCAEvalCase], path: str | Path) -> None:
    rows = [serialize_candidate_input(case) for case in sorted(cases, key=lambda item: item.case_id)]
    Path(path).write_text("".join(f"{_dumps(row)}\n" for row in rows), encoding="utf-8")


def write_scorer_truth_jsonl(cases: Sequence[RCAEvalCase], path: str | Path) -> None:
    rows = []
    for case in sorted(cases, key=lambda item: item.case_id):
        if case.scorer_only_truth is None:
            continue
        rows.append(
            {
                "schema_version": "p109.rcaeval_scorer_truth.v1",
                "case_id": case.case_id,
                "truth_id": f"{case.case_id}:truth",
                "scorer_only_truth_sha256": case.scorer_truth_sha256,
                "scorer_only_truth": _stable(case.scorer_only_truth),
            }
        )
    Path(path).write_text("".join(f"{_dumps(row)}\n" for row in rows), encoding="utf-8")


def _candidate_visible_raw_hashes(raw_hashes: Mapping[str, str], observations: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    visible_paths = {str(item.get("raw_path", "")) for item in observations if item.get("raw_path")}
    if "topology.json" in raw_hashes:
        visible_paths.add("topology.json")
    return {
        path: raw_hashes[path]
        for path in sorted(visible_paths)
        if path in raw_hashes and not _is_scorer_artifact_path(path)
    }


def _is_scorer_artifact_path(path: str) -> bool:
    lower = path.lower()
    return any(token in lower for token in ("truth", "scorer", "label", "report"))


def read_normalized_jsonl(path: str | Path) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            data = json.loads(line)
            if not isinstance(data, Mapping):
                raise RCAEvalNormalizationError("normalized_record_not_mapping")
            rows.append(data)
    return tuple(rows)


def _load_case_dir(case_dir: Path, *, dataset_id: str, source_revision: str) -> RCAEvalCase:
    if (case_dir / "case.json").exists():
        return _load_manifest_case(case_dir, dataset_id=dataset_id, source_revision=source_revision)

    case_id = case_dir.name
    truth_path = case_dir / "truth.json"
    truth = _read_json_mapping(truth_path) if truth_path.exists() else None
    if truth is not None and str(truth.get("case_id", case_id)) != case_id:
        raise RCAEvalNormalizationError("mismatched_case_directory")

    raw_hashes = _hash_case_files(case_dir)
    topology = _read_json_mapping(case_dir / "topology.json") if (case_dir / "topology.json").exists() else {"services": [], "edges": []}
    observations: list[Mapping[str, Any]] = []
    observations.extend(_read_metrics_csv(case_dir / "metrics.csv", raw_hashes=raw_hashes) if (case_dir / "metrics.csv").exists() else [])
    observations.extend(_read_jsonl_observations(case_dir / "logs.jsonl", modality="log", raw_hashes=raw_hashes) if (case_dir / "logs.jsonl").exists() else [])
    observations.extend(_read_jsonl_observations(case_dir / "traces.jsonl", modality="trace", raw_hashes=raw_hashes) if (case_dir / "traces.jsonl").exists() else [])
    if not observations:
        raise RCAEvalNormalizationError("missing_candidate_visible_evidence")
    _validate_timestamps(observations)
    _reject_duplicate_observations(observations)
    _reject_visible_leakage(observations, truth, raw_paths=raw_hashes.keys())

    return RCAEvalCase(
        case_id=case_id,
        source_id=f"rcaeval.{case_id}",
        system_id=case_id,
        fault_family=str((truth or {}).get("fault_type", "truth_unavailable")),
        incident_group_id=case_id,
        time_range=_time_range_from_observations(observations),
        topology=topology,
        candidate_visible_evidence=tuple(sorted(observations, key=lambda item: (str(item.get("timestamp", "")), str(item.get("raw_path", "")), str(item.get("id", ""))))),
        raw_hashes=raw_hashes,
        scorer_only_truth=_normalize_truth(truth) if truth is not None else None,
        dataset_id=dataset_id,
        source_revision=source_revision,
    )


def _load_manifest_case(case_dir: Path, *, dataset_id: str, source_revision: str) -> RCAEvalCase:
    manifest = _read_json_mapping(case_dir / "case.json")
    case_id = str(manifest.get("case_id") or case_dir.name)
    if case_id != case_dir.name and case_dir.parent.name not in {"valid_cases", "case-001"}:
        raise RCAEvalNormalizationError("mismatched_case_directory")
    raw_hashes = _hash_case_files(case_dir)
    topology = _mapping(manifest.get("topology"))
    observations: list[Mapping[str, Any]] = []
    for item in _sequence(manifest.get("telemetry_files")):
        if not isinstance(item, Mapping):
            continue
        rel_path = str(item.get("path", ""))
        source_path = case_dir / rel_path
        if not source_path.exists():
            raise RCAEvalNormalizationError(f"missing_telemetry_file:{rel_path}")
        modality = str(item.get("modality", "unknown"))
        service = str(item.get("service", "unknown"))
        observations.extend(_read_telemetry_file(source_path, rel_path=rel_path, modality=modality, service=service, raw_hashes=raw_hashes))
    for item in _sequence(manifest.get("observations")):
        if isinstance(item, Mapping):
            observations.append(dict(item))
    if not observations:
        raise RCAEvalNormalizationError("missing_candidate_visible_evidence")
    truth = _normalize_truth(_mapping(manifest.get("scorer_only_truth"))) if isinstance(manifest.get("scorer_only_truth"), Mapping) else None
    _validate_timestamps(observations)
    _reject_duplicate_observations(observations)
    _reject_visible_leakage(observations, truth, raw_paths=[key for key in raw_hashes if key != "case.json"])
    return RCAEvalCase(
        case_id=case_id,
        source_id=f"rcaeval.{case_id}",
        system_id=str(manifest.get("system_id", case_id)),
        fault_family=str(manifest.get("fault_family") or (truth or {}).get("fault_type", "truth_unavailable")),
        incident_group_id=str(manifest.get("incident_group_id", case_id)),
        time_range=_mapping(manifest.get("time_range")) or _time_range_from_observations(observations),
        topology=topology,
        candidate_visible_evidence=tuple(sorted(observations, key=lambda item: (str(item.get("timestamp", "")), str(item.get("raw_path", "")), str(item.get("id", ""))))),
        raw_hashes=raw_hashes,
        scorer_only_truth=truth,
        dataset_id=dataset_id,
        source_revision=source_revision,
    )


def _load_simple_data_case(path: Path, *, dataset_id: str, source_revision: str) -> RCAEvalCase:
    raw_hashes = {path.name: _sha256_file(path)}
    observations = _read_metrics_csv(path, raw_hashes=raw_hashes)
    _validate_timestamps(observations)
    return RCAEvalCase(
        case_id="simple_data",
        source_id="rcaeval.simple_data",
        system_id="simple_data",
        fault_family="truth_unavailable",
        incident_group_id="simple_data",
        time_range=_time_range_from_observations(observations),
        topology={"services": sorted({str(item.get("service", "unknown")) for item in observations}), "edges": []},
        candidate_visible_evidence=tuple(observations),
        raw_hashes=raw_hashes,
        scorer_only_truth=None,
        dataset_id=dataset_id,
        source_revision=source_revision,
        real_telemetry_smoke_only=True,
    )


def _read_telemetry_file(path: Path, *, rel_path: str, modality: str, service: str, raw_hashes: Mapping[str, str]) -> list[Mapping[str, Any]]:
    if path.suffix == ".csv":
        return _read_metrics_csv(path, raw_hashes=raw_hashes, rel_path=rel_path, default_service=service)
    if path.suffix == ".jsonl":
        return _read_jsonl_observations(path, modality=modality, raw_hashes=raw_hashes, rel_path=rel_path, default_service=service)
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = _sequence(data.get("spans")) if isinstance(data, Mapping) and "spans" in data else [data]
        observations: list[Mapping[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            if isinstance(row, Mapping):
                item = dict(row)
                item.setdefault("modality", modality)
                item.setdefault("service", service)
                item.setdefault("raw_path", rel_path)
                item.setdefault("raw_sha256", raw_hashes.get(rel_path, ""))
                item.setdefault("id", f"{rel_path}#{index}")
                observations.append(item)
        return observations
    text = path.read_text(encoding="utf-8")
    return [
        {
            "id": f"{rel_path}#L1",
            "modality": modality,
            "timestamp": _first_token_timestamp(text) or "",
            "service": service,
            "message": text.strip(),
            "raw_path": rel_path,
            "raw_sha256": raw_hashes.get(rel_path, ""),
        }
    ]


def _read_metrics_csv(path: Path, *, raw_hashes: Mapping[str, str], rel_path: str | None = None, default_service: str = "unknown") -> list[Mapping[str, Any]]:
    rel = rel_path or path.name
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        rows = list(reader)
    if "time" in fieldnames and "timestamp" not in fieldnames:
        return _read_wide_metrics_rows(rows, fieldnames=fieldnames, rel=rel, raw_hash=raw_hashes.get(rel, ""))
    observations: list[Mapping[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        timestamp = str(row.get("timestamp", "")).strip()
        service = str(row.get("service", default_service)).strip() or default_service
        item = {
            "id": f"{rel}:{index}",
            "modality": "metric",
            "timestamp": timestamp,
            "service": service,
            "metric": str(row.get("metric", "")).strip(),
            "value": _coerce_scalar(row.get("value")),
            "raw_path": rel,
            "raw_line": index + 1,
            "raw_sha256": raw_hashes.get(rel, ""),
        }
        if row.get("unit") not in (None, ""):
            item["unit"] = str(row.get("unit"))
        observations.append(item)
    return observations


def _read_wide_metrics_rows(rows: Sequence[Mapping[str, Any]], *, fieldnames: Sequence[str], rel: str, raw_hash: str) -> list[Mapping[str, Any]]:
    observations: list[Mapping[str, Any]] = []
    metric_columns = [name for name in fieldnames if name != "time"]
    for row_index, row in enumerate(rows, start=1):
        timestamp = _epoch_seconds_to_utc_iso(row.get("time"))
        for column in metric_columns:
            raw_value = row.get(column)
            if raw_value in (None, ""):
                continue
            service, metric = _split_wide_metric_column(column)
            observations.append(
                {
                    "id": f"{rel}:{row_index + 1}:{column}",
                    "modality": "metric",
                    "timestamp": timestamp,
                    "service": service,
                    "metric": metric,
                    "value": _coerce_scalar(raw_value),
                    "raw_path": rel,
                    "raw_line": row_index + 1,
                    "raw_column": column,
                    "raw_sha256": raw_hash,
                }
            )
    return observations


def _split_wide_metric_column(column: str) -> tuple[str, str]:
    service, separator, metric = column.rpartition("_")
    if not separator or not service or not metric:
        return "unknown", column
    return service, metric


def _epoch_seconds_to_utc_iso(value: Any) -> str:
    try:
        seconds = float(str(value))
    except (TypeError, ValueError) as exc:
        raise RCAEvalNormalizationError("invalid_timestamp") from exc
    if not seconds.is_integer():
        timestamp = datetime.fromtimestamp(seconds, tz=UTC).isoformat(timespec="milliseconds")
    else:
        timestamp = datetime.fromtimestamp(int(seconds), tz=UTC).isoformat(timespec="seconds")
    return timestamp.replace("+00:00", "Z")


def _read_jsonl_observations(path: Path, *, modality: str, raw_hashes: Mapping[str, str], rel_path: str | None = None, default_service: str = "unknown") -> list[Mapping[str, Any]]:
    rel = rel_path or path.name
    observations: list[Mapping[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        data = json.loads(line)
        if not isinstance(data, Mapping):
            raise RCAEvalNormalizationError("observation_not_mapping")
        item = dict(data)
        item.setdefault("id", f"{rel}:{index}")
        item.setdefault("modality", modality)
        item.setdefault("service", default_service)
        item["raw_path"] = rel
        item["raw_line"] = index
        item["raw_sha256"] = raw_hashes.get(rel, "")
        observations.append(item)
    return observations


def _normalize_truth(truth: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if truth is None:
        return None
    evidence = truth.get("evidence_references", truth.get("evidence_refs", []))
    return {
        "root_service": str(truth.get("root_service", "")),
        "fault_type": str(truth.get("fault_type", "")),
        "acceptable_service_aliases": [str(item) for item in _sequence(truth.get("acceptable_service_aliases", []))],
        "evidence_references": [str(item) for item in _sequence(evidence)],
    }


def _reject_visible_leakage(observations: Sequence[Mapping[str, Any]], truth: Mapping[str, Any] | None, *, raw_paths: Iterable[str]) -> None:
    if truth is None:
        return
    sensitive_values = {str(truth.get("root_service", "")).lower(), str(truth.get("fault_type", "")).lower()}
    sensitive_values.update(str(item).lower() for item in _sequence(truth.get("acceptable_service_aliases", [])))
    sensitive_values.discard("")
    suspicious_keys = {"truth", "scorer_only", "root_service", "root_cause", "fault_type", "answer", "label"}
    for raw_path in raw_paths:
        lower_path = raw_path.lower()
        if any(key in lower_path for key in suspicious_keys) and any(value and value in lower_path for value in sensitive_values):
            raise RCAEvalNormalizationError("candidate_visible_truth_leak: truth label leaked through visible raw path")
    for observation in observations:
        for key_path, value in _walk(observation):
            lower_key = ".".join(key_path).lower()
            lower_value = str(value).lower()
            if any(key in lower_key for key in suspicious_keys) and (not sensitive_values or any(item in lower_value for item in sensitive_values)):
                raise RCAEvalNormalizationError("candidate_visible_truth_leak: truth label leaked into candidate-visible evidence")


def _walk(value: Any, prefix: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            yield from _walk(nested, (*prefix, str(key)))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            yield from _walk(nested, (*prefix, str(index)))
    else:
        yield prefix, value


def _validate_timestamps(observations: Sequence[Mapping[str, Any]]) -> None:
    for item in observations:
        timestamp = str(item.get("timestamp", "")).strip()
        if not timestamp:
            raise RCAEvalNormalizationError("invalid_timestamp")


def _reject_duplicate_observations(observations: Sequence[Mapping[str, Any]]) -> None:
    seen: set[str] = set()
    for item in observations:
        key = _sha256_json(item)
        if key in seen:
            raise RCAEvalNormalizationError("duplicate_observation")
        seen.add(key)


def _reject_duplicate_case_ids(cases: Sequence[RCAEvalCase]) -> None:
    seen: set[str] = set()
    for case in cases:
        if case.case_id in seen:
            raise RCAEvalNormalizationError("duplicate_case_identity")
        seen.add(case.case_id)


def _hash_case_files(case_dir: Path) -> dict[str, str]:
    return {
        str(path.relative_to(case_dir)): _sha256_file(path)
        for path in sorted(case_dir.rglob("*"))
        if path.is_file()
    }


def _time_range_from_observations(observations: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    timestamps = sorted(str(item.get("timestamp", "")) for item in observations if str(item.get("timestamp", "")))
    return {"start": timestamps[0] if timestamps else "", "end": timestamps[-1] if timestamps else ""}


def _is_simple_data_dir(path: Path) -> bool:
    return path.is_dir() and (path / "simple_data.csv").exists() and not any(item.is_dir() for item in path.iterdir())


def _read_json_mapping(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise RCAEvalNormalizationError("json_mapping_required")
    return data


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _coerce_scalar(value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _first_token_timestamp(text: str) -> str | None:
    token = text.strip().split(" ", 1)[0] if text.strip() else ""
    return token if "T" in token else None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_dumps(value).encode("utf-8")).hexdigest()


def _dumps(value: Any) -> str:
    return json.dumps(_stable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple):
        return [_stable(item) for item in value]
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value
