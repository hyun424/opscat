from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.candidate_benchmark_promotion_gate import (
    CandidateBenchmarkPromotionGateReport,
    build_candidate_benchmark_promotion_gate_report,
    render_candidate_benchmark_promotion_gate_markdown,
)

CASES = Path("evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")


def test_candidate_benchmark_promotion_gate_promotes_improved_view_without_mutating_baseline() -> None:
    before = CASES.read_text(encoding="utf-8")
    first = build_candidate_benchmark_promotion_gate_report(CASES).to_dict()
    second = build_candidate_benchmark_promotion_gate_report(CASES).to_dict()
    after = CASES.read_text(encoding="utf-8")

    assert isinstance(build_candidate_benchmark_promotion_gate_report(CASES), CandidateBenchmarkPromotionGateReport)
    assert before == after
    assert first["summary"]["passed"] is True
    assert first["summary"]["promotion_status"] == "candidate_ready"
    assert first["summary"]["baseline_release_status"] == "preserved_reference_only"
    assert first["summary"]["source_case_count"] == 4
    assert first["summary"]["candidate_case_count"] == 4
    assert first["summary"]["improved_case_count"] >= 2
    assert first["summary"]["unsafe_action_count"] == 0
    assert first["source_baseline"]["fingerprint_sha256"] == second["source_baseline"]["fingerprint_sha256"]
    assert first["candidate_pack"]["fingerprint_sha256"] == second["candidate_pack"]["fingerprint_sha256"]
    assert len(first["source_baseline"]["fingerprint_sha256"]) == 64
    assert len(first["candidate_pack"]["fingerprint_sha256"]) == 64
    assert first["candidate_pack"]["version"] == "p55-candidate-v1"
    assert first["candidate_pack"]["source_reference"]["baseline_path"] == str(CASES)
    assert len(first["candidate_pack"]["cases"]) == 4
    assert first["gap_closure"]["evidence_gap"] == {"baseline": 1, "candidate": 0, "closed": True}
    assert first["gap_closure"]["recovery_verification_gap"] == {"baseline": 2, "candidate": 0, "closed": True}
    assert first["score_delta"]["evidence_quality_score"] > 0
    assert first["score_delta"]["recovery_verification_coverage"] > 0
    assert all(gate["passed"] is True for gate in first["promotion_gates"])
    assert first["boundary"]["candidate_benchmark_only"] is True
    assert first["boundary"]["production_mutation_enabled"] is False
    assert first["boundary"]["unattended_production_operation_claimed"] is False


def test_candidate_benchmark_promotion_gate_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p55.json"
    output_md = tmp_path / "p55.md"
    subprocess.run(
        [
            "python",
            "scripts/run_candidate_benchmark_promotion_gate.py",
            "--cases",
            str(CASES),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["passed"] is True
    assert payload["candidate_pack"]["version"] == "p55-candidate-v1"
    assert "# OpsCat Candidate Benchmark Promotion Gate" in markdown
    assert "Promotion gates" in markdown
    assert "Candidate pack" in markdown
    assert render_candidate_benchmark_promotion_gate_markdown(payload).startswith("# OpsCat Candidate Benchmark Promotion Gate")
