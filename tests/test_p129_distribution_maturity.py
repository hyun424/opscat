from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters
from app.services.p129_distribution_maturity import (
    P129_DISTRIBUTION_SCHEMA_VERSION,
    P129_RELEASE_SCHEMA_VERSION,
    _has_unbounded_claim,
    produce_p129_distribution_report,
    produce_p129_release_evidence,
    validate_p129_release_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


def _copy_p129_fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        "README.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "pyproject.toml",
        "uv.lock",
        "docs/install.md",
        "docs/installation.md",
        "docs/compatibility.md",
        "docs/limitations.md",
        "docs/public-contracts.md",
        "docs/operations/p129-oss-distribution-maturity-roadmap.md",
        "docs/operations/p129-test-spec.md",
        "docs/operations/p129-plan-review.md",
        "docs/operations/p129-verification-handoff.md",
        "docs/tickets/p129/README.md",
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    shutil.copytree(ROOT / "evals/p122", root / "evals/p122")
    return root


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_distribution_report_aggregates_existing_evidence_without_claim_inflation() -> None:
    report = produce_p129_distribution_report(root=ROOT, reviewer_id="independent-p129-verifier", builder_id="autonomous-builder")

    assert report["schema_version"] == P129_DISTRIBUTION_SCHEMA_VERSION
    assert report["status"] == "p129_distribution_maturity_ready"
    assert all(report["gates"].values())
    assert report["product_claim"] == "OSS distribution maturity with local/mock/sandbox qualification"
    assert "Production autonomy" in report["public_limitation"]
    assert report["authority"]["exact_nonlocal_authority_zero"] is True
    assert report["authority"]["nonzero_authority_counters"] == {}
    assert report["authority"]["counters"] == zero_authority_counters()
    assert report["p122_evidence"]["release_status"] == "p122_open_source_local_rc"
    assert report["p122_evidence"]["release_evidence_hash"] == json.loads((ROOT / "evals/p122/release-evidence.json").read_text())["release_evidence_hash"]
    assert report["packaging"]["reproducible_wheel_and_sdist"] is True
    assert report["packaging"]["clean_install_contract_demo_uninstall"] is True
    assert report["security"]["detected_secrets"] == 0
    assert report["security"]["high_or_critical_vulnerabilities"] == 0
    assert report["supply_chain"]["sbom_completeness"] == 1.0
    assert report["supply_chain"]["license_completeness"] == 1.0
    assert report["imports"]["stable_internal_boundary_declared"] is True
    assert report["imports"]["unresolved_contract_refs"] == []
    assert set(report["compatibility"]["python_versions"]) == {"3.12", "3.13", "3.14"}
    assert all(item["status"] in {"available", "pending_unavailable"} for item in report["compatibility"]["python_versions"].values())
    assert "production-ready" not in json.dumps(report).lower()
    assert report["report_hash"] == stable_hash({key: value for key, value in report.items() if key != "report_hash"})


def test_release_evidence_is_self_hashed_and_revalidates_current_inputs() -> None:
    evidence = produce_p129_release_evidence(root=ROOT, reviewer_id="independent-p129-verifier", builder_id="autonomous-builder")

    assert evidence["schema_version"] == P129_RELEASE_SCHEMA_VERSION
    assert evidence["release_status"] == "p129_distribution_maturity_ready"
    assert evidence["distribution_report"]["schema_version"] == P129_DISTRIBUTION_SCHEMA_VERSION
    assert evidence["authority"]["counters"] == zero_authority_counters()
    assert evidence["distribution_report"]["authority"]["nonzero_authority_counters"] == {}
    assert evidence["release_evidence_hash"] == stable_hash({key: value for key, value in evidence.items() if key != "release_evidence_hash"})
    assert validate_p129_release_evidence(evidence, root=ROOT)["valid"] is True

    tampered = dict(evidence)
    tampered["product_claim"] = "production-ready OSS distribution"
    validation = validate_p129_release_evidence(tampered, root=ROOT)
    assert validation["valid"] is False
    assert "all_fields_current failed closed" in validation["reasons"]


def test_fail_closed_when_security_policy_is_missing(tmp_path: Path) -> None:
    root = _copy_p129_fixture_root(tmp_path)
    (root / "SECURITY.md").unlink()

    report = produce_p129_distribution_report(root=root, reviewer_id="independent-p129-verifier", builder_id="autonomous-builder")

    assert report["status"] == "p129_blocked"
    assert report["gates"]["governed_docs_valid"] is False
    assert any(item["path"] == "SECURITY.md" and item["status"] == "missing" for item in report["governed_docs"])


def test_fail_closed_on_high_or_critical_security_findings(tmp_path: Path) -> None:
    root = _copy_p129_fixture_root(tmp_path)
    security_report = json.loads((root / "evals/p122/security-report.json").read_text())
    security_report["severity_counts"]["high"] = 1
    _write_json(root / "evals/p122/security-report.json", security_report)

    report = produce_p129_distribution_report(root=root, reviewer_id="independent-p129-verifier", builder_id="autonomous-builder")

    assert report["status"] == "p129_blocked"
    assert report["gates"]["security_release_blockers_zero"] is False
    assert report["security"]["high_or_critical_security_findings"] == 1


def test_fail_closed_on_unknown_license(tmp_path: Path) -> None:
    root = _copy_p129_fixture_root(tmp_path)
    inventory = json.loads((root / "evals/p122/license-inventory.json").read_text())
    inventory["components"][0]["license"] = "LicenseRef-UNKNOWN"
    _write_json(root / "evals/p122/license-inventory.json", inventory)

    report = produce_p129_distribution_report(root=root, reviewer_id="independent-p129-verifier", builder_id="autonomous-builder")

    assert report["status"] == "p129_blocked"
    assert report["gates"]["sbom_license_complete"] is False
    assert report["supply_chain"]["unknown_license_count"] == 1


def test_fail_closed_on_nonzero_authority_counter(tmp_path: Path) -> None:
    root = _copy_p129_fixture_root(tmp_path)
    release = json.loads((root / "evals/p122/release-evidence.json").read_text())
    release["authority"]["exact_nonlocal_authority_zero"] = False
    release["authority"]["nonzero_phases"] = ["121"]
    _write_json(root / "evals/p122/release-evidence.json", release)

    report = produce_p129_distribution_report(root=root, reviewer_id="independent-p129-verifier", builder_id="autonomous-builder")

    assert report["status"] == "p129_blocked"
    assert report["gates"]["exact_nonlocal_authority_zero"] is False
    assert report["authority"]["nonzero_authority_counters"] == {"p122": ["121"]}


def test_fail_closed_on_self_review(tmp_path: Path) -> None:
    root = _copy_p129_fixture_root(tmp_path)

    report = produce_p129_distribution_report(root=root, reviewer_id="same-person", builder_id="same-person")

    assert report["status"] == "p129_blocked"
    assert report["gates"]["distinct_reviewer"] is False
    assert "distinct_reviewer failed closed" in report["reasons"]


def test_overclaim_detection_requires_directional_limitation_or_negation() -> None:
    assert _has_unbounded_claim("Capability claims must link to production-ready evidence.") is True
    assert _has_unbounded_claim("Do not claim production-ready OSS distribution.") is False
    assert _has_unbounded_claim("Production-ready operation remains out of scope.") is False
