#!/usr/bin/env python3
"""Generate deterministic P135 provider-export release evidence."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import importlib
import json
import os
import resource
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_evaluation import stable_hash  # noqa: E402
from app.services.p121_signals import zero_authority_counters as zero_p121_authority  # noqa: E402
from app.services.p134_observation_authority import (  # noqa: E402
    build_contract,
    build_contract_core,
    build_proposal,
    build_review_receipt,
    evaluate_proposal,
)
from app.services.p134_observation_authority import (  # noqa: E402
    new_receipt_ledger as new_p134_receipt_ledger,
)
from app.services.p135_release_evidence import (  # noqa: E402
    FORBIDDEN_AUTHORITY_COUNTERS,
    OBSERVATION_ACTIVITY_COUNTERS,
    P135_READY_STATUS,
    REQUIRED_CASES,
    SUCCESS_PROVIDERS,
    build_authority_ledger,
    build_p135_release_evidence,
    validate_authority_ledger,
    validate_p135_release_evidence,
)

PROFILE_SCHEMA_VERSION = "p135.provider_export_profile.v1"
CASE_MATRIX_SCHEMA_VERSION = "p135.release_case_matrix.v1"
BUNDLES_SCHEMA_VERSION = "p135.canonical_normalized_bundles.v1"
AUTHORITY_CONTRACT_ID = "p135-local-export-attachment"
AUTHORITY_HOST_LABEL = "local-artifact.telemetry-read"
AUTHORITY_REQUEST_ID_PREFIX = "p135-local-"
STARTED_AT = "2026-07-13T00:10:00Z"
COMPLETED_AT = "2026-07-13T00:10:01Z"
RESOURCE_LIMITS = {
    "wall_limit_ms": 30_000,
    "cpu_limit_ms": 10_000,
    "peak_memory_limit_bytes": 100_663_296,
}
EXPECTED_ARTIFACTS = frozenset(
    {
        "case-matrix.json",
        "authority-ledger.json",
        "release-evidence.json",
        "execution-ledger.json",
        "normalized-bundles.json",
    }
)
PROFILE_FIELDS = frozenset(
    {
        "schema_version",
        "case_matrix_version",
        "authority_contract_id",
        "authority_host_label",
        "authority_request_id_prefix",
        "root_ref_hash",
        "input_root",
        "output_artifacts",
        "required_cases",
        "resource_limits",
    }
)

PROVIDER_ARTIFACTS: dict[str, dict[str, Any]] = {
    "prometheus_matrix_success": {
        "source_id": "prometheus-matrix",
        "provider": "prometheus",
        "format": "prometheus.query_range.matrix.v1",
        "signal_family": "metrics",
        "capability": "telemetry.metrics.read",
        "fixture": "prometheus_matrix.json",
        "expected_records": 2,
    },
    "loki_streams_success": {
        "source_id": "loki-streams",
        "provider": "loki",
        "format": "loki.query_range.streams.v1",
        "signal_family": "logs",
        "capability": "telemetry.logs.read",
        "fixture": "loki_streams.json",
        "expected_records": 2,
    },
    "grafana_dashboard_success": {
        "source_id": "grafana-dashboard",
        "provider": "grafana",
        "format": "grafana.dashboard.classic.v1",
        "signal_family": "topology",
        "capability": "telemetry.topology.read",
        "fixture": "grafana_dashboard.json",
        "expected_records": 1,
    },
    "sentry_issues_success": {
        "source_id": "sentry-issues",
        "provider": "sentry",
        "format": "sentry.issues.api.list.v1",
        "signal_family": "events",
        "capability": "telemetry.events.read",
        "fixture": "sentry_issues.json",
        "expected_records": 1,
    },
    "otlp_metrics_success": {
        "source_id": "otlp-metrics",
        "provider": "opentelemetry",
        "format": "otlp.file.jsonl.v1",
        "signal_family": "metrics",
        "capability": "telemetry.metrics.read",
        "fixture": "otlp_metrics.jsonl",
        "expected_records": 1,
    },
}
POST_READ_ARTIFACTS: dict[str, dict[str, Any]] = {
    "record_estimate_exceeded_fail_closed": {
        **PROVIDER_ARTIFACTS["prometheus_matrix_success"],
        "source_id": "record-estimate-exceeded",
        "expected_records": 1,
        "expected_error": "authority_record_estimate_exceeded",
    },
    "prometheus_wrong_result_type_rejected": {
        **PROVIDER_ARTIFACTS["prometheus_matrix_success"],
        "source_id": "prometheus-wrong-result",
        "fixture": "prometheus_wrong_result_type.json",
        "expected_records": 1,
        "expected_error": "prometheus_result_type_mismatch",
    },
    "loki_malformed_nanosecond_rejected": {
        **PROVIDER_ARTIFACTS["loki_streams_success"],
        "source_id": "loki-malformed-nanosecond",
        "fixture": "loki_malformed_nanosecond.json",
        "expected_records": 1,
        "expected_error": "malformed_loki_timestamp",
    },
    "grafana_duplicate_panel_id_rejected": {
        **PROVIDER_ARTIFACTS["grafana_dashboard_success"],
        "source_id": "grafana-duplicate-panel",
        "fixture": "grafana_duplicate_panel_id.json",
        "expected_records": 1,
        "expected_error": "duplicate_grafana_panel_id",
    },
    "sentry_duplicate_issue_identity_rejected": {
        **PROVIDER_ARTIFACTS["sentry_issues_success"],
        "source_id": "sentry-duplicate-issue",
        "fixture": "sentry_duplicate_issue_identity.json",
        "expected_records": 1,
        "expected_error": "duplicate_sentry_issue_id",
    },
    "otlp_mixed_signal_rejected": {
        **PROVIDER_ARTIFACTS["otlp_metrics_success"],
        "source_id": "otlp-mixed-signal",
        "fixture": "otlp_mixed_signal.jsonl",
        "expected_records": 1,
        "expected_error": "otlp_signal_family_mismatch",
    },
    "duplicate_json_key_rejected": {
        **PROVIDER_ARTIFACTS["prometheus_matrix_success"],
        "source_id": "duplicate-json-key",
        "fixture": "parser_failure_duplicate_key.json",
        "expected_records": 1,
        "expected_error": "duplicate_json_key",
    },
    "nonfinite_number_rejected": {
        **PROVIDER_ARTIFACTS["prometheus_matrix_success"],
        "source_id": "nonfinite-number",
        "fixture": "prometheus_nonfinite_number.json",
        "expected_records": 1,
        "expected_error": "non_finite_number:NaN",
    },
    "utf8_string_line_budget_rejected": {
        **PROVIDER_ARTIFACTS["loki_streams_success"],
        "source_id": "line-budget",
        "fixture": "loki_line_budget.json",
        "expected_records": 1,
        "expected_error": "log_line_budget_exceeded",
        "max_line_bytes": 16,
    },
}
PROMPT_SECRET_ARTIFACT = {
    **PROVIDER_ARTIFACTS["prometheus_matrix_success"],
    "source_id": "prompt-secret",
    "fixture": "p120_wrapped_prompt_secret.json",
    "expected_records": 1,
}


class _DeniedEnvironment(Mapping[str, str]):
    def __init__(self, blocker: Callable[..., Any]) -> None:
        self._blocker = blocker

    def __getitem__(self, key: str) -> str:
        return self._blocker(key)

    def __iter__(self) -> Iterator[str]:
        self._blocker()
        return iter(())

    def __len__(self) -> int:
        self._blocker()
        return 0


class _ForbiddenRuntimeGuard:
    """Fail immediately if the P135 matrix touches a forbidden runtime surface."""

    def __init__(self) -> None:
        self.counters = {key: 0 for key in FORBIDDEN_AUTHORITY_COUNTERS}
        self._stack = ExitStack()

    def _blocked(self, counter: str) -> Callable[..., Any]:
        def blocked(*_args: Any, **_kwargs: Any) -> Any:
            self.counters[counter] += 1
            raise RuntimeError(f"forbidden_runtime_surface:{counter}")

        return blocked

    def __enter__(self) -> _ForbiddenRuntimeGuard:
        patches = (
            patch.object(socket, "socket", self._blocked("socket_call_count")),
            patch.object(socket, "create_connection", self._blocked("network_call_count")),
            patch.object(socket, "getaddrinfo", self._blocked("dns_lookup_count")),
            patch.object(urllib.request, "urlopen", self._blocked("network_call_count")),
            patch.object(http.client.HTTPConnection, "request", self._blocked("network_call_count")),
            patch.object(http.client.HTTPSConnection, "request", self._blocked("network_call_count")),
            patch.object(subprocess, "Popen", self._blocked("subprocess_launch_count")),
            patch.object(subprocess, "run", self._blocked("subprocess_launch_count")),
            patch.object(subprocess, "call", self._blocked("subprocess_launch_count")),
            patch.object(subprocess, "check_call", self._blocked("subprocess_launch_count")),
            patch.object(subprocess, "check_output", self._blocked("subprocess_launch_count")),
            patch.object(os, "system", self._blocked("shell_execution_count")),
            patch.object(os, "popen", self._blocked("shell_execution_count")),
            patch.object(os, "getenv", self._blocked("environment_read_count")),
            patch.object(os, "kill", self._blocked("signal_count")),
            patch.object(os, "killpg", self._blocked("signal_count")),
            patch.object(signal, "raise_signal", self._blocked("signal_count")),
            patch.object(os, "environ", _DeniedEnvironment(self._blocked("environment_read_count"))),
        )
        for item in patches:
            self._stack.enter_context(item)
        requests_sessions = sys.modules.get("requests.sessions")
        if requests_sessions is not None and hasattr(requests_sessions, "Session"):
            self._stack.enter_context(
                patch.object(requests_sessions.Session, "request", self._blocked("provider_call_count"))
            )
        httpx_module = sys.modules.get("httpx")
        if httpx_module is not None:
            for client_name in ("Client", "AsyncClient"):
                client = getattr(httpx_module, client_name, None)
                if client is not None:
                    self._stack.enter_context(
                        patch.object(client, "request", self._blocked("provider_call_count"))
                    )
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._stack.close()


def main(argv: Sequence[str] | None = None) -> int:
    started_wall = time.monotonic()
    started_cpu = _cpu_ms()
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, default=ROOT / "evals/p135/input/provider-export-profile.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evals/p135")
    parser.add_argument("--independent-review", type=Path, default=ROOT / "evals/p135/independent-review.json")
    args = parser.parse_args(argv)

    try:
        profile = _validate_profile(_read_json(args.profile))
        input_root = _profile_input_root(profile, profile_path=args.profile)
        case_matrix, authority_ledger, execution_ledger, bundles = _run_case_matrix(profile, input_root)
        _revalidate_provider_artifacts(execution_ledger, bundles)
        independent_review = _read_json(args.independent_review)
        validate_authority_ledger(authority_ledger)
        case_matrix["resource_usage"] = _resource_usage(started_wall=started_wall, started_cpu=started_cpu)
        case_matrix["matrix_hash"] = stable_hash({key: value for key, value in case_matrix.items() if key != "matrix_hash"})
        release_evidence = build_p135_release_evidence(
            case_matrix,
            authority_ledger,
            _mapping(independent_review, "independent_review"),
            project_root=ROOT,
        )
        validate_p135_release_evidence(
            release_evidence,
            case_matrix=case_matrix,
            authority_ledger=authority_ledger,
            independent_review=_mapping(independent_review, "independent_review"),
            project_root=ROOT,
        )
        artifacts = {
            "case-matrix.json": case_matrix,
            "authority-ledger.json": authority_ledger,
            "release-evidence.json": release_evidence,
            "execution-ledger.json": execution_ledger,
            "normalized-bundles.json": bundles,
        }
        _write_exact_artifacts(args.output_dir, artifacts)
        print(
            json.dumps(
                {
                    "release_status": release_evidence["release_status"],
                    "release_evidence_hash": release_evidence["release_evidence_hash"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0 if release_evidence["release_status"] == P135_READY_STATUS else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "release_status": "p135_blocked",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


def _validate_profile(value: Any) -> Mapping[str, Any]:
    profile = _mapping(value, "profile")
    _expect_fields(profile, PROFILE_FIELDS, "profile")
    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValueError("invalid_profile_schema")
    if profile.get("case_matrix_version") != 1:
        raise ValueError("invalid_case_matrix_version")
    if profile.get("authority_contract_id") != AUTHORITY_CONTRACT_ID:
        raise ValueError("authority_contract_id_mismatch")
    if profile.get("authority_host_label") != AUTHORITY_HOST_LABEL:
        raise ValueError("authority_host_label_mismatch")
    if profile.get("authority_request_id_prefix") != AUTHORITY_REQUEST_ID_PREFIX:
        raise ValueError("authority_request_id_prefix_mismatch")
    if profile.get("required_cases") != list(REQUIRED_CASES):
        raise ValueError("required_cases_mismatch")
    if profile.get("output_artifacts") != sorted(EXPECTED_ARTIFACTS):
        raise ValueError("output_artifacts_mismatch")
    if dict(_mapping(profile.get("resource_limits"), "resource_limits")) != RESOURCE_LIMITS:
        raise ValueError("resource_limits_mismatch")
    root_hash = profile.get("root_ref_hash")
    if not isinstance(root_hash, str) or not root_hash.startswith("sha256:"):
        raise ValueError("invalid_root_ref_hash")
    input_root = profile.get("input_root")
    if not isinstance(input_root, str) or input_root.startswith("/") or ".." in Path(input_root).parts:
        raise ValueError("invalid_input_root")
    return profile


def _run_case_matrix(
    profile: Mapping[str, Any],
    input_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    with _ForbiddenRuntimeGuard() as guard:
        matrix, authority_ledger, execution_ledger, bundles = _run_case_matrix_guarded(
            profile,
            input_root,
        )
    runtime_clean = all(value == 0 for value in guard.counters.values())
    if not runtime_clean:
        raise ValueError("forbidden_runtime_surface_touched")
    for case in matrix["cases"].values():
        case["authority_zero"] = runtime_clean
        case["no_network_credentials_actions"] = runtime_clean
        case["case_hash"] = stable_hash({key: value for key, value in case.items() if key != "case_hash"})
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})
    authority_ledger = build_authority_ledger(
        evaluator_activity=authority_ledger["evaluator_activity"],
        observation_activity=authority_ledger["observation_activity"],
        forbidden_authority=guard.counters,
    )
    return matrix, authority_ledger, execution_ledger, bundles


def _run_case_matrix_guarded(
    profile: Mapping[str, Any],
    input_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    del profile
    provider_api = _provider_api()
    if not input_root.is_dir():
        raise FileNotFoundError(input_root)
    _validate_provider_zero_contract(provider_api)

    contract, p134_ledger, allowed_receipts = _build_authority_context(input_root, provider_api)
    shared_post_read = {key: value for key, value in POST_READ_ARTIFACTS.items() if key != "utf8_string_line_budget_rejected"}
    principal_specs = [*PROVIDER_ARTIFACTS.values(), *shared_post_read.values(), PROMPT_SECRET_ARTIFACT]
    manifest = provider_api.build_export_manifest(
        _manifest_data(input_root, principal_specs),
        contract,
        allowed_receipts,
    )
    provider_api.validate_export_manifest(manifest, contract, allowed_receipts)

    cases: dict[str, dict[str, Any]] = {}
    aggregate_activity = provider_api.zero_observation_activity()
    success_bundles: list[dict[str, Any]] = []
    failure_bundles: list[dict[str, Any]] = []
    duplicate_result: dict[str, Any] | None = None

    ledger = provider_api.new_execution_ledger(manifest)
    for case_name in SUCCESS_PROVIDERS:
        spec = PROVIDER_ARTIFACTS[case_name]
        result = _attach(provider_api, input_root, manifest, str(spec["source_id"]), contract, allowed_receipts, ledger)
        ledger = result.ledger
        _add_activity(aggregate_activity, result.activity)
        provider_api.validate_normalized_bundle(result.bundle)
        provider_api.validate_execution_ledger(ledger, manifest, contract, allowed_receipts, bundles=[*success_bundles, result.bundle])
        success_bundles.append(deepcopy(result.bundle))
        passed = result.duplicate is False and result.receipt["status"] == "succeeded" and result.bundle["provider"] == SUCCESS_PROVIDERS[case_name]
        cases[case_name] = _case(passed=passed, outcome="success", provider=SUCCESS_PROVIDERS[case_name], error=None)

    duplicate = _attach(
        provider_api,
        input_root,
        manifest,
        str(PROVIDER_ARTIFACTS["prometheus_matrix_success"]["source_id"]),
        contract,
        allowed_receipts,
        ledger,
    )
    _add_activity(aggregate_activity, duplicate.activity)
    duplicate_result = {
        "source_id": duplicate.bundle["source_id"],
        "duplicate": duplicate.duplicate,
        "receipt_hash": duplicate.receipt["receipt_hash"],
        "activity": dict(duplicate.activity),
    }
    cases["deterministic_duplicate"] = _case(
        passed=duplicate.duplicate is True and duplicate.ledger == ledger,
        outcome="duplicate",
        provider=None,
        error=None,
    )

    for case_name, spec in shared_post_read.items():
        result = _attach(provider_api, input_root, manifest, str(spec["source_id"]), contract, allowed_receipts, ledger)
        _add_activity(aggregate_activity, result.activity)
        provider_api.validate_denominator_failure_bundle(result.bundle)
        failure_bundles.append(deepcopy(result.bundle))
        expected_error = str(spec["expected_error"])
        cases[case_name] = _case(
            passed=result.receipt["status"] == "failed" and result.bundle.get("failure_reason") == expected_error,
            outcome="rejected",
            provider=None,
            error=expected_error,
        )

    prompt_result = _attach(provider_api, input_root, manifest, str(PROMPT_SECRET_ARTIFACT["source_id"]), contract, allowed_receipts, ledger)
    _add_activity(aggregate_activity, prompt_result.activity)
    provider_api.validate_normalized_bundle(prompt_result.bundle)
    success_bundles.append(deepcopy(prompt_result.bundle))
    prompt_serialized = json.dumps(prompt_result.bundle, sort_keys=True)
    prompt_flags = {flag for record in prompt_result.bundle["records"] for flag in record["risk_flags"]}
    prompt_passed = (
        prompt_result.receipt["status"] == "succeeded"
        and {"prompt_like_text", "credential_like_text"} <= prompt_flags
        and "sk_live_secret" not in prompt_serialized
        and "api_key" not in prompt_serialized
        and "ignore previous instructions" not in prompt_serialized
    )
    cases["prompt_injection_text_flagged_redacted"] = _case(
        passed=prompt_passed,
        outcome="rejected",
        provider=None,
        error="prompt_like_text:credential_like_text",
    )
    sensitive_passed = _sensitive_attribute_hash_absent(prompt_result.bundle)
    cases["sensitive_attribute_hashed_absent"] = _case(
        passed=sensitive_passed,
        outcome="rejected",
        provider=None,
        error="sensitive_attribute_hashed_absent",
    )

    cases.update(_run_pre_read_and_tamper_cases(provider_api, input_root, contract, allowed_receipts, manifest, ledger, success_bundles, aggregate_activity))
    line_budget_case, line_budget_bundle = _line_budget_case(provider_api, input_root, contract, aggregate_activity)
    failure_bundles.append(line_budget_bundle)
    cases["utf8_string_line_budget_rejected"] = line_budget_case

    provider_api.validate_execution_ledger(ledger, manifest, contract, allowed_receipts, bundles=success_bundles[:5])
    provider_successes = dict(sorted(Counter(receipt["provider"] for receipt in ledger["receipts"]).items()))
    passed_cases = sum(1 for case in cases.values() if case["passed"] is True)
    failed_cases = len(REQUIRED_CASES) - passed_cases
    matrix: dict[str, Any] = {
        "schema_version": CASE_MATRIX_SCHEMA_VERSION,
        "required_cases": list(REQUIRED_CASES),
        "cases": {name: cases[name] for name in REQUIRED_CASES},
        "totals": {
            "expected_cases": len(REQUIRED_CASES),
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "successful_provider_attachments": len(ledger["receipts"]),
            "duplicate_cases": sum(1 for case in cases.values() if case["outcome"] == "duplicate" and case["passed"] is True),
            "rejected_cases": sum(1 for case in cases.values() if case["outcome"] == "rejected" and case["passed"] is True),
            "denominator_scope": "principal_provider_export_assertions",
        },
        "provider_successes": provider_successes,
        "resource_usage": {
            "wall_time_ms": 0,
            "cpu_time_ms": 0,
            "peak_memory_bytes": 0,
            **RESOURCE_LIMITS,
        },
        "matrix_hash": "",
    }
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})

    authority_ledger = build_authority_ledger(
        evaluator_activity={
            "runner_invocation_count": 1,
            "profile_read_count": 1,
            "artifact_write_count": 5,
        },
        observation_activity=aggregate_activity,
    )
    bundles = _normalized_bundles_container(
        manifest=manifest,
        contract=contract,
        p134_ledger=p134_ledger,
        allowed_receipts=allowed_receipts,
        success_bundles=success_bundles,
        failure_bundles=failure_bundles,
        duplicate_result=duplicate_result,
        provider_success_ledger=ledger,
    )
    return matrix, authority_ledger, ledger, bundles


def _run_pre_read_and_tamper_cases(
    provider_api: Any,
    input_root: Path,
    contract: Mapping[str, Any],
    allowed_receipts: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    success_ledger: Mapping[str, Any],
    success_bundles: Sequence[Mapping[str, Any]],
    aggregate_activity: dict[str, int],
) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}

    cases["denied_p134_receipt_rejected"] = _expected_exception_case(
        provider_api,
        "authority_decision_not_allowed",
        lambda: provider_api.build_export_manifest(
            _manifest_data(input_root, [PROVIDER_ARTIFACTS["prometheus_matrix_success"]]),
            contract,
            [_denied_receipt(contract, input_root, PROVIDER_ARTIFACTS["prometheus_matrix_success"])],
        ),
    )

    wrong_capability_manifest = provider_api.build_export_manifest(
        _manifest_data(input_root, [PROVIDER_ARTIFACTS["prometheus_matrix_success"]]),
        contract,
        [_allowed_receipt(contract, input_root, PROVIDER_ARTIFACTS["prometheus_matrix_success"], capability="telemetry.logs.read")],
    )
    cases["wrong_p134_capability_rejected"] = _expected_exception_case(
        provider_api,
        "authority_capability_mismatch",
        lambda: _attach(
            provider_api,
            input_root,
            wrong_capability_manifest,
            str(PROVIDER_ARTIFACTS["prometheus_matrix_success"]["source_id"]),
            contract,
            [_allowed_receipt(contract, input_root, PROVIDER_ARTIFACTS["prometheus_matrix_success"], capability="telemetry.logs.read")],
            provider_api.new_execution_ledger(wrong_capability_manifest),
        ),
    )

    cases["byte_estimate_exceeded_rejected"] = _expected_exception_case(
        provider_api,
        "authority_byte_estimate_exceeded",
        lambda: provider_api.build_export_manifest(
            _manifest_data(input_root, [PROVIDER_ARTIFACTS["prometheus_matrix_success"]]),
            contract,
            [_allowed_receipt(contract, input_root, PROVIDER_ARTIFACTS["prometheus_matrix_success"], estimated_response_bytes=1)],
        ),
    )

    cases["manifest_total_byte_budget_exceeded"] = _expected_exception_case(
        provider_api,
        "manifest_total_byte_budget_exceeded",
        lambda: provider_api.build_export_manifest(
            _manifest_data(input_root, [PROVIDER_ARTIFACTS["prometheus_matrix_success"], PROVIDER_ARTIFACTS["loki_streams_success"]], max_total_bytes=1),
            contract,
            allowed_receipts,
        ),
    )
    cases["manifest_total_record_budget_exceeded"] = _expected_exception_case(
        provider_api,
        "manifest_total_record_budget_exceeded",
        lambda: provider_api.build_export_manifest(
            _manifest_data(input_root, [PROVIDER_ARTIFACTS["prometheus_matrix_success"], PROVIDER_ARTIFACTS["loki_streams_success"]], max_total_records=1),
            contract,
            allowed_receipts,
        ),
    )
    cases["absolute_traversal_path_rejected"] = _expected_exception_case(
        provider_api,
        "unsafe_relative_path",
        lambda: provider_api.build_export_manifest(
            _manifest_data(input_root, [{**PROVIDER_ARTIFACTS["prometheus_matrix_success"], "relative_path": "/tmp/prometheus_matrix.json"}]),
            contract,
            allowed_receipts,
        ),
    )
    cases["symlink_hardlink_nonregular_rejected"] = _symlink_case(provider_api, input_root, contract, aggregate_activity)
    cases["source_id_reuse_changed_content_rejected"] = _source_reuse_case(
        provider_api, input_root, contract, aggregate_activity
    )
    cases["content_hash_mismatch_rejected"] = _content_hash_case(provider_api, input_root, contract, aggregate_activity)
    cases["file_mutation_replacement_rejected"] = _file_mutation_case(provider_api, input_root, contract, aggregate_activity)

    forged_bundle = deepcopy(dict(success_bundles[0]))
    forged_bundle["artifact_bytes"] += 1
    forged_bundle["bundle_hash"] = stable_hash({key: value for key, value in forged_bundle.items() if key != "bundle_hash"})
    cases["forged_bundle_receipt_ledger_rejected"] = _expected_exception_case(
        provider_api,
        "receipt_bundle_hash_mismatch",
        lambda: provider_api.validate_execution_ledger(success_ledger, manifest, contract, allowed_receipts, bundles=[forged_bundle, *success_bundles[1:5]]),
    )

    forged_ledger = deepcopy(dict(success_ledger))
    forged_ledger["authority_counters"]["network_call_count"] = 1
    forged_ledger["ledger_hash"] = stable_hash({key: value for key, value in forged_ledger.items() if key != "ledger_hash"})
    cases["nonzero_forbidden_authority_rejected"] = _expected_exception_case(
        provider_api,
        "network_call_count_nonzero",
        lambda: provider_api.validate_execution_ledger(forged_ledger, manifest, contract, allowed_receipts, bundles=success_bundles[:5]),
    )

    live_denial = _live_claim_denial(contract)
    cases["live_provider_credential_action_claim_rejected"] = _case(
        passed=live_denial["decision"] == "denied" and "authority_level_not_qualified" in live_denial["reasons"],
        outcome="rejected",
        provider=None,
        error="authority_level_not_qualified",
    )
    return cases


def _build_authority_context(input_root: Path, provider_api: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    core = build_contract_core(
        {
            "contract_id": AUTHORITY_CONTRACT_ID,
            "contract_version": 1,
            "subject_ref_hash": stable_hash({"subject": "p135-local-fixtures"}),
            "max_authority_level": "OA1_LOCAL_ARTIFACT",
            "allowed_hosts": [AUTHORITY_HOST_LABEL],
            "allowed_methods": ["LOCAL_READ_FILE"],
            "allowed_capabilities": [
                "telemetry.events.read",
                "telemetry.logs.read",
                "telemetry.metrics.read",
                "telemetry.topology.read",
                "telemetry.traces.read",
            ],
            "budgets": _p134_budgets(max_allowed_requests_per_window=32),
            "valid_from": "2026-07-13T00:00:00Z",
            "expires_at": "2026-07-14T00:00:00Z",
            "default_decision": "deny",
            "kill_switch": False,
            "action_authority": zero_p121_authority(),
        }
    )
    review = build_review_receipt(
        core,
        {
            "decision": "approve",
            "reviewer_ref_hash": stable_hash({"reviewer": "p135-public-api-reviewer"}),
            "reviewed_at": "2026-07-13T00:00:01Z",
            "expires_at": "2026-07-13T23:59:59Z",
        },
    )
    contract = build_contract(core, review)
    ledger = new_p134_receipt_ledger(contract, window_started_at="2026-07-13T00:00:00Z")
    receipts: list[dict[str, Any]] = []
    shared_post_read = [value for key, value in POST_READ_ARTIFACTS.items() if key != "utf8_string_line_budget_rejected"]
    for sequence, spec in enumerate([*PROVIDER_ARTIFACTS.values(), *shared_post_read, PROMPT_SECRET_ARTIFACT], start=1):
        proposal = build_proposal(_proposal_data(input_root, spec, sequence=sequence))
        result = evaluate_proposal(contract, proposal, ledger)
        if result.receipt["decision"] != "allowed":
            raise ValueError(f"authority_receipt_denied:{spec['source_id']}")
        receipts.append(result.receipt)
        ledger = result.ledger
    provider_api.validate_export_manifest(
        provider_api.build_export_manifest(_manifest_data(input_root, [PROVIDER_ARTIFACTS["prometheus_matrix_success"]]), contract, receipts),
        contract,
        receipts,
    )
    return contract, ledger, receipts


def _manifest_data(
    input_root: Path,
    specs: Sequence[Mapping[str, Any]],
    *,
    max_total_bytes: int = 1_000_000,
    max_total_records: int = 1_000,
) -> dict[str, Any]:
    return {
        "manifest_id": "p135-local-export",
        "manifest_version": 1,
        "created_at": "2026-07-13T00:05:00Z",
        "root_ref_hash": stable_hash({"root": str(input_root.resolve())}),
        "limits": {
            "max_artifacts": 16,
            "max_file_bytes": 100_000,
            "max_total_bytes": max_total_bytes,
            "max_records_per_artifact": 100,
            "max_total_records": max_total_records,
            "max_json_depth": 32,
            "max_json_nodes": 20_000,
            "max_string_bytes": 4096,
            "max_preview_bytes": 96,
            "max_attributes_per_record": 32,
            "max_line_bytes": min([int(spec.get("max_line_bytes", 8192)) for spec in specs] or [8192]),
        },
        "artifacts": [_artifact_input(input_root, spec) for spec in specs],
    }


def _artifact_input(input_root: Path, spec: Mapping[str, Any]) -> dict[str, Any]:
    relative_path = str(spec.get("relative_path", spec["fixture"]))
    path = input_root / str(spec["fixture"])
    content = path.read_bytes() if path.is_file() else b""
    return {
        "source_id": spec["source_id"],
        "provider": spec["provider"],
        "format": spec["format"],
        "signal_family": spec["signal_family"],
        "relative_path": relative_path,
        "expected_content_hash": "sha256:" + hashlib.sha256(content).hexdigest(),
        "expected_bytes": int(spec.get("expected_bytes", len(content))),
        "expected_records": spec["expected_records"],
        "authority_capability": spec["capability"],
        "authority_source_ref_hash": stable_hash({"p135_source_id": spec["source_id"]}),
    }


def _proposal_data(
    input_root: Path,
    spec: Mapping[str, Any],
    *,
    sequence: int,
    capability: str | None = None,
    method: str = "LOCAL_READ_FILE",
    requested_level: str = "OA1_LOCAL_ARTIFACT",
    estimated_response_bytes: int | None = None,
    estimated_records: int | None = None,
) -> dict[str, Any]:
    artifact = _artifact_input(input_root, spec)
    return {
        "request_id": f"{AUTHORITY_REQUEST_ID_PREFIX}{sequence}",
        "sequence": sequence,
        "proposed_at": f"2026-07-13T00:{sequence % 60:02d}:00Z",
        "requested_level": requested_level,
        "source_ref_hash": artifact["authority_source_ref_hash"],
        "host_label": AUTHORITY_HOST_LABEL,
        "method": method,
        "capability": capability or str(artifact["authority_capability"]),
        "estimated_response_bytes": artifact["expected_bytes"] if estimated_response_bytes is None else estimated_response_bytes,
        "estimated_records": artifact["expected_records"] if estimated_records is None else estimated_records,
        "timeout_ms": 1000,
        "attempt_number": 1,
    }


def _allowed_receipt(
    contract: Mapping[str, Any],
    input_root: Path,
    spec: Mapping[str, Any],
    *,
    capability: str | None = None,
    estimated_response_bytes: int | None = None,
    estimated_records: int | None = None,
) -> dict[str, Any]:
    ledger = new_p134_receipt_ledger(contract, window_started_at="2026-07-13T00:00:00Z")
    proposal = build_proposal(
        _proposal_data(
            input_root,
            spec,
            sequence=1,
            capability=capability,
            estimated_response_bytes=estimated_response_bytes,
            estimated_records=estimated_records,
        )
    )
    return evaluate_proposal(contract, proposal, ledger).receipt


def _denied_receipt(contract: Mapping[str, Any], input_root: Path, spec: Mapping[str, Any]) -> dict[str, Any]:
    ledger = new_p134_receipt_ledger(contract, window_started_at="2026-07-13T00:00:00Z")
    proposal = build_proposal(_proposal_data(input_root, spec, sequence=1, method="HTTP_GET"))
    result = evaluate_proposal(contract, proposal, ledger)
    if result.receipt["decision"] != "denied":
        raise ValueError("expected_denied_receipt")
    return result.receipt


def _live_claim_denial(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    ledger = new_p134_receipt_ledger(contract, window_started_at="2026-07-13T00:00:00Z")
    proposal = build_proposal(
        {
            "request_id": f"{AUTHORITY_REQUEST_ID_PREFIX}live",
            "sequence": 1,
            "proposed_at": "2026-07-13T00:01:00Z",
            "requested_level": "OA4_CREDENTIAL_OR_EXTERNAL_READ",
            "source_ref_hash": stable_hash({"source": "live-claim"}),
            "host_label": AUTHORITY_HOST_LABEL,
            "method": "HTTP_GET",
            "capability": "telemetry.metrics.read",
            "estimated_response_bytes": 1,
            "estimated_records": 1,
            "timeout_ms": 1000,
            "attempt_number": 1,
        }
    )
    return evaluate_proposal(contract, proposal, ledger).receipt


def _p134_budgets(**overrides: int) -> dict[str, int]:
    budgets = {
        "window_seconds": 3600,
        "max_allowed_requests_per_window": 32,
        "max_allowed_estimated_response_bytes_per_window": 1_000_000,
        "max_allowed_estimated_records_per_window": 10_000,
        "max_unique_hosts_per_window": 3,
        "max_unique_methods_per_window": 1,
        "max_unique_capabilities_per_window": 6,
        "max_single_response_bytes": 100_000,
        "max_timeout_ms": 5_000,
        "max_attempt_number": 1,
    }
    budgets.update(overrides)
    return budgets


def _attach(
    provider_api: Any,
    root: Path,
    manifest: Mapping[str, Any],
    source_id: str,
    contract: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    ledger: Mapping[str, Any],
    *,
    read_chunk: Callable[[int, int], bytes] | None = None,
) -> Any:
    return provider_api.attach_export(
        root,
        manifest,
        source_id,
        contract,
        receipts,
        ledger,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        read_chunk=read_chunk,
    )


def _expected_exception_case(
    provider_api: Any,
    expected: str,
    action: Callable[[], Any],
    *,
    aggregate_activity: dict[str, int] | None = None,
) -> dict[str, Any]:
    del provider_api
    return _expected_exception_case_any(
        expected,
        (expected,),
        action,
        aggregate_activity=aggregate_activity,
    )


def _expected_exception_case_any(
    public_error: str,
    expected: Sequence[str],
    action: Callable[[], Any],
    *,
    aggregate_activity: dict[str, int] | None = None,
) -> dict[str, Any]:
    try:
        action()
    except Exception as exc:  # noqa: BLE001 - release matrix records the provider/core fail-closed reason.
        activity = getattr(exc, "activity", None)
        if aggregate_activity is not None and isinstance(activity, Mapping):
            _add_activity(aggregate_activity, activity)
        return _case(
            passed=any(item in str(exc) for item in expected),
            outcome="rejected",
            provider=None,
            error=public_error,
        )
    return _case(passed=False, outcome="rejected", provider=None, error=f"missing:{public_error}")


def _symlink_case(provider_api: Any, input_root: Path, contract: Mapping[str, Any], aggregate_activity: dict[str, int]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="p135-symlink-", dir="/tmp") as tmp:
        root = Path(tmp)
        shutil.copyfile(input_root / "prometheus_matrix.json", root / "real.json")
        (root / "symlink.json").symlink_to("real.json")
        spec = {**PROVIDER_ARTIFACTS["prometheus_matrix_success"], "source_id": "symlink-case", "fixture": "symlink.json", "relative_path": "symlink.json"}
        receipt = _allowed_receipt(contract, root, spec)
        manifest = provider_api.build_export_manifest(_manifest_data(root, [spec]), contract, [receipt])
        ledger = provider_api.new_execution_ledger(manifest)
        return _expected_exception_case(
            provider_api,
            "symlink_rejected",
            lambda: _attach(provider_api, root, manifest, "symlink-case", contract, [receipt], ledger),
        )


def _source_reuse_case(
    provider_api: Any,
    input_root: Path,
    contract: Mapping[str, Any],
    aggregate_activity: dict[str, int],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="p135-source-reuse-", dir="/tmp") as tmp:
        root = Path(tmp)
        target = root / "prometheus_matrix.json"
        shutil.copyfile(input_root / "prometheus_matrix.json", target)
        spec = PROVIDER_ARTIFACTS["prometheus_matrix_success"]
        receipt = _allowed_receipt(contract, root, spec)
        manifest = provider_api.build_export_manifest(_manifest_data(root, [spec]), contract, [receipt])
        first = _attach(
            provider_api,
            root,
            manifest,
            "prometheus-matrix",
            contract,
            [receipt],
            provider_api.new_execution_ledger(manifest),
        )
        _add_activity(aggregate_activity, first.activity)
        changed = target.read_bytes().replace(b'"5"', b'"6"', 1)
        target.write_bytes(changed)
        return _expected_exception_case(
            provider_api,
            "content_hash_mismatch",
            lambda: _attach(
                provider_api,
                root,
                manifest,
                "prometheus-matrix",
                contract,
                [receipt],
                first.ledger,
            ),
            aggregate_activity=aggregate_activity,
        )


def _content_hash_case(provider_api: Any, input_root: Path, contract: Mapping[str, Any], aggregate_activity: dict[str, int]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="p135-content-", dir="/tmp") as tmp:
        root = Path(tmp)
        shutil.copyfile(input_root / "prometheus_matrix.json", root / "prometheus_matrix.json")
        spec = PROVIDER_ARTIFACTS["prometheus_matrix_success"]
        receipt = _allowed_receipt(contract, root, spec)
        manifest = provider_api.build_export_manifest(_manifest_data(root, [spec]), contract, [receipt])
        (root / "prometheus_matrix.json").write_text('{"status":"success","data":{"resultType":"matrix","result":[]}}', encoding="utf-8")
        ledger = provider_api.new_execution_ledger(manifest)
        return _expected_exception_case_any(
            "content_hash_mismatch",
            ("content_hash_mismatch", "file_size_mismatch"),
            lambda: _attach(provider_api, root, manifest, "prometheus-matrix", contract, [receipt], ledger),
            aggregate_activity=aggregate_activity,
        )


def _line_budget_case(provider_api: Any, input_root: Path, contract: Mapping[str, Any], aggregate_activity: dict[str, int]) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = POST_READ_ARTIFACTS["utf8_string_line_budget_rejected"]
    receipt = _allowed_receipt(contract, input_root, spec)
    manifest = provider_api.build_export_manifest(_manifest_data(input_root, [spec]), contract, [receipt])
    result = _attach(provider_api, input_root, manifest, str(spec["source_id"]), contract, [receipt], provider_api.new_execution_ledger(manifest))
    _add_activity(aggregate_activity, result.activity)
    provider_api.validate_denominator_failure_bundle(result.bundle)
    expected_error = str(spec["expected_error"])
    return (
        _case(
            passed=result.receipt["status"] == "failed" and result.bundle.get("failure_reason") == expected_error,
            outcome="rejected",
            provider=None,
            error=expected_error,
        ),
        deepcopy(dict(result.bundle)),
    )


def _file_mutation_case(provider_api: Any, input_root: Path, contract: Mapping[str, Any], aggregate_activity: dict[str, int]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="p135-mutation-", dir="/tmp") as tmp:
        root = Path(tmp)
        target = root / "prometheus_matrix.json"
        shutil.copyfile(input_root / "prometheus_matrix.json", target)
        spec = PROVIDER_ARTIFACTS["prometheus_matrix_success"]
        receipt = _allowed_receipt(contract, root, spec)
        manifest = provider_api.build_export_manifest(_manifest_data(root, [spec]), contract, [receipt])
        ledger = provider_api.new_execution_ledger(manifest)
        original_read = provider_api.os.read
        mutated = False

        def patched_read(fd: int, size: int) -> bytes:
            nonlocal mutated
            chunk = original_read(fd, size)
            if chunk and not mutated:
                replacement = root / ".replacement.json"
                replacement.write_bytes(target.read_bytes())
                os.replace(replacement, target)
                mutated = True
            return chunk

        return _expected_exception_case(
            provider_api,
            "file_identity_changed",
            lambda: _attach(
                provider_api,
                root,
                manifest,
                "prometheus-matrix",
                contract,
                [receipt],
                ledger,
                read_chunk=patched_read,
            ),
            aggregate_activity=aggregate_activity,
        )


def _sensitive_attribute_hash_absent(bundle: Mapping[str, Any]) -> bool:
    serialized = json.dumps(bundle, sort_keys=True)
    if any(marker in serialized for marker in ("sk_live_secret", "api_key", "ignore previous instructions")):
        return False
    records = _sequence(bundle.get("records"), "records")
    return any(str(value).startswith("sha256:") for record in records for value in _mapping(record["p120_record"]["labels"], "labels").values())


def _revalidate_provider_artifacts(execution_ledger: Mapping[str, Any], bundles: Mapping[str, Any]) -> None:
    provider_api = _provider_api()
    container = _mapping(bundles, "normalized_bundles")
    required = {
        "schema_version",
        "manifest",
        "p134_contract",
        "p134_receipt_ledger",
        "p134_allowed_receipts",
        "success_bundles",
        "failure_bundles",
        "duplicate_result",
        "validation_context",
        "bundles_hash",
    }
    _expect_fields(container, frozenset(required), "normalized_bundles")
    if container.get("schema_version") != BUNDLES_SCHEMA_VERSION:
        raise ValueError("invalid_normalized_bundles_schema")
    if container.get("bundles_hash") != stable_hash({key: value for key, value in container.items() if key != "bundles_hash"}):
        raise ValueError("normalized_bundles_hash_invalid")
    manifest = _mapping(container["manifest"], "manifest")
    contract = _mapping(container["p134_contract"], "p134_contract")
    receipts = _sequence(container["p134_allowed_receipts"], "p134_allowed_receipts")
    success_bundles = _sequence(container["success_bundles"], "success_bundles")
    failure_bundles = _sequence(container["failure_bundles"], "failure_bundles")
    provider_api.validate_export_manifest(manifest, contract, receipts)
    for bundle in success_bundles:
        provider_api.validate_normalized_bundle(bundle)
    for bundle in failure_bundles:
        provider_api.validate_denominator_failure_bundle(bundle)
    provider_api.validate_execution_ledger(execution_ledger, manifest, contract, receipts, bundles=success_bundles[:5])


def _normalized_bundles_container(
    *,
    manifest: Mapping[str, Any],
    contract: Mapping[str, Any],
    p134_ledger: Mapping[str, Any],
    allowed_receipts: Sequence[Mapping[str, Any]],
    success_bundles: Sequence[Mapping[str, Any]],
    failure_bundles: Sequence[Mapping[str, Any]],
    duplicate_result: Mapping[str, Any] | None,
    provider_success_ledger: Mapping[str, Any],
) -> dict[str, Any]:
    container: dict[str, Any] = {
        "schema_version": BUNDLES_SCHEMA_VERSION,
        "manifest": deepcopy(dict(manifest)),
        "p134_contract": deepcopy(dict(contract)),
        "p134_receipt_ledger": deepcopy(dict(p134_ledger)),
        "p134_allowed_receipts": [deepcopy(dict(receipt)) for receipt in allowed_receipts],
        "success_bundles": [deepcopy(dict(bundle)) for bundle in success_bundles],
        "failure_bundles": [deepcopy(dict(bundle)) for bundle in failure_bundles],
        "duplicate_result": deepcopy(dict(duplicate_result or {})),
        "validation_context": {
            "provider_success_ledger_hash": provider_success_ledger["ledger_hash"],
            "promoted_success_bundle_hashes": [bundle["bundle_hash"] for bundle in success_bundles[:5]],
            "failure_bundle_hashes": [bundle["bundle_hash"] for bundle in failure_bundles],
            "p134_allowed_receipt_hashes": [receipt["receipt_hash"] for receipt in allowed_receipts],
            "p134_contract_hash": contract["contract_hash"],
            "manifest_hash": manifest["manifest_hash"],
        },
    }
    container["bundles_hash"] = stable_hash(container)
    return container


def _validate_provider_zero_contract(provider_api: Any) -> None:
    provider_forbidden = provider_api.zero_forbidden_authority()
    provider_activity = provider_api.zero_observation_activity()
    if any(type(value) is not int or value != 0 for value in provider_forbidden.values()):
        raise ValueError("provider_forbidden_authority_contract_mismatch")
    if set(provider_activity) != set(OBSERVATION_ACTIVITY_COUNTERS):
        raise ValueError("provider_observation_activity_contract_mismatch")


def _case(*, passed: bool, outcome: str, provider: str | None, error: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "passed": passed,
        "outcome": outcome,
        "provider": provider,
        "error": error,
        "authority_zero": False,
        "no_network_credentials_actions": False,
    }
    payload["case_hash"] = stable_hash(payload)
    return payload


def _provider_api() -> Any:
    return importlib.import_module("app.services.p135_provider_export_attachment")


def _profile_input_root(profile: Mapping[str, Any], *, profile_path: Path) -> Path:
    del profile_path
    relative = Path(str(profile["input_root"]))
    return (ROOT / relative).resolve()


def _add_activity(total: dict[str, int], activity: Mapping[str, Any]) -> None:
    for key in OBSERVATION_ACTIVITY_COUNTERS:
        value = activity[key]
        if type(value) is not int or value < 0:
            raise ValueError(f"invalid_activity:{key}")
        total[key] += value


def _resource_usage(*, started_wall: float, started_cpu: int) -> dict[str, int]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "wall_time_ms": max(0, int((time.monotonic() - started_wall) * 1000)),
        "cpu_time_ms": max(0, _cpu_ms() - started_cpu),
        "peak_memory_bytes": _peak_memory_bytes(int(usage.ru_maxrss)),
        **RESOURCE_LIMITS,
    }


def _cpu_ms() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return int((usage.ru_utime + usage.ru_stime) * 1000)


def _peak_memory_bytes(raw_maxrss: int, *, platform: str | None = None) -> int:
    """Normalize ru_maxrss, which is bytes on macOS and KiB on Linux/BSD."""

    return max(0, raw_maxrss if (platform or sys.platform) == "darwin" else raw_maxrss * 1024)


def _write_exact_artifacts(output_dir: Path, payloads: Mapping[str, Mapping[str, Any]]) -> None:
    if set(payloads) != EXPECTED_ARTIFACTS:
        raise ValueError("artifact_set_invalid")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(payloads):
        path = output_dir / name
        temporary = output_dir / f".{name}.tmp"
        temporary.write_text(json.dumps(payloads[name], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"invalid_{label}")
    return value


def _sequence(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"invalid_{label}")
    return list(value)


def _expect_fields(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = {str(key) for key in value}
    extra = sorted(actual - expected)
    if extra:
        raise ValueError(f"unexpected_{label}_field:{extra[0]}")
    missing = sorted(expected - actual)
    if missing:
        raise ValueError(f"missing_{label}_field:{missing[0]}")


if __name__ == "__main__":
    raise SystemExit(main())
