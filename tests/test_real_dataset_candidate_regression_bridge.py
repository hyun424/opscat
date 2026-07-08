from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.real_dataset_candidate_regression_bridge import (
    RealDatasetCandidateRegressionBridgeReport,
    build_real_dataset_candidate_regression_bridge_report,
    render_real_dataset_candidate_regression_bridge_markdown,
)

CASES = Path("evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")
MANIFEST = Path("evals/real_datasets/external/p44_benchmark_matrix_manifest.json")


def test_real_dataset_candidate_regression_bridge_requires_candidate_and_dataset_evidence() -> None:
    report = build_real_dataset_candidate_regression_bridge_report(CASES, MANIFEST, repeat_count=3)
    payload = report.to_dict()

    assert isinstance(report, RealDatasetCandidateRegressionBridgeReport)
    assert payload["summary"]["passed"] is True
    assert payload["summary"]["candidate_regression_passed"] is True
    assert payload["summary"]["dataset_matrix_passed"] is True
    assert payload["summary"]["dataset_mode"] == "fixture_fallback"
    assert payload["summary"]["dataset_source_count"] >= 5
    assert payload["summary"]["dataset_family_count"] >= 2
    assert payload["summary"]["parsed_record_count"] >= 10
    assert payload["summary"]["unsafe_action_count"] == 0
    assert payload["candidate_regression"]["repeat_count"] == 3
    assert payload["candidate_regression"]["stable_candidate_fingerprint"] is True
    assert payload["dataset_score"]["root_cause_accuracy"] >= 1.0
    assert payload["dataset_score"]["route_accuracy"] >= 1.0
    assert payload["dataset_weak_spots"]["worst_sources"] == []
    assert all(gate["passed"] is True for gate in payload["bridge_gates"])
    assert payload["boundary"]["real_dataset_bridge_only"] is True
    assert payload["boundary"]["live_api_calls_enabled"] is False


def test_real_dataset_candidate_regression_bridge_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p57.json"
    output_md = tmp_path / "p57.md"
    subprocess.run(
        [
            "python",
            "scripts/run_real_dataset_candidate_regression_bridge.py",
            "--cases",
            str(CASES),
            "--manifest",
            str(MANIFEST),
            "--repeat-count",
            "3",
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
    assert "# OpsCat Real Dataset Candidate Regression Bridge" in markdown
    assert "Bridge gates" in markdown
    assert "Dataset score" in markdown
    assert render_real_dataset_candidate_regression_bridge_markdown(payload).startswith("# OpsCat Real Dataset Candidate Regression Bridge")
