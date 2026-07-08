"""P28 read-only polling runtime.

The runtime is local/mock by default: it consumes P27 readiness reports,
reads fixture payloads only, feeds P26 adapters, and never executes writes or
remediation actions.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.connector_readiness import evaluate_connector_readiness_fixture
from app.services.redaction import redact_value
from app.services.telemetry_adapter import TelemetrySnapshot, adapt_telemetry_fixture

_ALLOWED_POLL_CAPABILITIES = frozenset({"read", "query", "list", "health", "metadata"})
_MUTATION_MARKERS = ("write", "delete", "restart", "shell", "kubectl", "exec", "deploy", "rollback", "mutate", "update", "create", "patch", "purge")
_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "fixture_transport_only": True,
    "read_only_polling_only": True,
    "live_api_calls_enabled": False,
    "live_writes_enabled": False,
    "remediation_execution_enabled": False,
    "production_mutation_enabled": False,
    "default_external_model_calls": False,
}


@dataclass(frozen=True)
class PollingJob:
    id: str
    source: str
    fixture_path: str
    interval_seconds: int
    timeout_seconds: int
    enabled: bool
    requested_capabilities: tuple[str, ...]
    max_batch_size: int = 1
    simulate: str = "ok"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, index: int) -> PollingJob:
        return cls(
            id=str(data.get("id", f"poll-job-{index}")),
            source=str(data.get("source", "")),
            fixture_path=str(data.get("fixture_path", "")),
            interval_seconds=max(1, int(data.get("interval_seconds", 60) or 60)),
            timeout_seconds=max(1, int(data.get("timeout_seconds", 10) or 10)),
            enabled=bool(data.get("enabled", False)),
            requested_capabilities=tuple(str(item) for item in _sequence(data.get("requested_capabilities", ("read",)))),
            max_batch_size=max(1, int(data.get("max_batch_size", 1) or 1)),
            simulate=str(data.get("simulate", "ok")),
        )

    @property
    def has_mutation_request(self) -> bool:
        return any(_is_mutation_capability(capability) or capability not in _ALLOWED_POLL_CAPABILITIES for capability in self.requested_capabilities)


@dataclass(frozen=True)
class PollResult:
    job_id: str
    source: str
    status: str
    reasons: tuple[str, ...]
    tick: int
    snapshot: TelemetrySnapshot | None = None
    trend_window_count: int = 0
    next_safe_retry_seconds: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "job_id": self.job_id,
            "source": self.source,
            "status": self.status,
            "reasons": list(self.reasons),
            "tick": self.tick,
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
            "trend_window_count": self.trend_window_count,
            "next_safe_retry_seconds": self.next_safe_retry_seconds,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class PollingRuntimeReport:
    jobs: tuple[PollingJob, ...]
    polls: tuple[PollResult, ...]

    def snapshots(self) -> tuple[TelemetrySnapshot, ...]:
        return tuple(poll.snapshot for poll in self.polls if poll.snapshot is not None)

    def to_dict(self) -> dict[str, Any]:
        snapshots = self.snapshots()
        trend_window_count = sum(len(snapshot.to_trend_windows()) for snapshot in snapshots)
        payload = {
            "summary": {
                "job_count": len(self.jobs),
                "poll_count": len(self.polls),
                "polled_count": sum(1 for poll in self.polls if poll.status == "polled"),
                "skipped_count": sum(1 for poll in self.polls if poll.status == "skipped"),
                "blocked_count": sum(1 for poll in self.polls if poll.status == "blocked"),
                "failed_count": sum(1 for poll in self.polls if poll.status == "failed"),
                "dropped_batch_count": sum(1 for poll in self.polls if poll.status == "failed"),
                "snapshot_count": len(snapshots),
                "trend_window_count": trend_window_count,
            },
            "score": {
                "mutation_schedule_count": sum(1 for poll in self.polls if poll.status == "polled" and any(_is_mutation_capability(reason) for reason in poll.reasons)),
                "tight_loop_risk_count": sum(1 for poll in self.polls if poll.status in {"failed", "skipped"} and poll.next_safe_retry_seconds <= 0),
            },
            "boundary": dict(_BOUNDARY),
            "polls": [poll.to_dict() for poll in self.polls],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class PollingRuntime:
    def run_fixture(self, jobs_path: str | Path, readiness_path: str | Path, *, ticks: int = 1) -> PollingRuntimeReport:
        jobs = _load_jobs(jobs_path)
        readiness_payload = evaluate_connector_readiness_fixture(readiness_path).to_dict()
        readiness_by_source = {str(item.get("source")): item for item in _sequence(readiness_payload.get("sources", ())) if isinstance(item, Mapping)}
        polls: list[PollResult] = []
        for tick in range(1, max(1, ticks) + 1):
            for job in jobs:
                polls.append(self._poll_job(job, readiness_by_source, tick=tick))
        return PollingRuntimeReport(jobs=jobs, polls=tuple(polls))

    def _poll_job(self, job: PollingJob, readiness_by_source: Mapping[str, Mapping[str, Any]], *, tick: int) -> PollResult:
        if not job.enabled:
            return PollResult(job.id, job.source, "skipped", ("job_disabled",), tick, next_safe_retry_seconds=job.interval_seconds)
        if job.has_mutation_request:
            return PollResult(job.id, job.source, "blocked", ("mutation_request_blocked",), tick, next_safe_retry_seconds=0)
        readiness = readiness_by_source.get(job.source)
        if readiness is None:
            return PollResult(job.id, job.source, "skipped", ("readiness_missing",), tick, next_safe_retry_seconds=300)
        readiness_state = str(readiness.get("state", "unavailable"))
        if readiness_state == "blocked":
            return PollResult(job.id, job.source, "blocked", ("readiness_blocked",), tick, next_safe_retry_seconds=0)
        if readiness_state != "ready":
            retry = int(readiness.get("next_safe_retry_seconds", 300) or 300)
            reasons = (f"readiness_{readiness_state}", *tuple(str(item) for item in _sequence(readiness.get("reasons", ()))))
            return PollResult(job.id, job.source, "skipped", reasons, tick, next_safe_retry_seconds=retry)
        if job.simulate in {"timeout", "rate_limit", "malformed"}:
            return PollResult(job.id, job.source, "failed", (job.simulate,), tick, next_safe_retry_seconds=120 if job.simulate != "malformed" else 180)
        try:
            snapshot = adapt_telemetry_fixture(job.source, job.fixture_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return PollResult(job.id, job.source, "failed", ("adapter_error", exc.__class__.__name__), tick, next_safe_retry_seconds=180)
        return PollResult(job.id, job.source, "polled", ("fixture_transport", "p27_readiness_ready"), tick, snapshot=snapshot, trend_window_count=len(snapshot.to_trend_windows()))


def run_polling_fixture(jobs_path: str | Path, readiness_path: str | Path, *, ticks: int = 1) -> PollingRuntimeReport:
    return PollingRuntime().run_fixture(jobs_path, readiness_path, ticks=ticks)


def render_polling_runtime_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), Mapping) else {}
    score = payload.get("score", {}) if isinstance(payload.get("score"), Mapping) else {}
    lines = [
        "# OpsCat Read-only Polling Runtime Report",
        "",
        "Boundary: fixture/local transport only; P27 readiness required; P26 adapters only; "
        "no live API calls; no live writes; no remediation execution; does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Jobs: {summary.get('job_count')}",
        f"- Polled: {summary.get('polled_count')}",
        f"- Skipped: {summary.get('skipped_count')}",
        f"- Blocked: {summary.get('blocked_count')}",
        f"- Failed: {summary.get('failed_count')}",
        f"- Snapshots: {summary.get('snapshot_count')}",
        f"- Trend windows: {summary.get('trend_window_count')}",
        "",
        "## Score",
        f"- mutation_schedule_count: {score.get('mutation_schedule_count')}",
        f"- tight_loop_risk_count: {score.get('tight_loop_risk_count')}",
        "",
        "## Polls",
    ]
    polls = payload.get("polls", [])
    if isinstance(polls, Sequence) and not isinstance(polls, (str, bytes, bytearray)):
        for poll in polls:
            if isinstance(poll, Mapping):
                reasons = ",".join(str(item) for item in _sequence(poll.get("reasons", ())))
                lines.append(f"- `{poll.get('job_id')}` source={poll.get('source')} status={poll.get('status')} retry={poll.get('next_safe_retry_seconds')} reasons={reasons}")
    return "\n".join(lines) + "\n"


def write_polling_runtime_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_polling_runtime_markdown(payload), encoding="utf-8")


def _load_jobs(path: str | Path) -> tuple[PollingJob, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("polling fixture must be an object")
    return tuple(PollingJob.from_dict(item, index=index) for index, item in enumerate(_sequence(data.get("jobs", ())), start=1) if isinstance(item, Mapping))


def _is_mutation_capability(capability: str) -> bool:
    lowered = capability.lower()
    return any(marker in lowered for marker in _MUTATION_MARKERS)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
