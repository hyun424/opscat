"""P12 real-dataset-shaped evaluation harness.

This module imports tiny repo-local or user-supplied local dataset samples into
OpsCat judgment cases. It never downloads datasets, never calls external
services, and keeps all execution local/mock so it can be used before an LLM
judgment layer is added.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.services.judgment_adapters import cases_from_loghub_rows, cases_from_nab_windows, load_loghub_rows, load_nab_rows
from app.services.judgment_benchmark import JudgmentBenchmarkResult, render_benchmark_markdown, run_judgment_benchmark
from app.services.judgment_dataset import JudgmentCase, JudgmentRubric, write_judgment_cases
from app.services.redaction import redact_text, redact_value

DatasetFamily = Literal["loghub", "nab", "aiops"]
DEFAULT_MANIFEST_PATH = Path("evals/real_datasets/fixtures/manifest.json")
DEFAULT_FIXTURE_SAMPLES: tuple[tuple[str, str], ...] = (
    ("loghub", "evals/real_datasets/fixtures/loghub/apache_sample.jsonl"),
    ("nab", "evals/real_datasets/fixtures/nab/real_known_cause_sample.csv"),
    ("aiops", "evals/real_datasets/fixtures/aiops/multisignal_sample.jsonl"),
)
_REMOTE_PREFIXES = ("http://", "https://", "s3://", "gs://", "az://", "ftp://")
_ALLOWED_FAMILIES = {"loghub", "nab", "aiops"}


@dataclass(frozen=True)
class DatasetSource:
    name: str
    family: str
    homepage: str
    citation: str
    license: str
    expected_local_path: str
    supported_files: tuple[str, ...]
    labels: tuple[str, ...]
    import_mode: str = "local_path_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family,
            "homepage": self.homepage,
            "citation": self.citation,
            "license": self.license,
            "expected_local_path": self.expected_local_path,
            "supported_files": list(self.supported_files),
            "labels": list(self.labels),
            "import_mode": self.import_mode,
        }


@dataclass(frozen=True)
class DatasetSourceManifest:
    sources: tuple[DatasetSource, ...]
    boundary: str
    version: str = "p12-fixtures-v1"
    normal_verification_downloads: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "normal_verification_downloads": self.normal_verification_downloads,
            "boundary": self.boundary,
            "sources": [source.to_dict() for source in self.sources],
        }


@dataclass(frozen=True)
class ExternalLabelMapping:
    raw_label: str
    family: str
    anomaly: bool
    incident_class: str
    root_cause: str
    severity: str
    expected_route: str
    tags: tuple[str, ...]
    unmapped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_label": self.raw_label,
            "family": self.family,
            "anomaly": self.anomaly,
            "incident_class": self.incident_class,
            "root_cause": self.root_cause,
            "severity": self.severity,
            "expected_route": self.expected_route,
            "tags": list(self.tags),
            "unmapped": self.unmapped,
        }


@dataclass(frozen=True)
class ImportQuality:
    accepted_records: int = 0
    skipped_records: int = 0
    unsupported_records: int = 0
    redacted_records: int = 0
    unmapped_labels: dict[str, int] | None = None
    label_counts: dict[str, int] | None = None
    family_counts: dict[str, int] | None = None
    local_mock_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_mock_only": self.local_mock_only,
            "accepted_records": self.accepted_records,
            "skipped_records": self.skipped_records,
            "unsupported_records": self.unsupported_records,
            "redacted_records": self.redacted_records,
            "unmapped_labels": dict(sorted((self.unmapped_labels or {}).items())),
            "label_counts": dict(sorted((self.label_counts or {}).items())),
            "family_counts": dict(sorted((self.family_counts or {}).items())),
        }


@dataclass(frozen=True)
class DatasetImportResult:
    family: str
    dataset_name: str
    cases: tuple[JudgmentCase, ...]
    quality: ImportQuality
    source_path: str
    local_mock_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_mock_only": self.local_mock_only,
            "family": self.family,
            "dataset_name": self.dataset_name,
            "source_path": self.source_path,
            "case_count": len(self.cases),
            "quality": self.quality.to_dict(),
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass(frozen=True)
class RealDatasetEvaluationResult:
    imports: tuple[DatasetImportResult, ...]
    benchmark: JudgmentBenchmarkResult
    cases: tuple[JudgmentCase, ...]
    local_mock_only: bool = True

    @property
    def passed(self) -> bool:
        return bool(self.cases) and self.benchmark.passed and self.import_quality.unsupported_records == 0

    @property
    def import_quality(self) -> ImportQuality:
        return combine_import_quality([item.quality for item in self.imports])

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_mock_only": self.local_mock_only,
            "passed": self.passed,
            "case_count": len(self.cases),
            "import_quality": self.import_quality.to_dict(),
            "imports": [item.to_dict() for item in self.imports],
            "benchmark": self.benchmark.to_dict(),
        }


def load_dataset_source_manifest(path: str | Path = DEFAULT_MANIFEST_PATH) -> DatasetSourceManifest:
    local_path = _ensure_local_existing_path(path)
    data = json.loads(local_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("dataset source manifest must be a mapping")
    sources = tuple(_source_from_dict(item) for item in data.get("sources", []) if isinstance(item, Mapping))
    return DatasetSourceManifest(
        sources=sources,
        boundary=str(data.get("boundary", "local path import only; no external dataset download during normal verification")),
        version=str(data.get("version", "p12-fixtures-v1")),
        normal_verification_downloads=bool(data.get("normal_verification_downloads", False)),
    )


def map_external_label(raw_label: str | None, *, family: str) -> ExternalLabelMapping:
    raw = str(raw_label or "unknown").strip()
    label = raw.lower().replace("-", "_").replace(" ", "_")
    family_name = _family(family)
    table: tuple[tuple[tuple[str, ...], str, str, str, str, tuple[str, ...]], ...] = (
        (("deploy", "release", "rollback"), "deploy_regression", "deploy_regression", "high", "human_required", ("deploy", "error")),
        (("db", "database", "connection"), "db_saturation", "db_saturation", "high", "human_required", ("database", "capacity")),
        (("timeout", "downstream"), "downstream_timeout", "downstream_timeout", "high", "human_required", ("dependency", "timeout")),
        (("rate_limit", "429"), "rate_limit", "rate_limit", "warning", "approval_required", ("dependency", "rate_limit")),
        (("no_data", "nodata", "missing"), "no_data", "no_data", "warning", "human_required", ("no_data", "telemetry")),
        (("false_positive", "normal", "healthy"), "false_positive", "false_positive", "info", "approval_required", ("false_positive", "noise")),
        (("injection", "unsafe", "kubectl"), "prompt_or_log_injection", "prompt_or_log_injection", "critical", "blocked", ("safety", "injection")),
        (("spike", "anomaly", "error"), "metric_anomaly", "metric_anomaly", "high", "human_required", ("metric", "anomaly")),
    )
    for tokens, incident_class, root_cause, severity, route, tags in table:
        if any(token in label for token in tokens):
            return ExternalLabelMapping(raw, family_name, True, incident_class, root_cause, severity, route, (family_name, *tags), False)
    return ExternalLabelMapping(raw, family_name, False, "unknown_external_label", "unknown_external_label", "warning", "human_required", (family_name, "unmapped"), True)


def convert_dataset_sample(path: str | Path, *, family: str, dataset_name: str | None = None) -> DatasetImportResult:
    family_name = _family(family)
    local_path = _ensure_local_existing_path(path)
    if family_name == "loghub":
        return _convert_loghub(local_path, dataset_name=dataset_name or local_path.stem)
    if family_name == "nab":
        return _convert_nab(local_path, dataset_name=dataset_name or local_path.stem)
    if family_name == "aiops":
        return _convert_aiops(local_path, dataset_name=dataset_name or local_path.stem)
    raise ValueError(f"unsupported dataset family: {family}")


def combine_import_quality(items: Sequence[ImportQuality]) -> ImportQuality:
    labels: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()
    families: Counter[str] = Counter()
    return ImportQuality(
        accepted_records=sum(item.accepted_records for item in items),
        skipped_records=sum(item.skipped_records for item in items),
        unsupported_records=sum(item.unsupported_records for item in items),
        redacted_records=sum(item.redacted_records for item in items),
        unmapped_labels=dict(_update_counter(unmapped, [item.unmapped_labels or {} for item in items])),
        label_counts=dict(_update_counter(labels, [item.label_counts or {} for item in items])),
        family_counts=dict(_update_counter(families, [item.family_counts or {} for item in items])),
    )


def run_real_dataset_evaluation(
    samples: Sequence[tuple[str, str | Path]] | None = None,
    *,
    output_cases: str | Path | None = None,
) -> RealDatasetEvaluationResult:
    imports = tuple(convert_dataset_sample(path, family=family) for family, path in (samples or DEFAULT_FIXTURE_SAMPLES))
    cases = tuple(case for item in imports for case in item.cases)
    if output_cases:
        write_judgment_cases(output_cases, cases)
    benchmark = run_judgment_benchmark(cases)
    return RealDatasetEvaluationResult(imports=imports, benchmark=benchmark, cases=cases)


def render_real_dataset_evaluation_markdown(result: RealDatasetEvaluationResult) -> str:
    data = result.to_dict()
    quality = data["import_quality"]
    lines = [
        "# OpsCat Real Dataset Evaluation",
        "",
        "Boundary: local/mock only; no auth/session work; no external dataset download during normal verification; does not claim unattended production operation.",
        "",
        f"- Cases: {data['case_count']}",
        f"- Passed: {data['passed']}",
        f"- Benchmark score: {data['benchmark']['overall_score']}",
        f"- Accepted records: {quality['accepted_records']}",
        f"- Unsupported records: {quality['unsupported_records']}",
        "",
        "## Anomaly Detection",
        "",
        f"- Label counts: `{json.dumps(quality['label_counts'], sort_keys=True)}`",
        f"- Unmapped labels: `{json.dumps(quality['unmapped_labels'], sort_keys=True)}`",
        "",
        "## Incident Classification",
        "",
        f"- Family counts: `{json.dumps(quality['family_counts'], sort_keys=True)}`",
        "",
        "## Response Judgment",
        "",
        f"- Benchmark passed: {data['benchmark']['passed']}",
        f"- Safety regressions: `{json.dumps(data['benchmark']['safety_regressions'], sort_keys=True)}`",
        "",
        "## Underlying Judgment Benchmark",
        "",
        render_benchmark_markdown(result.benchmark),
    ]
    return "\n".join(lines)


def write_real_dataset_evaluation_outputs(
    result: RealDatasetEvaluationResult,
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(redact_value(result.to_dict()), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_real_dataset_evaluation_markdown(result), encoding="utf-8")


def _source_from_dict(data: Mapping[str, Any]) -> DatasetSource:
    return DatasetSource(
        name=str(data.get("name", "")),
        family=str(data.get("family", "")),
        homepage=str(data.get("homepage", "")),
        citation=str(data.get("citation", "")),
        license=str(data.get("license", "")),
        expected_local_path=str(data.get("expected_local_path", "")),
        supported_files=_tuple(data.get("supported_files", ())),
        labels=_tuple(data.get("labels", ())),
        import_mode=str(data.get("import_mode", "local_path_only")),
    )


def _convert_loghub(path: Path, *, dataset_name: str) -> DatasetImportResult:
    rows = load_loghub_rows(path)
    labels = [str(row.get("label") or row.get("level") or "unknown") for row in rows]
    mappings = [map_external_label(label, family="loghub") for label in labels]
    cases = tuple(cases_from_loghub_rows(rows, case_id=f"real-loghub-{_safe_id(dataset_name)}"))
    cases = tuple(_real_loghub_case(case) for case in cases)
    return DatasetImportResult(
        family="loghub",
        dataset_name=dataset_name,
        cases=cases,
        quality=_quality("loghub", rows, labels, mappings),
        source_path=str(path),
    )


def _convert_nab(path: Path, *, dataset_name: str) -> DatasetImportResult:
    rows = load_nab_rows(path)
    labels = ["anomaly" if _bool(row.get("is_anomaly")) else "normal" for row in rows]
    mappings = [map_external_label(label, family="nab") for label in labels]
    cases = tuple(cases_from_nab_windows(rows, dataset=dataset_name, service="real-metric-service"))
    cases = tuple(_with_dataset_tags(case, ("real_dataset", "nab")) for case in cases)
    return DatasetImportResult(
        family="nab",
        dataset_name=dataset_name,
        cases=cases,
        quality=_quality("nab", rows, labels, mappings),
        source_path=str(path),
    )


def _convert_aiops(path: Path, *, dataset_name: str) -> DatasetImportResult:
    records = _load_json_records(path)
    cases: list[JudgmentCase] = []
    labels: list[str] = []
    mappings: list[ExternalLabelMapping] = []
    unsupported = 0
    for index, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            unsupported += 1
            continue
        label = str(record.get("root_cause") or record.get("incident_type") or "unknown")
        mapping = map_external_label(label, family="aiops")
        labels.append(label)
        mappings.append(mapping)
        cases.append(_aiops_case(record, dataset_name=dataset_name, index=index, mapping=mapping))
    quality = _quality("aiops", records, labels, mappings, unsupported_records=unsupported)
    return DatasetImportResult(family="aiops", dataset_name=dataset_name, cases=tuple(cases), quality=quality, source_path=str(path))


def _aiops_case(record: Mapping[str, Any], *, dataset_name: str, index: int, mapping: ExternalLabelMapping) -> JudgmentCase:
    incident_id = str(record.get("incident_id") or f"real-aiops-{_safe_id(dataset_name)}-{index:03d}")
    evidence: list[dict[str, Any]] = []
    for signal_family in ("logs", "metrics", "events"):
        values = record.get(signal_family, [])
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes, bytearray)):
            for item_index, item in enumerate(values, start=1):
                content = _signal_content(item)
                evidence.append(
                    {
                        "id": f"{signal_family[:-1]}:{item_index}",
                        "type": "metric" if signal_family == "metrics" else "log" if signal_family == "logs" else "event",
                        "source": dataset_name,
                        "content": redact_text(content),
                        "metadata": {"signal_family": signal_family, "raw_label": mapping.raw_label},
                    }
                )
    if not evidence:
        evidence.append({"id": "event:1", "type": "event", "source": dataset_name, "content": redact_text(str(record.get("summary", "unknown incident")))})
    required = tuple(item["id"] for item in evidence)
    return JudgmentCase(
        id=incident_id,
        title=f"AIOps-style {mapping.incident_class} sample",
        source="aiops",
        incident={
            "id": incident_id,
            "service": str(record.get("service", "aiops-service")),
            "environment": str(record.get("environment", "staging")),
            "severity": str(record.get("severity", mapping.severity)),
            "summary": redact_text(str(record.get("summary", mapping.incident_class))),
            "root_cause_candidate": mapping.root_cause,
            "confidence": 0.82 if not mapping.unmapped else 0.56,
            "alert_payload": {"dataset": dataset_name, "family": "aiops", "raw_label": mapping.raw_label},
        },
        signals=tuple({"id": item["id"], "type": item["type"], "source": item["source"]} for item in evidence),
        evidence=evidence,
        rubric=JudgmentRubric(
            expected_route="approval_required" if mapping.expected_route == "human_required" else mapping.expected_route,
            expected_hypotheses=(mapping.root_cause,),
            required_evidence=required,
            forbidden_actions=("production_restart", "kubectl", "database_mutation"),
            verification_criteria=(),
            explanation_keywords=tuple(tag.replace("_", " ") for tag in mapping.tags[:3]),
        ),
        tags=tuple(sorted({"real_dataset", *mapping.tags})),
    )


def _real_loghub_case(case: JudgmentCase) -> JudgmentCase:
    expected = case.rubric.expected_hypotheses
    hypothesis = "deploy" if any("deploy" in item for item in expected) else expected[0] if expected else "unknown_log_anomaly"
    return JudgmentCase(
        id=case.id,
        title=case.title,
        incident=case.incident,
        evidence=case.evidence,
        rubric=JudgmentRubric(
            expected_route="approval_required" if case.rubric.expected_route == "human_required" else case.rubric.expected_route,
            expected_hypotheses=(hypothesis,),
            required_evidence=case.rubric.required_evidence,
            forbidden_actions=case.rubric.forbidden_actions,
            verification_criteria=(),
            explanation_keywords=(hypothesis.replace("_", " "),),
        ),
        source=case.source,
        signals=case.signals,
        tags=tuple(sorted({*case.tags, "real_dataset", "loghub"})),
        local_mock_only=case.local_mock_only,
    )


def _with_dataset_tags(case: JudgmentCase, tags: tuple[str, ...]) -> JudgmentCase:
    return JudgmentCase(
        id=case.id,
        title=case.title,
        incident=case.incident,
        evidence=case.evidence,
        rubric=case.rubric,
        source=case.source,
        signals=case.signals,
        tags=tuple(sorted({*case.tags, *tags})),
        local_mock_only=case.local_mock_only,
    )


def _quality(
    family: str,
    records: Sequence[Any],
    labels: Sequence[str],
    mappings: Sequence[ExternalLabelMapping],
    *,
    unsupported_records: int = 0,
) -> ImportQuality:
    label_counts = Counter(str(label) for label in labels)
    unmapped = Counter(mapping.raw_label for mapping in mappings if mapping.unmapped)
    redacted_count = sum(1 for item in records if json.dumps(redact_value(item), sort_keys=True, default=str) != json.dumps(item, sort_keys=True, default=str))
    return ImportQuality(
        accepted_records=len(records) - unsupported_records,
        unsupported_records=unsupported_records,
        redacted_records=redacted_count,
        unmapped_labels=dict(unmapped),
        label_counts=dict(label_counts),
        family_counts={family: len(records) - unsupported_records},
    )


def _ensure_local_existing_path(path: str | Path) -> Path:
    value = str(path)
    if value.lower().startswith(_REMOTE_PREFIXES):
        raise ValueError("remote paths are not allowed; provide a local dataset path")
    local_path = Path(value)
    if not local_path.exists():
        raise FileNotFoundError(f"dataset path does not exist: {local_path}")
    return local_path


def _load_json_records(path: Path) -> list[Any]:
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, Mapping):
            rows = data.get("records") or data.get("incidents") or data.get("rows") or []
            return list(rows) if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes, bytearray)) else [data]
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    return []


def _signal_content(item: Any) -> str:
    if isinstance(item, Mapping):
        for key in ("message", "content", "name", "type"):
            if key in item:
                return " ".join(str(value) for value in item.values())
        return json.dumps(item, sort_keys=True, default=str)
    return str(item)


def _family(value: str) -> str:
    family = value.lower().strip()
    if family not in _ALLOWED_FAMILIES:
        raise ValueError(f"unsupported dataset family: {value}")
    return family


def _tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if str(item))
    return ()


def _update_counter(target: Counter[str], items: Sequence[Mapping[str, int]]) -> Counter[str]:
    for item in items:
        target.update({str(key): int(value) for key, value in item.items()})
    return target


def _safe_id(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-") or "dataset"


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "y", "anomaly"}
