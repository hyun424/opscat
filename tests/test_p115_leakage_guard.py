from __future__ import annotations

import pytest

from app.services.p115_leakage_guard import P115LeakageError, require_leakage_free, scan_candidate_visible_artifact


def test_clean_candidate_artifact_has_exact_zero_findings_and_stable_hash() -> None:
    artifact = {"case_id": "case-1", "evidence_ids": ["ev-1"], "rollback_plan": {"rollback_id": "restore_pool"}}
    first = scan_candidate_visible_artifact(artifact)
    second = scan_candidate_visible_artifact(artifact)
    assert first.clean is True
    assert first.findings == ()
    assert first.report_hash == second.report_hash


@pytest.mark.parametrize(
    ("artifact", "path", "code"),
    [
        ({"GroundTruth": "restart"}, "candidate.json", "hidden_outcome_key"),
        ({"nested": {"scorer-only-truth": "restart"}}, "candidate.json", "hidden_outcome_key"),
        ({"notes": "ground truth: restart"}, "candidate.md", "forbidden_text_leak"),
        ({"validation": {"command": "kubectl restart production"}}, "candidate.json", "authority_or_credential_field"),
        ({"description": "api_key = secret-value"}, "candidate.json", "forbidden_text_leak"),
        ({"description": "target production cluster"}, "candidate.json", "forbidden_text_leak"),
        ({"case_id": "case-1"}, "fixtures/hidden-outcome.json", "filename_outcome_leak"),
    ],
)
def test_named_red_leaks_fail_closed(artifact: object, path: str, code: str) -> None:
    report = scan_candidate_visible_artifact(artifact, artifact_path=path)
    assert report.clean is False
    assert code in {finding["code"] for finding in report.findings}
    with pytest.raises(P115LeakageError):
        require_leakage_free(artifact, artifact_path=path)
