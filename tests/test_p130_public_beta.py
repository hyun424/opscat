from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters
from app.services.p130_public_beta import (
    P130_PHASES,
    build_p130_public_beta,
    validate_p130_release_evidence,
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _self_hashed(payload: dict[str, Any], field: str) -> dict[str, Any]:
    payload[field] = stable_hash({key: value for key, value in payload.items() if key != field})
    return payload


def _release_payload(phase: int) -> dict[str, Any]:
    return _self_hashed(
        {
            "schema_version": f"p{phase}.release_evidence.v1",
            "release_id": f"P{phase}-fixture",
            "release_status": f"p{phase}_ready",
            "product_claim": f"P{phase} local sandbox evidence is ready.",
            "public_limitation": "Local, sandbox, replay, or disposable-lab evidence only; no credentials, live production, or operator replacement.",
            "authority": {"counters": zero_authority_counters()},
            "gates": {"ready": True},
        },
        "release_evidence_hash",
    )


def _review_payload(*, reviewer_id: str = "independent-reviewer", builder_id: str = "builder", root: Path) -> dict[str, Any]:
    reviewed_hashes = {
        f"p{phase}": json.loads((root / f"evals/p{phase}/release-evidence.json").read_text(encoding="utf-8"))["release_evidence_hash"]
        for phase in P130_PHASES
    }
    return _self_hashed(
        {
            "schema_version": "p130.independent_review.v1",
            "verdict": "PASS",
            "reviewer_id": reviewer_id,
            "builder_id": builder_id,
            "reviewed_release_hashes": reviewed_hashes,
            "review_date": "2026-07-12",
            "review_method": "codex_native_subagent",
            "scope": "P130 public beta aggregation fixtures",
            "notes": "Fixture review binds every upstream release hash.",
        },
        "self_hash",
    )


def _claim_inputs() -> dict[str, Any]:
    return {
        "schema_version": "p130.claim_input.v1",
        "claims": [
            {
                "claim_id": "p130-local-beta-framework",
                "statement": "OpsCat has an evidence-qualified public beta readiness framework for local, sandbox, replay, and disposable-lab evidence.",
                "owner": "ops-beta",
                "status": "supported",
                "evidence": [{"phase": f"p{phase}", "artifact": f"evals/p{phase}/release-evidence.json"} for phase in P130_PHASES],
                "test": "tests/test_p130_public_beta.py",
                "limitation": "Evidence-qualified and non-production only.",
                "scope": "local sandbox replay disposable-lab beta readiness framework",
                "review_date": "2026-07-12",
                "withdrawal_path": "Remove public beta claim and publish correction if any bound upstream hash changes or gate fails.",
            },
            {
                "claim_id": "p130-feedback-no-credential-process",
                "statement": "Beta feedback intake uses no credentials or production access.",
                "owner": "ops-support",
                "status": "limited",
                "evidence": [{"phase": "p129", "artifact": "evals/p129/release-evidence.json"}],
                "test": "tests/test_p130_public_beta.py",
                "limitation": "Feedback is offline and non-credentialed; auth is deferred.",
                "scope": "non-credentialed feedback intake",
                "review_date": "2026-07-12",
                "withdrawal_path": "Disable feedback intake language if credential-free handling cannot be preserved.",
            },
        ],
    }


def _risk_inputs() -> dict[str, Any]:
    return {
        "schema_version": "p130.risk_input.v1",
        "risks": [
            {
                "risk_id": "p130-non-production-evidence-limit",
                "description": "Local and disposable-lab evidence does not prove live production effectiveness.",
                "severity": "medium",
                "status": "open",
                "owner": "ops-beta",
                "mitigation": "Keep public beta language evidence-qualified and non-production.",
                "residual_risk": "Users may overread beta claims without limitation text.",
                "review_date": "2026-07-12",
                "stop_or_rollback_condition": "Withdraw public beta language if limitations are removed or contradicted.",
            }
        ],
    }


def _feedback_inputs() -> dict[str, Any]:
    return {
        "schema_version": "p130.feedback_input.v1",
        "requires_credentials": False,
        "requires_production_access": False,
        "requires_live_connector": False,
        "intake_paths": ["public issue template without secrets", "email alias with secret-redaction instructions"],
        "support_boundary": "No credential handling, no production access, no live remediation.",
    }


def _exit_inputs() -> dict[str, Any]:
    return {
        "schema_version": "p130.exit_policy_input.v1",
        "withdrawal_paths_visible": True,
        "exit_criteria": ["distinct reviewer PASS remains current", "all upstream release hashes remain current"],
        "rollback_paths": ["unpublish beta claim ledger", "publish correction with failed gate reasons"],
    }


def _fixture_root(tmp_path: Path) -> Path:
    for phase in P130_PHASES:
        _write_json(tmp_path / f"evals/p{phase}/release-evidence.json", _release_payload(phase))
    _write_json(tmp_path / "evals/p130/independent-review.json", _review_payload(root=tmp_path))
    _write_json(tmp_path / "evals/p130/input/claims.json", _claim_inputs())
    _write_json(tmp_path / "evals/p130/input/risks.json", _risk_inputs())
    _write_json(tmp_path / "evals/p130/input/feedback.json", _feedback_inputs())
    _write_json(tmp_path / "evals/p130/input/exit-policy.json", _exit_inputs())
    return tmp_path


def test_builds_public_beta_aggregation_from_current_fixture_evidence(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)

    bundle = build_p130_public_beta(root=root, builder_id="builder", reviewer_id="independent-reviewer")

    release = bundle["release_evidence"]
    assert release["release_status"] == "p130_public_beta_qualified"
    assert release["gates"]["traceability_1_0"] is True
    assert release["gates"]["zero_undocumented_or_untraced_claims"] is True
    assert release["gates"]["zero_high_critical_blockers"] is True
    assert release["gates"]["zero_prohibited_claims"] is True
    assert release["gates"]["exact_zero_runtime_authority"] is True
    assert release["gates"]["visible_withdrawal_paths"] is True
    assert set(release["upstream_release_hashes"]) == {f"p{phase}" for phase in P130_PHASES}
    assert bundle["claim_ledger"]["traceability_ratio"] == 1.0
    assert bundle["risk_register"]["high_critical_open_blockers"] == []
    assert validate_p130_release_evidence(release, root=root)["valid"] is True


def test_missing_independent_review_fails_closed_without_fabricating_pass(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    (root / "evals/p130/independent-review.json").unlink()

    release = build_p130_public_beta(root=root, builder_id="builder", reviewer_id="independent-reviewer")["release_evidence"]

    assert release["release_status"] == "p130_blocked"
    assert release["gates"]["independent_review_passed"] is False
    assert release["review"]["artifact"] == {}


def test_rejects_self_review_even_with_pass_verdict(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    _write_json(root / "evals/p130/independent-review.json", _review_payload(root=root, reviewer_id="builder", builder_id="builder"))

    release = build_p130_public_beta(root=root, builder_id="builder", reviewer_id="builder")["release_evidence"]

    assert release["release_status"] == "p130_blocked"
    assert release["gates"]["distinct_reviewer"] is False
    assert release["gates"]["independent_review_passed"] is False


def test_rejects_review_without_explicit_provenance(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    review = json.loads((root / "evals/p130/independent-review.json").read_text(encoding="utf-8"))
    review.pop("review_method")
    review = _self_hashed(review, "self_hash")
    _write_json(root / "evals/p130/independent-review.json", review)

    release = build_p130_public_beta(root=root, builder_id="builder", reviewer_id="independent-reviewer")["release_evidence"]

    assert release["release_status"] == "p130_blocked"
    assert release["gates"]["independent_review_passed"] is False


def test_rejects_incomplete_or_unknown_authority_counter_maps(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    evidence_path = root / "evals/p127/release-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["authority"] = {"counters": {"made_up_counter": 0}}
    evidence = _self_hashed(evidence, "release_evidence_hash")
    _write_json(evidence_path, evidence)

    release = build_p130_public_beta(root=root, builder_id="builder", reviewer_id="independent-reviewer")["release_evidence"]

    assert release["release_status"] == "p130_blocked"
    assert release["gates"]["exact_zero_runtime_authority"] is False


def test_review_must_bind_current_upstream_hashes(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    changed = _release_payload(123)
    changed["product_claim"] = "Changed local evidence."
    changed = _self_hashed(changed, "release_evidence_hash")
    _write_json(root / "evals/p123/release-evidence.json", changed)

    release = build_p130_public_beta(root=root, builder_id="builder", reviewer_id="independent-reviewer")["release_evidence"]

    assert release["release_status"] == "p130_blocked"
    assert release["gates"]["independent_review_passed"] is False
    assert release["gates"]["current_upstream_evidence_hashes"] is True


def test_rejects_tampered_upstream_self_hash(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    tampered = json.loads((root / "evals/p124/release-evidence.json").read_text(encoding="utf-8"))
    tampered["product_claim"] = "Tampered without rehash."
    _write_json(root / "evals/p124/release-evidence.json", tampered)

    release = build_p130_public_beta(root=root, builder_id="builder", reviewer_id="independent-reviewer")["release_evidence"]

    assert release["release_status"] == "p130_blocked"
    assert release["gates"]["current_upstream_evidence_hashes"] is False


def test_rejects_prohibited_public_beta_claims(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    claims = _claim_inputs()
    claims["claims"][0]["statement"] = "OpsCat is production ready with live connector proof."
    _write_json(root / "evals/p130/input/claims.json", claims)

    release = build_p130_public_beta(root=root, builder_id="builder", reviewer_id="independent-reviewer")["release_evidence"]

    assert release["release_status"] == "p130_blocked"
    assert release["gates"]["zero_prohibited_claims"] is False
    assert "p130-local-beta-framework" in release["claim_summary"]["prohibited_claims"]


def test_rejects_missing_claim_limitation_and_withdrawal_path(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    claims = _claim_inputs()
    claims["claims"][0]["limitation"] = ""
    claims["claims"][1]["withdrawal_path"] = ""
    _write_json(root / "evals/p130/input/claims.json", claims)

    release = build_p130_public_beta(root=root, builder_id="builder", reviewer_id="independent-reviewer")["release_evidence"]

    assert release["release_status"] == "p130_blocked"
    assert release["gates"]["zero_undocumented_or_untraced_claims"] is False
    assert release["gates"]["visible_withdrawal_paths"] is False


def test_rejects_missing_risk_owner_and_high_critical_blocker(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    risks = _risk_inputs()
    risks["risks"][0]["owner"] = ""
    risks["risks"][0]["severity"] = "critical"
    _write_json(root / "evals/p130/input/risks.json", risks)

    release = build_p130_public_beta(root=root, builder_id="builder", reviewer_id="independent-reviewer")["release_evidence"]

    assert release["release_status"] == "p130_blocked"
    assert release["gates"]["risk_register_complete"] is False
    assert release["gates"]["zero_high_critical_blockers"] is False


def test_rejects_credentials_live_production_and_nonzero_authority(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    feedback = _feedback_inputs()
    feedback["requires_credentials"] = True
    feedback["requires_production_access"] = True
    _write_json(root / "evals/p130/input/feedback.json", feedback)
    p125 = json.loads((root / "evals/p125/release-evidence.json").read_text(encoding="utf-8"))
    p125["authority"]["counters"]["production_mutation_count"] = 1
    p125 = _self_hashed(p125, "release_evidence_hash")
    _write_json(root / "evals/p125/release-evidence.json", p125)

    release = build_p130_public_beta(root=root, builder_id="builder", reviewer_id="independent-reviewer")["release_evidence"]

    assert release["release_status"] == "p130_blocked"
    assert release["gates"]["feedback_requires_no_credentials_or_production_access"] is False
    assert release["gates"]["exact_zero_runtime_authority"] is False


def test_validation_rebuilds_and_rejects_outer_rehash_forgery(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    release = build_p130_public_beta(root=root, builder_id="builder", reviewer_id="independent-reviewer")["release_evidence"]
    forged = copy.deepcopy(release)
    forged["gates"]["zero_prohibited_claims"] = False
    forged["release_evidence_hash"] = stable_hash({key: value for key, value in forged.items() if key != "release_evidence_hash"})

    result = validate_p130_release_evidence(forged, root=root)

    assert result["valid"] is False
    assert result["checks"]["all_fields_current"] is False
    assert result["checks"]["self_hash_current"] is True


def test_builder_and_validator_cli_round_trip_with_temp_outputs(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    build = subprocess.run(
        [
            sys.executable,
            "scripts/build_p130_public_beta.py",
            "--root",
            str(root),
            "--builder-id",
            "builder",
            "--reviewer-id",
            "independent-reviewer",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    for name in ("claim-ledger.json", "risk-register.json", "beta-evidence.json", "release-evidence.json"):
        assert (root / "evals/p130" / name).is_file()

    validate = subprocess.run(
        [sys.executable, "scripts/validate_p130_public_beta.py", str(root / "evals/p130/release-evidence.json"), "--root", str(root)],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert json.loads(validate.stdout)["valid"] is True


def test_builder_cli_returns_nonzero_when_review_missing(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    (root / "evals/p130/independent-review.json").unlink()

    build = subprocess.run(
        [
            sys.executable,
            "scripts/build_p130_public_beta.py",
            "--root",
            str(root),
            "--builder-id",
            "builder",
            "--reviewer-id",
            "independent-reviewer",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert build.returncode == 1
    assert json.loads(build.stdout)["release_status"] == "p130_blocked"
