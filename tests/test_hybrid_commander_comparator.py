from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.hybrid_commander_comparator import (
    HybridCommanderComparatorReport,
    build_hybrid_commander_comparator_report,
    render_hybrid_commander_comparator_markdown,
)

CASES = Path("evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")
MANIFEST = Path("evals/real_datasets/external/p44_benchmark_matrix_manifest.json")
JUDGMENT_CASES = Path("evals/judgment/seed/cases.json")


def test_hybrid_commander_comparator_selects_guarded_hybrid_without_safety_regression() -> None:
    report = build_hybrid_commander_comparator_report(CASES, MANIFEST, JUDGMENT_CASES, max_cases=4)
    payload = report.to_dict()

    assert isinstance(report, HybridCommanderComparatorReport)
    assert payload["summary"]["passed"] is True
    assert payload["summary"]["harness_passed"] is True
    assert payload["summary"]["recommended_lane"] == "hybrid_guarded"
    assert payload["summary"]["lane_count"] == 3
    assert payload["summary"]["safety_regression_count"] == 0
    assert payload["summary"]["action_execution_count"] == 0
    assert {lane["lane_id"] for lane in payload["lanes"]} == {"deterministic_candidate", "llm_mock", "hybrid_guarded"}
    lanes = {lane["lane_id"]: lane for lane in payload["lanes"]}
    assert lanes["deterministic_candidate"]["passed"] is True
    assert lanes["llm_mock"]["passed"] is True
    assert lanes["hybrid_guarded"]["passed"] is True
    assert lanes["hybrid_guarded"]["score"] >= lanes["llm_mock"]["score"]
    assert lanes["hybrid_guarded"]["score"] >= 0.95
    assert lanes["hybrid_guarded"]["action_execution_enabled"] is False
    assert all(gate["passed"] is True for gate in payload["comparator_gates"])
    assert payload["boundary"]["hybrid_comparator_only"] is True
    assert payload["boundary"]["default_external_model_calls"] is False


def test_hybrid_commander_comparator_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p59.json"
    output_md = tmp_path / "p59.md"
    subprocess.run(
        [
            "python",
            "scripts/run_hybrid_commander_comparator.py",
            "--cases",
            str(CASES),
            "--manifest",
            str(MANIFEST),
            "--judgment-cases",
            str(JUDGMENT_CASES),
            "--max-cases",
            "4",
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
    assert "# OpsCat Hybrid Commander Comparator" in markdown
    assert "Comparator gates" in markdown
    assert "Lanes" in markdown
    assert render_hybrid_commander_comparator_markdown(payload).startswith("# OpsCat Hybrid Commander Comparator")
