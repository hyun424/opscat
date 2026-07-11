"""P109 remediation outcome reducer for imported MicroRemed results."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.microremed_result_adapter import ImportedMicroRemedBundle

_OUTCOMES = ("verified_recovery", "harmful", "unnecessary", "no_effect", "unverified")


@dataclass(frozen=True)
class RemediationOutcomeBenchmarkResult:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


def run_remediation_outcome_benchmark(
    bundle_path: str | Path,
    *,
    trusted_signers: Sequence[Mapping[str, str]] | None = None,
) -> RemediationOutcomeBenchmarkResult:
    imported = ImportedMicroRemedBundle.from_path(bundle_path, trusted_signers=trusted_signers)
    imported_payload = imported.to_dict()
    runs = list(imported_payload["runs"])
    eligible_runs = [run for run in runs if run["eligible"]]
    eligible_attempts = [attempt for run in eligible_runs for attempt in run["attempts"]]
    verified_runs = [run for run in eligible_runs if run["outcome"] == "verified_recovery"]
    harmful_runs = [run for run in eligible_runs if run["outcome"] == "harmful"]
    unnecessary_runs = [run for run in eligible_runs if run["outcome"] == "unnecessary"]
    first_attempt_recoveries = [run for run in verified_runs if run["attempt_count"] == 1]
    successful_attempts = [attempt for run in verified_runs for attempt in run["attempts"] if attempt["action_kind"] != "noop" and not attempt["safety_violation"]]
    recovery_durations = [int(run["recovery_duration_seconds"]) for run in verified_runs if run.get("recovery_duration_seconds") is not None]
    outcome_counts = Counter(str(run["outcome"]) for run in runs)
    for outcome in _OUTCOMES:
        outcome_counts.setdefault(outcome, 0)

    metrics = {
        "verified_recovery_rate": _metric(len(verified_runs), len(eligible_runs)),
        "first_attempt_recovery_rate": _metric(len(first_attempt_recoveries), len(eligible_runs)),
        "attempt_success_rate": _metric(len(successful_attempts), len(eligible_attempts)),
        "mean_attempts": _metric(sum(int(run["attempt_count"]) for run in eligible_runs), len(eligible_runs)),
        "mean_recovery_duration_seconds": _metric(sum(recovery_durations), len(recovery_durations)),
        "harmful_action_rate": _metric(len(harmful_runs), len(eligible_runs)),
        "unnecessary_action_rate": _metric(len(unnecessary_runs), len(eligible_runs)),
    }
    payload = {
        "schema_version": "p109.remediation_outcome_benchmark.v1",
        "scored": bool(eligible_runs),
        "release_evidence": False,
        "fixture_results_smoke_only": imported.smoke_only,
        "external_execution": imported.external_execution,
        "release_trusted": imported_payload["release_trusted"],
        "eligible_run_count": len(eligible_runs),
        "run_count": len(runs),
        "outcome_counts": {outcome: int(outcome_counts[outcome]) for outcome in _OUTCOMES},
        "metrics": metrics,
        "by_system": _group_metrics(eligible_runs, "system"),
        "by_fault_family": _group_metrics(eligible_runs, "fault_family"),
        "by_difficulty": _group_metrics(eligible_runs, "difficulty"),
        "runs": runs,
        "authority": imported_payload["authority"],
    }
    return RemediationOutcomeBenchmarkResult(payload)


def _group_metrics(runs: Iterable[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[str(run[key])].append(run)
    return {
        group: {
            "run_count": len(items),
            "verified_recovery_rate": _metric(sum(item["outcome"] == "verified_recovery" for item in items), len(items)),
            "harmful_action_rate": _metric(sum(item["outcome"] == "harmful" for item in items), len(items)),
            "unnecessary_action_rate": _metric(sum(item["outcome"] == "unnecessary" for item in items), len(items)),
        }
        for group, items in sorted(grouped.items())
    }


def _metric(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": None if denominator == 0 else numerator / denominator,
        "status": "unevaluable" if denominator == 0 else "scored",
    }
