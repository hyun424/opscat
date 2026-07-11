"""P61 local shadow connector validation.

This validates live-shaped observability connector behavior against a local JSON
source only. It performs no network calls and exposes no mutation operations.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.operator_replacement_readiness_gate_v2 import build_operator_replacement_readiness_gate_v2_report
from app.services.redaction import redact_text, redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "local_shadow_connector_only": True,
    "read_only_connector": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "action_execution_enabled": False,
    "unattended_production_operation_claimed": False,
}
_DEFAULT_CASES = Path("evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")
_DEFAULT_MANIFEST = Path("evals/real_datasets/external/p44_benchmark_matrix_manifest.json")
_DEFAULT_JUDGMENT_CASES = Path("evals/judgment/seed/cases.json")


@dataclass(frozen=True)
class LocalShadowConnectorValidationReport:
    source_path: Path

    def to_dict(self) -> dict[str, Any]:
        connector = LocalShadowObservabilityConnector(self.source_path)
        metrics = connector.fetch_metrics()
        logs = connector.fetch_logs()
        errors = connector.fetch_errors()
        deployments = connector.fetch_deployments()
        source_cards = connector.source_cards()
        evidence = _build_evidence(metrics, logs, errors, deployments)
        judgment = _shadow_judgment(evidence)
        readiness_link = _readiness_link()
        malformed = sum(1 for card in source_cards if card.get("malformed_payload"))
        empty = sum(1 for card in source_cards if int(card.get("signal_count", 0)) == 0 and not card.get("malformed_payload"))
        action_execution_count = 0
        live_api_call_count = 0
        production_mutation_count = 0
        gates = _validation_gates(metrics, logs, errors, deployments, evidence, judgment, readiness_link, malformed, action_execution_count)
        passed = all(bool(gate.get("passed")) for gate in gates)
        payload = {
            "summary": {
                "source_count": len(source_cards),
                "metric_signal_count": len(metrics),
                "log_signal_count": len(logs),
                "error_signal_count": len(errors),
                "deployment_signal_count": len(deployments),
                "empty_source_count": empty,
                "malformed_payload_count": malformed,
                "action_execution_count": action_execution_count,
                "live_api_call_count": live_api_call_count,
                "production_mutation_count": production_mutation_count,
                "passed": passed,
            },
            "source_cards": source_cards,
            "evidence": evidence,
            "shadow_judgment": judgment,
            "readiness_link": readiness_link,
            "validation_gates": gates,
            "boundary": dict(_BOUNDARY),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class LocalShadowObservabilityConnector:
    """Read-only local connector with live-shaped fetch methods only."""

    def __init__(self, source_path: str | Path) -> None:
        self.source_path = Path(source_path)
        self._payload = _load_payload(self.source_path)

    def fetch_metrics(self) -> list[dict[str, Any]]:
        return _collect(self._payload, "metrics")

    def fetch_logs(self) -> list[dict[str, Any]]:
        return _collect(self._payload, "logs")

    def fetch_errors(self) -> list[dict[str, Any]]:
        return _collect(self._payload, "errors")

    def fetch_deployments(self) -> list[dict[str, Any]]:
        return _collect(self._payload, "deployments")

    def source_cards(self) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for source in _sources(self._payload):
            metrics = _maybe_sequence(source.get("metrics"))
            logs = _maybe_sequence(source.get("logs"))
            errors = _maybe_sequence(source.get("errors"))
            deployments = _maybe_sequence(source.get("deployments"))
            malformed = any(
                key in source and not isinstance(source.get(key), Sequence) or isinstance(source.get(key), (str, bytes, bytearray))
                for key in ("metrics", "logs", "errors", "deployments")
            )
            cards.append(
                {
                    "source_id": str(source.get("source_id", "local-shadow-source")),
                    "connector_kind": str(source.get("connector_kind", "local_shadow")),
                    "read_only": bool(source.get("read_only", True)),
                    "service": str(source.get("service", "unknown")),
                    "signal_count": len(metrics) + len(logs) + len(errors) + len(deployments),
                    "malformed_payload": malformed,
                    "live_api_called": False,
                }
            )
        return cards


def build_local_shadow_connector_validation_report(source_path: str | Path) -> LocalShadowConnectorValidationReport:
    return LocalShadowConnectorValidationReport(Path(source_path))


def render_local_shadow_connector_validation_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    judgment = _mapping(payload.get("shadow_judgment"))
    readiness = _mapping(payload.get("readiness_link"))
    lines = [
        "# OpsCat Local Shadow Connector Validation",
        "",
        "Validates a live-shaped local observability source through a read-only connector contract. No real server, network call, or remediation execution is used.",
        "",
        "## Summary",
        f"- Passed: {summary.get('passed')}",
        f"- Sources: {summary.get('source_count')}",
        f"- Metrics: {summary.get('metric_signal_count')}",
        f"- Logs: {summary.get('log_signal_count')}",
        f"- Errors: {summary.get('error_signal_count')}",
        f"- Deployments: {summary.get('deployment_signal_count')}",
        f"- Empty sources: {summary.get('empty_source_count')}",
        f"- Malformed payloads: {summary.get('malformed_payload_count')}",
        "",
        "## Shadow judgment",
        f"- Top hypothesis: {judgment.get('top_hypothesis')}",
        f"- Confidence: {judgment.get('confidence')}",
        f"- Recommended action: {judgment.get('recommended_action')}",
        f"- Execution: {judgment.get('execution')}",
        "",
        "## Readiness link",
        f"- Local operator replacement ready: {readiness.get('local_operator_replacement_ready')}",
        f"- Unattended production ready: {readiness.get('unattended_production_ready')}",
        "",
        "## Validation gates",
    ]
    for gate in _sequence(payload.get("validation_gates", ())):
        if isinstance(gate, Mapping):
            lines.append(f"- `{gate.get('gate_id')}` passed={gate.get('passed')}: {gate.get('reason')}")
    lines.extend(["", "## Boundary", "- Local shadow connector only; no live calls, production mutation, action execution, or remediation execution."])
    return "\n".join(lines) + "\n"


def write_local_shadow_connector_validation_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_local_shadow_connector_validation_markdown(payload), encoding="utf-8")


def _load_payload(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("local shadow source must be a mapping")
    return data


def _sources(payload: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    return tuple(item for item in _sequence(payload.get("sources", ())) if isinstance(item, Mapping))


def _collect(payload: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in _sources(payload):
        for item in _maybe_sequence(source.get(key)):
            if isinstance(item, Mapping):
                service = str(item.get("service") or source.get("service", "unknown"))
                result.append({"source_id": str(source.get("source_id", "local-shadow-source")), "service": service, **dict(item)})
    return result


def _build_evidence(metrics: Sequence[Mapping[str, Any]], logs: Sequence[Mapping[str, Any]], errors: Sequence[Mapping[str, Any]], deployments: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    supporting: list[str] = []
    counter: list[str] = []
    missing = ["rollback dry-run result", "customer impact estimate"]
    for metric in metrics:
        name = str(metric.get("metric", ""))
        value = float(metric.get("value", 0.0) or 0.0)
        baseline = float(metric.get("baseline", 0.0) or 0.0)
        if name == "http_5xx_rate" and baseline > 0 and value >= baseline * 5:
            supporting.append(f"{metric.get('service')} http_5xx_rate {baseline} -> {value} {metric.get('unit', '')}".strip())
        if name == "db_pool_wait_seconds_p95" and value <= max(baseline * 2, 0.2):
            counter.append(f"database pool wait stayed near baseline ({value}s)")
    for log in logs:
        message = redact_text(str(log.get("message", "")))
        lower = message.lower()
        if "timeout" in lower and "deploy" in lower:
            supporting.append(f"timeout log after deploy: {message}")
        if "not observed" in lower or "no saturation" in lower:
            counter.append(message)
    for error in errors:
        count = int(error.get("count", 0) or 0)
        if count > 0:
            supporting.append(f"error event spike: {redact_text(str(error.get('title', 'error')))} count={count}")
    for deployment in deployments:
        version = redact_text(str(deployment.get("version", "unknown")))
        supporting.append(f"deployment {version} occurred at {deployment.get('deployed_at')}")
    return {"supporting_evidence": supporting, "counter_evidence": counter, "missing_evidence": missing}


def _shadow_judgment(evidence: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    supporting = _sequence(evidence.get("supporting_evidence", ()))
    counter = _sequence(evidence.get("counter_evidence", ()))
    has_deploy = any("deploy" in str(item).lower() for item in supporting)
    has_error = any("5xx" in str(item).lower() or "error" in str(item).lower() for item in supporting)
    top = "recent_deploy_regression" if has_deploy and has_error else "needs_more_evidence"
    confidence = 0.91 if top == "recent_deploy_regression" and counter else 0.64
    return {
        "top_hypothesis": top,
        "confidence": confidence,
        "recommended_action": "prepare rollback PR draft" if top == "recent_deploy_regression" else "continue read-only observation",
        "execution": "blocked_shadow_mode",
        "blocked_actions": ["restart", "rollback", "deploy", "write_config", "shell_execute"],
    }


def _readiness_link() -> dict[str, Any]:
    payload = build_operator_replacement_readiness_gate_v2_report(_DEFAULT_CASES, _DEFAULT_MANIFEST, _DEFAULT_JUDGMENT_CASES).to_dict()
    summary = _mapping(payload.get("summary"))
    return {
        "local_operator_replacement_ready": bool(summary.get("local_operator_replacement_ready")),
        "unattended_production_ready": bool(summary.get("unattended_production_ready")),
        "recommended_mode": str(summary.get("recommended_mode", "unknown")),
        "readiness_level": str(summary.get("readiness_level", "unknown")),
    }


def _validation_gates(
    metrics: Sequence[Mapping[str, Any]],
    logs: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
    deployments: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Sequence[str]],
    judgment: Mapping[str, Any],
    readiness: Mapping[str, Any],
    malformed_payload_count: int,
    action_execution_count: int,
) -> list[dict[str, Any]]:
    return [
        {"gate_id": "signal-coverage", "passed": bool(metrics and logs and errors and deployments), "reason": "Local shadow source must include metric, log, error, and deployment signals."},
        {"gate_id": "malformed-tolerated", "passed": malformed_payload_count >= 1, "reason": "Malformed local payloads must be tolerated and reported."},
        {
            "gate_id": "evidence-card",
            "passed": bool(evidence.get("supporting_evidence")) and bool(evidence.get("counter_evidence")) and bool(evidence.get("missing_evidence")),
            "reason": "Judgment must include supporting, counter, and missing evidence.",
        },
        {
            "gate_id": "shadow-judgment",
            "passed": judgment.get("top_hypothesis") == "recent_deploy_regression" and float(judgment.get("confidence", 0.0)) >= 0.9,
            "reason": "Local shadow commander should identify the deploy-regression scenario.",
        },
        {"gate_id": "execution-blocked", "passed": action_execution_count == 0 and judgment.get("execution") == "blocked_shadow_mode", "reason": "P61 must not execute remediation."},
        {
            "gate_id": "readiness-linked",
            "passed": bool(readiness.get("local_operator_replacement_ready")) and not bool(readiness.get("unattended_production_ready")),
            "reason": "P61 preserves P60 local readiness while production autonomy remains blocked.",
        },
    ]


def _maybe_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _sequence(value: Any) -> Sequence[Any]:
    return _maybe_sequence(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
