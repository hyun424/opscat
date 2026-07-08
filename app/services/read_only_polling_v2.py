"""P34 read-only polling runtime v2.

The runtime uses P33 dry-run readiness as a gate before polling local telemetry
fixtures through P26 adapters. It never performs live API calls.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.live_connector_dry_run import run_live_connector_dry_run_fixture
from app.services.redaction import redact_value
from app.services.telemetry_adapter import TelemetrySnapshot, adapt_telemetry_fixture

_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "read_only": True,
    "dry_run_gate_required": True,
    "live_api_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_REMOTE_PREFIXES = ("http://", "https://", "s3://", "gs://", "az://", "ftp://")


@dataclass(frozen=True)
class PollingV2Job:
    id: str
    connector_id: str
    source: str
    fixture_path: str
    read_only: bool
    interval_seconds: int
    operation: str = "read"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PollingV2Job:
        return cls(
            id=str(data.get("id", "poll-job")),
            connector_id=str(data.get("connector_id", "")),
            source=str(data.get("source", "")),
            fixture_path=str(data.get("fixture_path", "")),
            read_only=bool(data.get("read_only", True)),
            interval_seconds=int(data.get("interval_seconds", 60) or 60),
            operation=str(data.get("operation", "read")),
        )


@dataclass(frozen=True)
class PollingV2JobResult:
    job: PollingV2Job
    status: str
    reasons: tuple[str, ...]
    connector_status: str
    snapshot: TelemetrySnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        windows = self.snapshot.to_trend_windows() if self.snapshot is not None else ()
        payload = {
            "job_id": self.job.id,
            "connector_id": self.job.connector_id,
            "source": self.job.source,
            "fixture_path": self.job.fixture_path,
            "read_only": self.job.read_only,
            "operation": self.job.operation,
            "status": self.status,
            "reasons": list(self.reasons),
            "connector_status": self.connector_status,
            "snapshot": self.snapshot.to_dict() if self.snapshot is not None else None,
            "trend_windows": [window.to_dict() for window in windows],
            "live_api_called": False,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class ReadOnlyPollingV2Report:
    jobs: tuple[PollingV2JobResult, ...]
    dry_run_summary: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        polled = [job for job in self.jobs if job.status == "polled"]
        skipped = [job for job in self.jobs if job.status == "skipped"]
        blocked = [job for job in self.jobs if job.status == "blocked"]
        snapshots = [job.snapshot for job in polled if job.snapshot is not None]
        trend_count = sum(len(snapshot.to_trend_windows()) for snapshot in snapshots)
        ready_read_jobs = [job for job in self.jobs if job.connector_status == "ready" and job.job.read_only]
        poll_success = _ratio(len(polled), len(ready_read_jobs))
        readiness_gate = 1.0 if all(job.status != "polled" for job in self.jobs if job.connector_status != "ready") else 0.0
        payload = {
            "summary": {
                "job_count": len(self.jobs),
                "polled_count": len(polled),
                "skipped_count": len(skipped),
                "blocked_count": len(blocked),
                "snapshot_count": len(snapshots),
                "trend_window_count": trend_count,
                "passed": len(polled) >= 2 and trend_count >= 4 and not _unsafe_poll_count(self.jobs),
            },
            "score": {
                "poll_success_rate": poll_success,
                "readiness_gate_rate": readiness_gate,
                "unsafe_poll_count": _unsafe_poll_count(self.jobs),
                "live_api_call_count": 0,
            },
            "boundary": dict(_BOUNDARY),
            "dry_run_summary": dict(self.dry_run_summary),
            "jobs": [job.to_dict() for job in self.jobs],
            "trend_windows": [window.to_dict() for snapshot in snapshots for window in snapshot.to_trend_windows()],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class ReadOnlyPollingV2Runner:
    def run_path(self, jobs_path: str | Path, dry_run_manifest: str | Path) -> ReadOnlyPollingV2Report:
        dry_run_payload = run_live_connector_dry_run_fixture(dry_run_manifest).to_dict()
        jobs = load_polling_v2_jobs(jobs_path)
        return self.run(jobs, dry_run_payload)

    def run(self, jobs: Sequence[PollingV2Job], dry_run_payload: Mapping[str, Any]) -> ReadOnlyPollingV2Report:
        connector_status = {
            str(item.get("connector_id")): str(item.get("status"))
            for item in _sequence(dry_run_payload.get("connectors", ()))
            if isinstance(item, Mapping)
        }
        results = tuple(_run_job(job, connector_status.get(job.connector_id, "missing")) for job in jobs)
        summary = dry_run_payload.get("summary", {}) if isinstance(dry_run_payload.get("summary"), Mapping) else {}
        return ReadOnlyPollingV2Report(jobs=results, dry_run_summary=summary)


def load_polling_v2_jobs(path: str | Path) -> tuple[PollingV2Job, ...]:
    local_path = _ensure_local_path(path)
    data = json.loads(local_path.read_text(encoding="utf-8"))
    raw = data.get("jobs", ()) if isinstance(data, Mapping) else data
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise ValueError("polling v2 fixture must contain jobs")
    return tuple(PollingV2Job.from_dict(item) for item in raw if isinstance(item, Mapping))


def run_read_only_polling_v2_fixture(jobs_path: str | Path, dry_run_manifest: str | Path) -> ReadOnlyPollingV2Report:
    return ReadOnlyPollingV2Runner().run_path(jobs_path, dry_run_manifest)


def render_read_only_polling_v2_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    lines = [
        "# OpsCat Read-only Polling Runtime v2 Report",
        "",
        "Boundary: read-only polling gated by P33 dry-run readiness; no live API calls; no production mutation; does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Jobs: {summary.get('job_count')}",
        f"- Polled: {summary.get('polled_count')}",
        f"- Skipped: {summary.get('skipped_count')}",
        f"- Blocked: {summary.get('blocked_count')}",
        f"- Trend windows: {summary.get('trend_window_count')}",
        "",
        "## Readiness gate",
        f"- poll_success_rate: {score.get('poll_success_rate')}",
        f"- readiness_gate_rate: {score.get('readiness_gate_rate')}",
        f"- unsafe_poll_count: {score.get('unsafe_poll_count')}",
        f"- live_api_call_count: {score.get('live_api_call_count')}",
        "",
        "## Jobs",
    ]
    jobs = payload.get("jobs", [])
    if isinstance(jobs, Sequence) and not isinstance(jobs, (str, bytes, bytearray)):
        for job in jobs:
            if isinstance(job, Mapping):
                reasons = ",".join(str(reason) for reason in _sequence(job.get("reasons", ())))
                lines.append(f"- `{job.get('job_id')}` connector={job.get('connector_id')} status={job.get('status')} reasons={reasons}")
    return "\n".join(lines) + "\n"


def write_read_only_polling_v2_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_read_only_polling_v2_markdown(payload), encoding="utf-8")


def _run_job(job: PollingV2Job, connector_status: str) -> PollingV2JobResult:
    if not job.read_only or job.operation != "read":
        return PollingV2JobResult(job=job, status="blocked", reasons=("write_or_mutation_job",), connector_status=connector_status)
    if connector_status != "ready":
        return PollingV2JobResult(job=job, status="skipped", reasons=("connector_not_ready",), connector_status=connector_status)
    snapshot = adapt_telemetry_fixture(job.source, _ensure_local_path(job.fixture_path))
    return PollingV2JobResult(job=job, status="polled", reasons=("read_only_fixture_polled",), connector_status=connector_status, snapshot=snapshot)


def _unsafe_poll_count(jobs: Sequence[PollingV2JobResult]) -> int:
    return sum(1 for job in jobs if job.status == "polled" and (not job.job.read_only or job.job.operation != "read"))


def _ensure_local_path(path: str | Path) -> Path:
    value = str(path)
    if value.lower().startswith(_REMOTE_PREFIXES):
        raise ValueError("remote polling paths are not allowed for normal verification")
    local_path = Path(value)
    if not local_path.exists():
        raise FileNotFoundError(f"polling v2 path does not exist: {local_path}")
    return local_path


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 3) if denominator else 0.0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
