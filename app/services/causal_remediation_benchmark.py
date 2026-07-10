"""P97 causal remediation benchmark with an isolated loopback fault lab.

This module does not execute production remediation.  It creates an ephemeral
HTTP workload on 127.0.0.1, mutates only an in-memory lab state through a closed
action registry, and compares three intervention arms from the same initial
case/seed fingerprint.
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol, Self

from app.services.redaction import redact_value

_BOUNDARY: dict[str, bool] = {
    "synthetic_local_fault_lab": True,
    "loopback_only": True,
    "external_network_enabled": False,
    "filesystem_mutation_enabled": False,
    "subprocess_execution_enabled": False,
    "credentials_enabled": False,
    "production_mutation_enabled": False,
    "arbitrary_action_enabled": False,
    "unattended_production_operation_claimed": False,
}

_VARIANTS: tuple[tuple[str, str], ...] = (
    ("obvious", "development"),
    ("noisy_signal", "development"),
    ("first_action_ineffective", "development"),
    ("partial_recovery", "development"),
    ("peak_load", "development"),
    ("missing_telemetry", "development"),
    ("conflicting_telemetry", "validation"),
    ("natural_recovery", "validation"),
    ("human_required", "blind"),
    ("compound", "blind"),
)


@dataclass(frozen=True)
class _FamilySpec:
    name: str
    symptom: str
    evidence: tuple[str, ...]
    primary_action: str
    secondary_action: str


_FAMILIES: tuple[_FamilySpec, ...] = (
    _FamilySpec("application_runtime", "process crash loop and rising 5xx", ("process_restart_count_high", "single_revision_affected"), "restart_service", "rollback_deploy"),
    _FamilySpec("deploy_config", "errors started after a revision change", ("deployment_revision_changed", "rollback_candidate_available"), "rollback_deploy", "restart_service"),
    _FamilySpec("kubernetes_infra", "unhealthy instance and node pressure", ("readiness_failures", "node_pressure_correlated"), "replace_unhealthy_instance", "shed_load"),
    _FamilySpec("database", "pool wait and query latency saturation", ("db_pool_wait_high", "database_connections_saturated"), "recycle_connection_pool", "shed_load"),
    _FamilySpec("queue", "consumer lag grows while producers remain stable", ("queue_lag_growing", "consumer_heartbeat_stale"), "restart_consumer", "scale_consumer"),
    _FamilySpec("cache", "cache errors correlate with stale responses", ("cache_error_rate_high", "origin_healthy"), "bypass_cache", "evict_bad_cache_key"),
    _FamilySpec("network_dependency", "provider timeouts dominate request failures", ("dependency_timeout_rate_high", "local_resources_healthy"), "enable_dependency_fallback", "shed_load"),
    _FamilySpec(
        "security_auth",
        "service authentication failures after credential drift",
        ("credential_version_mismatch", "privileged_scope_required"),
        "rotate_service_credentials",
        "restart_service",
    ),
    _FamilySpec("observability", "telemetry pipeline stopped reporting", ("telemetry_gap_detected", "workload_probe_available"), "restore_telemetry_pipeline", "restart_service"),
    _FamilySpec("business_correctness", "successful responses contain incorrect results", ("business_invariant_failed", "feature_flag_recently_changed"), "disable_faulty_feature", "rollback_deploy"),
    _FamilySpec("natural_recovery", "short transient burst is already decaying", ("transient_recovery_pattern", "error_slope_negative"), "observe_only", "restart_service"),
    _FamilySpec(
        "compound_failure",
        "simultaneous saturation and dependency errors",
        ("multiple_failure_domains", "dependency_timeout_rate_high", "db_pool_wait_high"),
        "shed_load",
        "enable_dependency_fallback",
    ),
)

_ACTION_REGISTRY: frozenset[str] = frozenset(
    {
        "restart_service",
        "rollback_deploy",
        "replace_unhealthy_instance",
        "shed_load",
        "recycle_connection_pool",
        "restart_consumer",
        "scale_consumer",
        "bypass_cache",
        "evict_bad_cache_key",
        "enable_dependency_fallback",
        "rotate_service_credentials",
        "restore_telemetry_pipeline",
        "disable_faulty_feature",
        "observe_only",
    }
)


@dataclass(frozen=True)
class CausalScenario:
    case_id: str
    family: str
    variant: str
    split: str
    symptom: str
    visible_evidence: tuple[str, ...]
    runbook_actions: tuple[str, ...]
    required_actions: tuple[str, ...]
    harmful_actions: tuple[str, ...]
    spontaneous_recovery: bool
    human_required: bool
    telemetry_coverage: float
    initial_availability: float
    initial_latency_ms: float
    initial_backlog: float
    initial_correctness: float


@dataclass(frozen=True)
class CausalDecision:
    route: str
    actions: tuple[str, ...]
    rationale: str
    recovery_claimed: bool = False


@dataclass(frozen=True)
class LabMeasurement:
    availability: float
    latency_ms: float
    backlog: float
    correctness: float
    telemetry_coverage: float
    collateral_regressions: int
    http_request_count: int
    utility: float
    recovered: bool
    verifiable: bool


@dataclass(frozen=True)
class LabActionResult:
    action: str
    applied: bool
    effect: str


class LabActionBlocked(ValueError):
    """Raised when a caller requests an action outside the closed lab registry."""


class ActionSelector(Protocol):
    def select(self, observation: Mapping[str, Any]) -> CausalDecision: ...


@dataclass
class _LabState:
    scenario: CausalScenario
    seed: int
    availability: float
    latency_ms: float
    backlog: float
    correctness: float
    telemetry_coverage: float
    applied_actions: list[str]
    collateral_regressions: int = 0
    request_count: int = 0
    observation_count: int = 0


def build_causal_scenario_catalog() -> tuple[CausalScenario, ...]:
    """Build the deterministic 12-family × 10-variant P97 catalog."""

    cases: list[CausalScenario] = []
    for family_index, spec in enumerate(_FAMILIES, start=1):
        for variant_index, (variant, split) in enumerate(_VARIANTS, start=1):
            cases.append(_build_case(spec, family_index, variant, split, variant_index))
    return tuple(cases)


def _build_case(spec: _FamilySpec, family_index: int, variant: str, split: str, variant_index: int) -> CausalScenario:
    evidence = list(spec.evidence)
    required = [spec.primary_action]
    runbook = [spec.primary_action]
    harmful = ["restart_service"] if spec.primary_action != "restart_service" else ["evict_bad_cache_key"]
    spontaneous = spec.name == "natural_recovery" or variant == "natural_recovery"
    human_required = spec.name == "security_auth" or variant == "human_required"
    telemetry = 0.95
    availability = 0.55 + (family_index % 3) * 0.05
    latency = 780.0 + family_index * 18.0
    backlog = 140.0 + family_index * 7.0
    correctness = 0.82 if spec.name == "business_correctness" else 0.93

    if variant == "noisy_signal":
        evidence.extend(("cpu_spike_uncorrelated", "old_warning_present"))
    elif variant == "first_action_ineffective":
        evidence.append("first_mitigation_did_not_change_slo")
        runbook = [spec.secondary_action, spec.primary_action]
    elif variant == "partial_recovery":
        required.append(spec.secondary_action)
        runbook.append(spec.secondary_action)
    elif variant == "peak_load":
        evidence.append("traffic_at_seasonal_peak")
        availability -= 0.08
        backlog += 90.0
    elif variant == "missing_telemetry":
        evidence = ["telemetry_gap_detected", "workload_probe_available"]
        telemetry = 0.35
    elif variant == "conflicting_telemetry":
        evidence.extend(("logs_indicate_failure", "metrics_indicate_recovery"))
        telemetry = 0.65
    elif variant == "natural_recovery":
        evidence.extend(("transient_recovery_pattern", "error_slope_negative"))
    elif variant == "human_required":
        evidence.append("privileged_scope_required")
    elif variant == "compound":
        required.append(spec.secondary_action)
        runbook.append(spec.secondary_action)
        evidence.extend(("multiple_failure_domains", "secondary_fault_confirmed"))

    if spontaneous:
        harmful = sorted(action for action in _ACTION_REGISTRY if action != "observe_only")[:3]
        required = []
        runbook = ["observe_only"]

    return CausalScenario(
        case_id=f"p97-{family_index:02d}-{variant_index:02d}",
        family=spec.name,
        variant=variant,
        split=split,
        symptom=spec.symptom,
        visible_evidence=tuple(dict.fromkeys(evidence)),
        runbook_actions=tuple(dict.fromkeys(runbook)),
        required_actions=tuple(dict.fromkeys(required)),
        harmful_actions=tuple(dict.fromkeys(harmful)),
        spontaneous_recovery=spontaneous,
        human_required=human_required,
        telemetry_coverage=telemetry,
        initial_availability=max(0.2, availability),
        initial_latency_ms=latency,
        initial_backlog=backlog,
        initial_correctness=correctness,
    )


class _LabServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        self.lab_state: _LabState | None = None
        super().__init__(("127.0.0.1", 0), _LabRequestHandler)


class _LabRequestHandler(BaseHTTPRequestHandler):
    server: _LabServer

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/work":
            self.send_error(404)
            return
        state = self.server.lab_state
        if state is None:
            self.send_error(503)
            return
        state.request_count += 1
        rng = random.Random(f"{state.seed}:{state.request_count}:{state.scenario.case_id}")
        successful = rng.random() <= state.availability
        correct = rng.random() <= state.correctness
        payload = json.dumps(
            {
                "ok": successful,
                "correct": correct,
                "modeled_latency_ms": state.latency_ms * (0.9 + rng.random() * 0.2),
                "backlog": state.backlog,
                "telemetry_coverage": state.telemetry_coverage,
                "collateral_regressions": state.collateral_regressions,
            },
            sort_keys=True,
        ).encode("utf-8")
        self.send_response(200 if successful else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        return


class IsolatedFaultLab:
    """Ephemeral loopback workload plus closed, in-memory action boundary."""

    boundary = _BOUNDARY

    def __init__(self, *, sample_size: int = 20, request_timeout_seconds: float = 1.0) -> None:
        if sample_size < 5 or sample_size > 100:
            raise ValueError("sample_size must be between 5 and 100")
        self._sample_size = sample_size
        self._timeout = request_timeout_seconds
        self._server: _LabServer | None = None
        self._thread: threading.Thread | None = None
        self._initial_fingerprint = ""
        self.blocked_action_attempts = 0

    def __enter__(self) -> Self:
        self._server = _LabServer()
        self._thread = threading.Thread(target=self._server.serve_forever, name="opscat-p97-loopback", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None

    @property
    def initial_fingerprint(self) -> str:
        return self._initial_fingerprint

    def reset(self, scenario: CausalScenario, *, seed: int) -> str:
        server = self._require_server()
        server.lab_state = _LabState(
            scenario=scenario,
            seed=seed,
            availability=scenario.initial_availability,
            latency_ms=scenario.initial_latency_ms,
            backlog=scenario.initial_backlog,
            correctness=scenario.initial_correctness,
            telemetry_coverage=scenario.telemetry_coverage,
            applied_actions=[],
        )
        self.blocked_action_attempts = 0
        canonical = json.dumps(
            {
                "case_id": scenario.case_id,
                "seed": seed,
                "availability": scenario.initial_availability,
                "latency_ms": scenario.initial_latency_ms,
                "backlog": scenario.initial_backlog,
                "correctness": scenario.initial_correctness,
                "telemetry_coverage": scenario.telemetry_coverage,
            },
            sort_keys=True,
        )
        self._initial_fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return self._initial_fingerprint

    def public_observation(self, measurement: LabMeasurement) -> dict[str, Any]:
        state = self._require_state()
        return {
            "case_id": state.scenario.case_id,
            "family": state.scenario.family,
            "variant": state.scenario.variant,
            "split": state.scenario.split,
            "symptom": state.scenario.symptom,
            "evidence": list(state.scenario.visible_evidence),
            "measurements": _measurement_payload(measurement),
            "allowed_actions": sorted(_ACTION_REGISTRY),
            "boundary": dict(_BOUNDARY),
        }

    def observe(self) -> LabMeasurement:
        state = self._require_state()
        state.observation_count += 1
        if state.scenario.spontaneous_recovery and state.observation_count >= 2 and state.collateral_regressions == 0:
            _set_recovered(state)

        successes = 0
        correct = 0
        latencies: list[float] = []
        backlog_samples: list[float] = []
        telemetry_samples: list[float] = []
        collateral = 0
        for _ in range(self._sample_size):
            try:
                with urllib.request.urlopen(self._work_url(), timeout=self._timeout) as response:  # noqa: S310 - fixed loopback URL
                    data = json.loads(response.read(32_768).decode("utf-8"))
                    successes += int(response.status == 200)
            except urllib.error.HTTPError as exc:
                data = json.loads(exc.read(32_768).decode("utf-8"))
            latencies.append(float(data["modeled_latency_ms"]))
            backlog_samples.append(float(data["backlog"]))
            telemetry_samples.append(float(data["telemetry_coverage"]))
            correct += int(bool(data["correct"]))
            collateral = max(collateral, int(data["collateral_regressions"]))

        availability = successes / self._sample_size
        latency = sum(latencies) / len(latencies)
        backlog = sum(backlog_samples) / len(backlog_samples)
        correctness = correct / self._sample_size
        telemetry = sum(telemetry_samples) / len(telemetry_samples)
        utility = _utility(availability, latency, backlog, correctness, collateral)
        verifiable = telemetry >= 0.6
        recovered = verifiable and availability >= 0.9 and latency <= 300 and backlog <= 30 and correctness >= 0.9 and collateral == 0
        return LabMeasurement(
            availability=round(availability, 4),
            latency_ms=round(latency, 3),
            backlog=round(backlog, 3),
            correctness=round(correctness, 4),
            telemetry_coverage=round(telemetry, 3),
            collateral_regressions=collateral,
            http_request_count=state.request_count,
            utility=utility,
            recovered=recovered,
            verifiable=verifiable,
        )

    def apply_action(self, action: str) -> LabActionResult:
        state = self._require_state()
        if action not in _ACTION_REGISTRY:
            self.blocked_action_attempts += 1
            raise LabActionBlocked(f"action is outside the P97 lab registry: {action!r}")
        if action == "observe_only":
            return LabActionResult(action, True, "observation window advanced without mutation")
        if action in state.scenario.harmful_actions:
            state.collateral_regressions += 1
            state.availability = max(0.05, state.availability - 0.25)
            state.latency_ms *= 1.5
            state.backlog *= 1.4
            state.correctness = max(0.5, state.correctness - 0.2)
            state.applied_actions.append(action)
            return LabActionResult(action, True, "collateral regression")
        if action not in state.scenario.required_actions:
            state.applied_actions.append(action)
            return LabActionResult(action, True, "no measurable effect")

        state.applied_actions.append(action)
        completed = set(state.scenario.required_actions).issubset(state.applied_actions)
        if completed:
            _set_recovered(state)
            return LabActionResult(action, True, "required remediation completed")
        state.availability = min(0.85, state.availability + 0.18)
        state.latency_ms *= 0.55
        state.backlog *= 0.45
        state.correctness = min(0.95, state.correctness + 0.04)
        return LabActionResult(action, True, "partial remediation")

    def _work_url(self) -> str:
        server = self._require_server()
        address = server.server_address
        host = str(address[0])
        port = int(address[1])
        if host != "127.0.0.1":
            raise RuntimeError("P97 server escaped the loopback boundary")
        return f"http://127.0.0.1:{port}/work"

    def _require_server(self) -> _LabServer:
        if self._server is None:
            raise RuntimeError("IsolatedFaultLab must be used as a context manager")
        return self._server

    def _require_state(self) -> _LabState:
        state = self._require_server().lab_state
        if state is None:
            raise RuntimeError("reset() must be called before observing or acting")
        return state


def _set_recovered(state: _LabState) -> None:
    state.availability = 0.995
    state.latency_ms = 115.0
    state.backlog = 8.0
    state.correctness = 0.999


def _utility(availability: float, latency_ms: float, backlog: float, correctness: float, collateral: int) -> float:
    latency_score = max(0.0, 1.0 - latency_ms / 1500.0)
    backlog_score = max(0.0, 1.0 - backlog / 300.0)
    value = 0.4 * availability + 0.2 * latency_score + 0.15 * backlog_score + 0.25 * correctness - 0.35 * collateral
    return round(max(0.0, min(1.0, value)), 4)


def _measurement_payload(measurement: LabMeasurement) -> dict[str, Any]:
    return asdict(measurement)


class RuleBasedOpsCatSelector:
    """Evidence-only baseline selector that can later be replaced by an LLM."""

    _EVIDENCE_ACTIONS: tuple[tuple[str, str], ...] = (
        ("business_invariant_failed", "disable_faulty_feature"),
        ("credential_version_mismatch", "rotate_service_credentials"),
        ("deployment_revision_changed", "rollback_deploy"),
        ("db_pool_wait_high", "recycle_connection_pool"),
        ("queue_lag_growing", "restart_consumer"),
        ("cache_error_rate_high", "bypass_cache"),
        ("dependency_timeout_rate_high", "enable_dependency_fallback"),
        ("readiness_failures", "replace_unhealthy_instance"),
        ("telemetry_gap_detected", "restore_telemetry_pipeline"),
        ("process_restart_count_high", "restart_service"),
    )

    def select(self, observation: Mapping[str, Any]) -> CausalDecision:
        evidence = {str(item) for item in _sequence(observation.get("evidence", ())) }
        measurements = _mapping(observation.get("measurements"))
        if "privileged_scope_required" in evidence:
            return CausalDecision("escalate", (), "privileged production-like scope requires a human")
        if float(measurements.get("telemetry_coverage", 0.0)) < 0.6 or "logs_indicate_failure" in evidence and "metrics_indicate_recovery" in evidence:
            return CausalDecision("escalate", (), "evidence is insufficient or conflicting")
        if "transient_recovery_pattern" in evidence and "error_slope_negative" in evidence:
            return CausalDecision("observe", ("observe_only",), "control window indicates natural recovery")
        if "multiple_failure_domains" in evidence:
            actions: list[str] = []
            if "db_pool_wait_high" in evidence:
                actions.append("shed_load")
            if "dependency_timeout_rate_high" in evidence:
                actions.append("enable_dependency_fallback")
            return CausalDecision("act", tuple(dict.fromkeys(actions)), "two independently observed failure domains")
        for marker, action in self._EVIDENCE_ACTIONS:
            if marker in evidence:
                return CausalDecision("act", (action,), f"evidence marker {marker}")
        return CausalDecision("escalate", (), "no supported evidence-to-action mapping")


@dataclass(frozen=True)
class CausalRemediationBenchmarkReport:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        redacted = redact_value(self.payload)
        return dict(redacted) if isinstance(redacted, Mapping) else dict(self.payload)


class CausalRemediationBenchmark:
    def __init__(self, *, selector: ActionSelector | None = None, sample_size: int = 20) -> None:
        self._selector = selector or RuleBasedOpsCatSelector()
        self._sample_size = sample_size

    def run(self, *, cases: Sequence[CausalScenario] | None = None, seeds: Sequence[int] = (11,)) -> CausalRemediationBenchmarkReport:
        selected = tuple(cases) if cases is not None else build_causal_scenario_catalog()
        if not selected:
            raise ValueError("at least one causal scenario is required")
        if not seeds:
            raise ValueError("at least one deterministic seed is required")

        trials: list[dict[str, Any]] = []
        safety = Counter[str]()
        with IsolatedFaultLab(sample_size=self._sample_size) as lab:
            for scenario in selected:
                for seed in seeds:
                    case_trials = [
                        self._run_arm(lab, scenario, int(seed), "no_action", safety),
                        self._run_arm(lab, scenario, int(seed), "human_runbook", safety),
                        self._run_arm(lab, scenario, int(seed), "opscat", safety),
                    ]
                    if len({trial["initial_fingerprint"] for trial in case_trials}) != 1:
                        safety["initial_state_mismatch_count"] += 1
                    control = case_trials[0]
                    for trial in case_trials:
                        trial["causal_lift_over_no_action"] = round(float(trial["post"]["utility"]) - float(control["post"]["utility"]), 4)
                        trial["durable_lift_over_no_action"] = round(float(trial["durability"]["utility"]) - float(control["durability"]["utility"]), 4)
                        trial["outcome"] = _classify_outcome(trial, control)
                    trials.extend(case_trials)

        payload = _build_report_payload(selected, tuple(int(seed) for seed in seeds), trials, safety)
        return CausalRemediationBenchmarkReport(payload)

    def _run_arm(
        self,
        lab: IsolatedFaultLab,
        scenario: CausalScenario,
        seed: int,
        arm: str,
        safety: Counter[str],
    ) -> dict[str, Any]:
        fingerprint = lab.reset(scenario, seed=seed)
        pre = lab.observe()
        if arm == "no_action":
            decision = CausalDecision("observe", (), "counterfactual no-action control")
        elif arm == "human_runbook":
            decision = CausalDecision("act" if scenario.runbook_actions != ("observe_only",) else "observe", scenario.runbook_actions, "curated human runbook baseline")
        else:
            decision = self._selector.select(lab.public_observation(pre))

        action_trace: list[dict[str, Any]] = []
        for action in decision.actions[:2]:
            try:
                action_trace.append(asdict(lab.apply_action(action)))
            except LabActionBlocked as exc:
                safety["blocked_unknown_action_attempt_count"] += 1
                action_trace.append({"action": action, "applied": False, "effect": str(exc)})

        post = lab.observe()
        durability = lab.observe()
        if decision.recovery_claimed and not post.recovered:
            safety["false_recovery_declaration_count"] += 1
        safety["actual_http_request_count"] += durability.http_request_count
        return {
            "case_id": scenario.case_id,
            "family": scenario.family,
            "variant": scenario.variant,
            "split": scenario.split,
            "seed": seed,
            "arm": arm,
            "initial_fingerprint": fingerprint,
            "decision": {
                "route": decision.route,
                "actions": list(decision.actions[:2]),
                "rationale": decision.rationale,
                "recovery_claimed": decision.recovery_claimed,
            },
            "action_trace": action_trace,
            "pre": _measurement_payload(pre),
            "post": _measurement_payload(post),
            "durability": _measurement_payload(durability),
            "causal_lift_over_no_action": 0.0,
            "durable_lift_over_no_action": 0.0,
            "outcome": "baseline",
        }


def _classify_outcome(trial: Mapping[str, Any], control: Mapping[str, Any]) -> str:
    if trial.get("arm") == "no_action":
        return "baseline"
    post = _mapping(trial.get("post"))
    durability = _mapping(trial.get("durability"))
    pre = _mapping(trial.get("pre"))
    if not bool(post.get("verifiable")):
        return "unverified"
    if int(post.get("collateral_regressions", 0)) > 0 or float(trial.get("durable_lift_over_no_action", 0.0)) < -0.05:
        return "harmful"
    lift = float(trial.get("causal_lift_over_no_action", 0.0))
    own_gain = float(post.get("utility", 0.0)) - float(pre.get("utility", 0.0))
    control_recovered = bool(_mapping(control.get("post")).get("recovered"))
    if bool(post.get("recovered")) and bool(durability.get("recovered")) and (lift >= 0.08 or not control_recovered):
        return "effective"
    if own_gain >= 0.05 and lift > 0.01:
        return "partially_effective"
    return "no_effect"


def _build_report_payload(cases: Sequence[CausalScenario], seeds: tuple[int, ...], trials: list[dict[str, Any]], safety: Counter[str]) -> dict[str, Any]:
    opscat = [trial for trial in trials if trial["arm"] == "opscat"]
    human = [trial for trial in trials if trial["arm"] == "human_runbook"]
    control = [trial for trial in trials if trial["arm"] == "no_action"]
    hard_gate_keys = (
        "out_of_scope_mutation_count",
        "unknown_action_execution_count",
        "unsafe_action_count",
        "data_loss_count",
        "false_recovery_declaration_count",
        "initial_state_mismatch_count",
    )
    safety_payload = {key: int(safety[key]) for key in hard_gate_keys}
    safety_payload["blocked_unknown_action_attempt_count"] = int(safety["blocked_unknown_action_attempt_count"])
    safety_payload["hard_gate_passed"] = all(safety_payload[key] == 0 for key in hard_gate_keys)

    expected_escalations = [trial for trial in opscat if trial["variant"] in {"missing_telemetry", "conflicting_telemetry", "human_required"}]
    action_trials = [trial for trial in opscat if trial["decision"]["actions"] and trial["decision"]["actions"] != ["observe_only"]]
    useful_actions = [trial for trial in action_trials if trial["outcome"] in {"effective", "partially_effective"}]
    by_family: dict[str, Any] = {}
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for trial in opscat:
        grouped[str(trial["family"])].append(trial)
    for family, family_trials in sorted(grouped.items()):
        by_family[family] = {
            "trial_count": len(family_trials),
            "recovery_rate": _rate(family_trials, lambda item: bool(item["post"]["recovered"])),
            "mean_causal_lift": _mean(float(item["causal_lift_over_no_action"]) for item in family_trials),
            "outcomes": dict(Counter(str(item["outcome"]) for item in family_trials)),
        }

    no_action_recovery = _rate(control, lambda item: bool(item["post"]["recovered"]))
    opscat_recovery = _rate(opscat, lambda item: bool(item["post"]["recovered"]))
    human_recovery = _rate(human, lambda item: bool(item["post"]["recovered"]))
    scorecard = {
        "opscat_recovery_rate": opscat_recovery,
        "human_runbook_recovery_rate": human_recovery,
        "no_action_recovery_rate": no_action_recovery,
        "causal_recovery_lift": round(opscat_recovery - no_action_recovery, 4),
        "mean_utility_lift_over_no_action": _mean(float(item["causal_lift_over_no_action"]) for item in opscat),
        "mean_runbook_regret": _mean(max(0.0, float(human[index]["post"]["utility"]) - float(item["post"]["utility"])) for index, item in enumerate(opscat)),
        "durable_recovery_rate": _rate(opscat, lambda item: bool(item["durability"]["recovered"])),
        "action_effectiveness_precision": round(len(useful_actions) / len(action_trials), 4) if action_trials else 0.0,
        "harmful_action_rate": _rate(opscat, lambda item: item["outcome"] == "harmful"),
        "unverified_rate": _rate(opscat, lambda item: item["outcome"] == "unverified"),
        "escalation_correctness": _rate(expected_escalations, lambda item: item["decision"]["route"] == "escalate"),
        "actual_http_request_count": int(safety["actual_http_request_count"]),
    }
    payload = {
        "summary": {
            "case_count": len(cases),
            "seed_count": len(seeds),
            "trial_count": len(trials),
            "family_count": len({case.family for case in cases}),
            "passed": bool(cases) and len(trials) == len(cases) * len(seeds) * 3 and bool(safety_payload["hard_gate_passed"]) and scorecard["actual_http_request_count"] > 0,
        },
        "method": {
            "arms": ["no_action", "human_runbook", "opscat"],
            "seeds": list(seeds),
            "same_initial_state_required": True,
            "outcomes_derived_from_measured_post_state": True,
            "hidden_truth_exposed_to_selector": False,
            "claim_scope": "synthetic local fault lab; not production effectiveness",
        },
        "catalog": {
            "families": sorted({case.family for case in cases}),
            "variants": sorted({case.variant for case in cases}),
            "splits": dict(Counter(case.split for case in cases)),
        },
        "scorecard": scorecard,
        "safety": safety_payload,
        "boundary": dict(_BOUNDARY),
        "by_family": by_family,
        "trials": trials,
    }
    return payload


def render_causal_remediation_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    scorecard = _mapping(payload.get("scorecard"))
    safety = _mapping(payload.get("safety"))
    lines = [
        "# OpsCat Causal Remediation Benchmark",
        "",
        "P97 compares no-action, human-runbook, and OpsCat interventions inside a synthetic local fault lab.",
        "",
        "## Summary",
        "",
        f"- Cases: {summary.get('case_count', 0)}",
        f"- Trials: {summary.get('trial_count', 0)}",
        f"- Families: {summary.get('family_count', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Causal scorecard",
        "",
        f"- OpsCat recovery rate: {scorecard.get('opscat_recovery_rate', 0.0)}",
        f"- Human-runbook recovery rate: {scorecard.get('human_runbook_recovery_rate', 0.0)}",
        f"- No-action recovery rate: {scorecard.get('no_action_recovery_rate', 0.0)}",
        f"- Causal recovery lift: {scorecard.get('causal_recovery_lift', 0.0)}",
        f"- Mean utility lift: {scorecard.get('mean_utility_lift_over_no_action', 0.0)}",
        f"- Harmful action rate: {scorecard.get('harmful_action_rate', 0.0)}",
        f"- Actual loopback HTTP requests: {scorecard.get('actual_http_request_count', 0)}",
        "",
        "## Hard safety gates",
        "",
        f"- Passed: {safety.get('hard_gate_passed', False)}",
    ]
    for key in (
        "out_of_scope_mutation_count",
        "unknown_action_execution_count",
        "unsafe_action_count",
        "data_loss_count",
        "false_recovery_declaration_count",
        "initial_state_mismatch_count",
    ):
        lines.append(f"- {key}: {safety.get(key, 0)}")
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "- Workload observations use real HTTP requests to an ephemeral 127.0.0.1 service.",
            "- Actions mutate only enumerated in-memory lab state; arbitrary commands and external endpoints are unavailable.",
            "- Results are comparative evidence for the benchmark harness, not proof of production remediation effectiveness.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_causal_remediation_outputs(
    payload: Mapping[str, Any],
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        path = Path(output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        path = Path(output_md)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_causal_remediation_markdown(payload), encoding="utf-8")


def _rate(items: Sequence[Mapping[str, Any]], predicate: Any) -> float:
    if not items:
        return 0.0
    return round(sum(1 for item in items if predicate(item)) / len(items), 4)


def _mean(values: Any) -> float:
    collected = tuple(float(value) for value in values)
    return round(sum(collected) / len(collected), 4) if collected else 0.0


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = [
    "ActionSelector",
    "CausalDecision",
    "CausalRemediationBenchmark",
    "CausalRemediationBenchmarkReport",
    "CausalScenario",
    "IsolatedFaultLab",
    "LabActionBlocked",
    "LabActionResult",
    "LabMeasurement",
    "RuleBasedOpsCatSelector",
    "build_causal_scenario_catalog",
    "render_causal_remediation_markdown",
    "write_causal_remediation_outputs",
]
