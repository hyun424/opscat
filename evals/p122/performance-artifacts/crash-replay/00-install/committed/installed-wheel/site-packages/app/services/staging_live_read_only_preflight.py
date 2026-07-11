"""P63 staging live read-only preflight runner.

Default execution is no-live: it evaluates whether staging GET checks are eligible
but performs zero network calls. A call is attempted only when live_staging,
manual approval, a safe injected transport, P62 readiness, allowlisted host, and
GET-only method gates all pass.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.redaction import redact_value
from app.services.staging_read_only_connector_contract import run_staging_read_only_connector_contract_fixture

_MAX_TIMEOUT_MS = 5_000
_REMOTE_PREFIXES = ("http://", "https://", "s3://", "gs://", "az://", "ftp://")
_BOUNDARY_BASE: dict[str, bool] = {
    "default_no_live_mode": True,
    "staging_preflight_only": True,
    "read_only_get_only": True,
    "real_network_required_for_tests": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "action_execution_enabled": False,
    "unattended_production_operation_claimed": False,
}


@dataclass(frozen=True)
class StagingLivePreflightCheck:
    id: str
    connector_id: str
    method: str
    url: str
    timeout_ms: int
    expected_status: int
    mock_status: int
    response_shape: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StagingLivePreflightCheck:
        return cls(
            id=str(data.get("id", "preflight-check")),
            connector_id=str(data.get("connector_id", "")),
            method=str(data.get("method", "GET")).upper(),
            url=str(data.get("url", "")),
            timeout_ms=int(data.get("timeout_ms", 1_000) or 1_000),
            expected_status=int(data.get("expected_status", 200) or 200),
            mock_status=int(data.get("mock_status", 200) or 200),
            response_shape=_mapping(data.get("response_shape")),
        )

    @property
    def host(self) -> str:
        return str(urlparse(self.url).hostname or "")


@dataclass(frozen=True)
class StagingLivePreflightPlan:
    contract_manifest: Path
    allowed_hosts: tuple[str, ...]
    checks: tuple[StagingLivePreflightCheck, ...]


@dataclass(frozen=True)
class StagingReadOnlyTransportResponse:
    status_code: int
    body_shape: Mapping[str, Any]
    elapsed_ms: int


@dataclass
class MockStagingReadOnlyTransport:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def get(self, check: StagingLivePreflightCheck) -> StagingReadOnlyTransportResponse:
        call = {
            "check_id": check.id,
            "method": "GET",
            "url": check.url,
            "host": check.host,
            "timeout_ms": check.timeout_ms,
        }
        self.calls.append(call)
        return StagingReadOnlyTransportResponse(status_code=check.mock_status, body_shape=check.response_shape, elapsed_ms=min(check.timeout_ms, 50))


@dataclass(frozen=True)
class StagingLivePreflightResult:
    check: StagingLivePreflightCheck
    status: str
    reasons: tuple[str, ...]
    connector_status: str
    provider: str
    environment: str
    allowlisted_host: bool
    p62_ready: bool
    manual_approval_required: bool
    manual_approval_present: bool
    response_status: int | None = None
    elapsed_ms: int | None = None

    @property
    def eligible(self) -> bool:
        return self.p62_ready and self.allowlisted_host and self.check.method == "GET" and self.check.timeout_ms <= _MAX_TIMEOUT_MS and self.environment == "staging"

    @property
    def attempted(self) -> bool:
        return self.status in {"successful", "failed"}

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "check_id": self.check.id,
            "connector_id": self.check.connector_id,
            "provider": self.provider,
            "environment": self.environment,
            "method": self.check.method,
            "url_host": self.check.host,
            "timeout_ms": self.check.timeout_ms,
            "expected_status": self.check.expected_status,
            "status": self.status,
            "reasons": list(self.reasons),
            "connector_status": self.connector_status,
            "eligible": self.eligible,
            "allowlisted_host": self.allowlisted_host,
            "manual_approval_required": self.manual_approval_required,
            "manual_approval_present": self.manual_approval_present,
            "response_status": self.response_status,
            "elapsed_ms": self.elapsed_ms,
            "live_api_called": self.attempted,
            "production_mutation_count": 0,
            "action_execution_count": 0,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class StagingLiveReadOnlyPreflightReport:
    plan: StagingLivePreflightPlan
    results: tuple[StagingLivePreflightResult, ...]
    live_staging: bool
    manual_approval: bool
    mock_transport_call_count: int

    def to_dict(self) -> dict[str, Any]:
        eligible = tuple(result for result in self.results if result.eligible)
        attempted = tuple(result for result in self.results if result.attempted)
        successful = tuple(result for result in self.results if result.status == "successful")
        blocked = tuple(result for result in self.results if result.status == "blocked")
        non_get = tuple(result for result in self.results if result.check.method != "GET")
        manual_missing = tuple(result for result in self.results if "manual_approval_missing" in result.reasons)
        payload = {
            "summary": {
                "check_count": len(self.results),
                "eligible_check_count": len(eligible),
                "attempted_check_count": len(attempted),
                "successful_check_count": len(successful),
                "blocked_check_count": len(blocked),
                "passed": _passed(self.live_staging, eligible, attempted, successful),
            },
            "score": {
                "live_api_call_count": len(attempted),
                "mock_transport_call_count": self.mock_transport_call_count,
                "production_mutation_count": 0,
                "action_execution_count": 0,
                "non_get_check_count": len(non_get),
                "manual_approval_missing_count": len(manual_missing),
            },
            "boundary": {
                **_BOUNDARY_BASE,
                "default_no_live_mode": not self.live_staging,
                "live_staging_enabled": self.live_staging,
            },
            "operator_handoff": _operator_handoff(self.live_staging, self.manual_approval, eligible, blocked),
            "checks": [result.to_dict() for result in self.results],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def load_staging_live_read_only_preflight_plan(path: str | Path) -> StagingLivePreflightPlan:
    local_path = _ensure_local_path(path)
    data = json.loads(local_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("staging live preflight manifest must be an object")
    checks = tuple(StagingLivePreflightCheck.from_dict(item) for item in _sequence(data.get("checks", ())) if isinstance(item, Mapping))
    return StagingLivePreflightPlan(
        contract_manifest=Path(str(data.get("contract_manifest", "evals/staging/p62_staging_connector_contract.json"))),
        allowed_hosts=tuple(str(item) for item in _sequence(data.get("allowed_hosts", ()))),
        checks=checks,
    )


def run_staging_live_read_only_preflight_fixture(
    path: str | Path,
    *,
    live_staging: bool = False,
    manual_approval: bool = False,
    transport: MockStagingReadOnlyTransport | None = None,
) -> StagingLiveReadOnlyPreflightReport:
    plan = load_staging_live_read_only_preflight_plan(path)
    contract_payload = run_staging_read_only_connector_contract_fixture(plan.contract_manifest).to_dict()
    connectors = {
        str(item.get("connector_id")): item
        for item in _sequence(contract_payload.get("connectors", ()))
        if isinstance(item, Mapping)
    }
    results: list[StagingLivePreflightResult] = []
    for check in plan.checks:
        result = _evaluate_check(check, connectors.get(check.connector_id, {}), plan.allowed_hosts, live_staging, manual_approval, transport)
        results.append(result)
    call_count = len(transport.calls) if transport is not None else 0
    return StagingLiveReadOnlyPreflightReport(plan=plan, results=tuple(results), live_staging=live_staging, manual_approval=manual_approval, mock_transport_call_count=call_count)


def render_staging_live_read_only_preflight_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    boundary = _mapping(payload.get("boundary"))
    handoff = _mapping(payload.get("operator_handoff"))
    lines = [
        "# OpsCat Staging Live Read-only Preflight",
        "",
        "Default no-live mode evaluates eligibility but performs zero network/API calls unless live staging and manual approval are explicit.",
        "",
        "## Summary",
        f"- Checks: {summary.get('check_count')}",
        f"- Eligible checks: {summary.get('eligible_check_count')}",
        f"- Attempted checks: {summary.get('attempted_check_count')}",
        f"- Successful checks: {summary.get('successful_check_count')}",
        f"- Blocked checks: {summary.get('blocked_check_count')}",
        "",
        "## Safety counters",
        f"- live_api_call_count: {score.get('live_api_call_count')}",
        f"- mock_transport_call_count: {score.get('mock_transport_call_count')}",
        f"- production_mutation_count: {score.get('production_mutation_count')}",
        f"- action_execution_count: {score.get('action_execution_count')}",
        f"- non_get_check_count: {score.get('non_get_check_count')}",
        f"- manual_approval_missing_count: {score.get('manual_approval_missing_count')}",
        "",
        "## Boundary",
        f"- live_staging_enabled: {boundary.get('live_staging_enabled')}",
        f"- default_no_live_mode: {boundary.get('default_no_live_mode')}",
        "",
        "## Operator handoff",
        f"- Next step: {handoff.get('next_step')}",
        "",
        "## Checks",
    ]
    for item in _sequence(payload.get("checks", ())):
        if isinstance(item, Mapping):
            reasons = ",".join(str(reason) for reason in _sequence(item.get("reasons", ())))
            lines.append(f"- `{item.get('check_id')}` connector={item.get('connector_id')} status={item.get('status')} reasons={reasons}")
    return "\n".join(lines) + "\n"


def write_staging_live_read_only_preflight_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_staging_live_read_only_preflight_markdown(payload), encoding="utf-8")


def _evaluate_check(
    check: StagingLivePreflightCheck,
    connector: Mapping[str, Any],
    allowed_hosts: Sequence[str],
    live_staging: bool,
    manual_approval: bool,
    transport: MockStagingReadOnlyTransport | None,
) -> StagingLivePreflightResult:
    connector_status = str(connector.get("status", "missing"))
    provider = str(connector.get("provider", "unknown"))
    environment = str(connector.get("environment", "unknown"))
    p62_ready = connector_status == "ready"
    allowlisted_host = check.host in set(allowed_hosts)
    base_reasons = _base_reasons(check, p62_ready, allowlisted_host, environment)
    eligible = not base_reasons

    if not eligible:
        return StagingLivePreflightResult(
            check=check,
            status="blocked",
            reasons=base_reasons,
            connector_status=connector_status,
            provider=provider,
            environment=environment,
            allowlisted_host=allowlisted_host,
            p62_ready=p62_ready,
            manual_approval_required=True,
            manual_approval_present=manual_approval,
        )
    if not live_staging:
        return StagingLivePreflightResult(
            check=check,
            status="eligible_no_live",
            reasons=("default_no_live_mode",),
            connector_status=connector_status,
            provider=provider,
            environment=environment,
            allowlisted_host=allowlisted_host,
            p62_ready=p62_ready,
            manual_approval_required=True,
            manual_approval_present=manual_approval,
        )
    if not manual_approval:
        return StagingLivePreflightResult(
            check=check,
            status="blocked",
            reasons=("manual_approval_missing",),
            connector_status=connector_status,
            provider=provider,
            environment=environment,
            allowlisted_host=allowlisted_host,
            p62_ready=p62_ready,
            manual_approval_required=True,
            manual_approval_present=False,
        )
    if transport is None:
        return StagingLivePreflightResult(
            check=check,
            status="blocked",
            reasons=("safe_transport_missing",),
            connector_status=connector_status,
            provider=provider,
            environment=environment,
            allowlisted_host=allowlisted_host,
            p62_ready=p62_ready,
            manual_approval_required=True,
            manual_approval_present=True,
        )
    response = transport.get(check)
    status = "successful" if response.status_code == check.expected_status else "failed"
    reason = "read_only_get_preflight_success" if status == "successful" else "unexpected_status_code"
    return StagingLivePreflightResult(
        check=check,
        status=status,
        reasons=(reason,),
        connector_status=connector_status,
        provider=provider,
        environment=environment,
        allowlisted_host=allowlisted_host,
        p62_ready=p62_ready,
        manual_approval_required=True,
        manual_approval_present=True,
        response_status=response.status_code,
        elapsed_ms=response.elapsed_ms,
    )


def _base_reasons(check: StagingLivePreflightCheck, p62_ready: bool, allowlisted_host: bool, environment: str) -> tuple[str, ...]:
    reasons: list[str] = []
    if not p62_ready:
        reasons.append("p62_connector_not_ready")
    if check.method != "GET":
        reasons.append("non_get_method")
    if not allowlisted_host:
        reasons.append("host_not_allowlisted")
    if not check.url.lower().startswith("https://"):
        reasons.append("non_https_url")
    if check.timeout_ms <= 0 or check.timeout_ms > _MAX_TIMEOUT_MS:
        reasons.append("unsafe_timeout_budget")
    if environment != "staging":
        reasons.append("non_staging_environment")
    return tuple(reasons)


def _operator_handoff(live_staging: bool, manual_approval: bool, eligible: Sequence[StagingLivePreflightResult], blocked: Sequence[StagingLivePreflightResult]) -> dict[str, Any]:
    if not live_staging:
        next_step = "rerun with explicit live staging flag after manual approval and read-only credentials"
    elif not manual_approval:
        next_step = "collect manual approval before live staging GET preflight"
    else:
        next_step = "review successful staging GET preflight results before enabling polling"
    return {
        "eligible_checks": [result.check.id for result in eligible],
        "blocked_checks": [result.check.id for result in blocked],
        "next_step": next_step,
    }


def _passed(
    live_staging: bool,
    eligible: Sequence[StagingLivePreflightResult],
    attempted: Sequence[StagingLivePreflightResult],
    successful: Sequence[StagingLivePreflightResult],
) -> bool:
    if not live_staging:
        return len(eligible) >= 3 and len(attempted) == 0
    return len(eligible) >= 3 and len(successful) == len(attempted)


def _ensure_local_path(path: str | Path) -> Path:
    value = str(path)
    if value.lower().startswith(_REMOTE_PREFIXES):
        raise ValueError("remote staging preflight manifests are not allowed for normal verification")
    local_path = Path(value)
    if not local_path.exists():
        raise FileNotFoundError(f"staging preflight manifest does not exist: {local_path}")
    return local_path


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
