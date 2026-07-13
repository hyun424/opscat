from __future__ import annotations

import importlib
from copy import deepcopy
from typing import Any

import pytest

from tests.fixtures.p136.builders import (
    RELEASE_STATUS,
    TEST_SOURCE_BINDINGS,
    independent_review_artifact,
    release_evidence,
)


def _release_api(*names: str) -> Any:
    try:
        module = importlib.import_module("app.services.p136_release_evidence")
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing P136 release evidence module/API: app.services.p136_release_evidence ({exc})")
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        pytest.fail(f"missing P136 release evidence module/API: {', '.join(missing)}")
    return module


def _error() -> type[Exception]:
    module = _release_api("P136ReleaseEvidenceError")
    return module.P136ReleaseEvidenceError


def _validate(api: Any, evidence: dict[str, Any]) -> dict[str, Any]:
    return api.validate_p136_release_evidence(
        evidence,
        expected_source_hashes=TEST_SOURCE_BINDINGS,
        independent_review=independent_review_artifact(),
    )


def test_release_evidence_accepts_exactly_50_cases_and_exact_qualified_status() -> None:
    api = _release_api("validate_p136_release_evidence")
    evidence = release_evidence(50, status=RELEASE_STATUS)

    validated = _validate(api, evidence)

    assert validated["totals"] == {"expected": 50, "passed": 50, "failed": 0}
    assert validated["status"] == RELEASE_STATUS
    assert len(validated["cases"]) == 50


def test_release_evidence_rejects_49_or_51_cases_even_when_totals_are_rehashed() -> None:
    api = _release_api("validate_p136_release_evidence")
    error = _error()

    with pytest.raises(error, match="p136_release_case_count_must_equal_50"):
        _validate(api, release_evidence(49, status=RELEASE_STATUS))
    with pytest.raises(error, match="p136_release_case_count_must_equal_50"):
        _validate(api, release_evidence(51, status=RELEASE_STATUS))


def test_release_evidence_rejects_status_drift_and_self_stamped_success() -> None:
    api = _release_api("validate_p136_release_evidence")
    error = _error()
    wrong_status = release_evidence(50, status="qualified")
    self_stamped = release_evidence(50, status=RELEASE_STATUS)
    self_stamped["cases"][17]["actual"] = "not-run"
    self_stamped["cases"][17]["status"] = "passed"

    with pytest.raises(error, match="invalid_p136_release_status"):
        _validate(api, wrong_status)
    with pytest.raises(error, match="case_actual_expected_mismatch"):
        _validate(api, self_stamped)


def test_release_evidence_rebuilds_totals_provider_promotions_and_duplicate_zero_claims() -> None:
    api = _release_api("validate_p136_release_evidence")
    error = _error()
    evidence = release_evidence(50, status=RELEASE_STATUS)
    forged_totals = deepcopy(evidence)
    forged_totals["totals"] = {"expected": 50, "passed": 50, "failed": 0}
    forged_totals["cases"][0]["status"] = "failed"
    forged_duplicates = deepcopy(evidence)
    forged_duplicates["cases"][8]["duplicate_segment_reads"] = 1
    measured_duplicates = deepcopy(evidence)
    measured_duplicates["cases"][8]["duplicate_segment_reads"] = 1
    measured_duplicates["cases"][8]["evidence"]["measured_duplicate_segment_reads"] = 1
    forged_provider_count = deepcopy(evidence)
    forged_provider_count["cases"][0]["provider_first_batch_promotion"] = False
    forged_provider_positions = deepcopy(evidence)
    forged_provider_positions["cases"][0]["provider_first_batch_promotion"] = False
    forged_provider_positions["cases"][5]["provider_first_batch_promotion"] = True

    with pytest.raises(error, match="rebuilt_totals_mismatch"):
        _validate(api, forged_totals)
    with pytest.raises(error, match="duplicate_segment_reads_must_be_zero"):
        _validate(api, forged_duplicates)
    with pytest.raises(error, match="duplicate_segment_reads_must_be_zero"):
        _validate(api, measured_duplicates)
    with pytest.raises(error, match="provider_first_batch_promotion_count_mismatch"):
        _validate(api, forged_provider_count)
    with pytest.raises(error, match="provider_first_batch_promotion_case_mismatch"):
        _validate(api, forged_provider_positions)


def test_release_evidence_rejects_nonzero_forbidden_authority_and_resource_budget_excess() -> None:
    api = _release_api("validate_p136_release_evidence")
    error = _error()
    authority_drift = release_evidence(50, status=RELEASE_STATUS)
    authority_drift["forbidden_authority"]["network_call_count"] = 1
    slow = release_evidence(50, status=RELEASE_STATUS)
    slow["resource_usage"]["wall_time_ms"] = 30_001
    cpu_heavy = release_evidence(50, status=RELEASE_STATUS)
    cpu_heavy["resource_usage"]["cpu_time_ms"] = 14_500
    cpu_heavy["resource_usage"]["child_cpu_time_ms"] = 501

    with pytest.raises(error, match="forbidden_authority_nonzero"):
        _validate(api, authority_drift)
    with pytest.raises(error, match="wall_time_budget_exceeded"):
        _validate(api, slow)
    with pytest.raises(error, match="self_plus_child_cpu_budget_exceeded"):
        _validate(api, cpu_heavy)


def test_release_evidence_rejects_absolute_paths_secret_values_and_unredacted_payloads() -> None:
    api = _release_api("validate_p136_release_evidence")
    error = _error()
    absolute_path = release_evidence(50, status=RELEASE_STATUS)
    absolute_path["cases"][2]["artifact_ref"] = "/tmp/creator-only/p136.json"
    secret_value = release_evidence(50, status=RELEASE_STATUS)
    secret_value["cases"][3]["redacted_sample"] = {"authorization": "Bearer secret-token"}
    raw_payload = release_evidence(50, status=RELEASE_STATUS)
    raw_payload["cases"][4]["raw_provider_payload"] = {"metric": "unredacted"}

    with pytest.raises(error, match="absolute_path_leak"):
        _validate(api, absolute_path)
    with pytest.raises(error, match="secret_value_leak"):
        _validate(api, secret_value)
    with pytest.raises(error, match="raw_provider_payload_leak"):
        _validate(api, raw_payload)


def test_release_evidence_requires_complete_independent_review_input() -> None:
    api = _release_api("validate_p136_release_evidence")
    error = _error()

    with pytest.raises(error, match="independent_review_required"):
        api.validate_p136_release_evidence(
            release_evidence(50, status=RELEASE_STATUS),
            expected_source_hashes=TEST_SOURCE_BINDINGS,
        )


def test_release_evidence_is_bound_to_current_independent_review_and_sources() -> None:
    api = _release_api("validate_p136_release_evidence", "validate_independent_review_artifact")
    error = _error()
    evidence = release_evidence(50, status=RELEASE_STATUS)
    review = independent_review_artifact()

    validated = api.validate_p136_release_evidence(
        evidence,
        expected_source_hashes=TEST_SOURCE_BINDINGS,
        independent_review=review,
    )
    assert validated["source_bindings"] == TEST_SOURCE_BINDINGS

    stale_sources = {**TEST_SOURCE_BINDINGS, "scripts/verify.sh": "sha256:" + ("0" * 64)}
    with pytest.raises(error, match="release_evidence_source_stale"):
        api.validate_p136_release_evidence(
            evidence,
            expected_source_hashes=stale_sources,
            independent_review=review,
        )

    blocked_review = independent_review_artifact()
    blocked_review["findings"]["p1"] = 1
    blocked_review["independent_review_hash"] = api.stable_hash(
        {key: value for key, value in blocked_review.items() if key != "independent_review_hash"}
    )
    with pytest.raises(error, match="review_blocking_findings"):
        api.validate_p136_release_evidence(
            evidence,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            independent_review=blocked_review,
        )
