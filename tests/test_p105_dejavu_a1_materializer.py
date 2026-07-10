from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

DEJAVU_SCRIPT = Path("scripts/materialize_p105_dejavu_a1_reviewed_local.py")

EXPECTED_PARTITIONS = {
    "db_003": ("45b932965cd0dca686bd5f911f7c53086bad4033c5df3323207e99452c5c75ee", "held_out_test"),
    "db_007": ("f8455be6448f2535f998e962d2dd04e08dd4a6061c535eea14a6baea3582e804", "real_derived_shadow"),
}
EXPECTED_POSITIVE_WINDOWS = {
    "dejavu-a1-db-connection-limit-db_007-1586542500": 22,
    "dejavu-a1-db-connection-limit-db_003-1590165600": 3,
    "dejavu-a1-db-connection-limit-db_007-1590430140": 14,
    "dejavu-a1-db-connection-limit-db_003-1590515580": 17,
    "dejavu-a1-db-connection-limit-db_007-1590519180": 18,
    "dejavu-a1-db-connection-limit-db_003-1590689460": 7,
    "dejavu-a1-db-connection-limit-db_003-1590868020": 23,
}


def _require_dejavu_script() -> None:
    if not DEJAVU_SCRIPT.exists():
        pytest.fail("P105-025 RED: missing scripts/materialize_p105_dejavu_a1_reviewed_local.py.", pytrace=False)


def _write_a1_fixture(root: Path) -> tuple[Path, Path, Path]:
    root.mkdir(parents=True)
    metrics = root / "metrics.csv"
    faults = root / "faults.csv"
    graph = root / "graph.yml"
    with metrics.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "timestamp", "value", "metric_type"])
        writer.writeheader()
        for service in ("db_003", "db_007"):
            for timestamp in range(1590163200, 1590166801, 60):
                for metric in ("Proc_User_Used_Pct", "Proc_Used_Pct", "Sess_Connect"):
                    writer.writerow({"name": f"{service}##{metric}", "timestamp": timestamp, "value": "42.0", "metric_type": metric})
        writer.writerow({"name": "web_001##Sess_Connect", "timestamp": 1590163200, "value": "99", "metric_type": "Sess_Connect"})
    with faults.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "object", "fault_description", "kpi", "name", "node_type", "root_cause_node"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "timestamp": 1590165600,
                "object": "db",
                "fault_description": "db connection limit",
                "kpi": "Proc_User_Used_Pct;Proc_Used_Pct;Sess_Connect",
                "name": "db_003",
                "node_type": "DB Session",
                "root_cause_node": "db_003 Session",
            }
        )
        writer.writerow(
            {
                "timestamp": 1590165600,
                "object": "db",
                "fault_description": "DB Connection Limit",
                "kpi": "Proc_User_Used_Pct;Proc_Used_Pct;Sess_Connect",
                "name": "db_007",
                "node_type": "DB Session",
                "root_cause_node": "db_007 Session",
            }
        )
    graph.write_text(
        "\n".join(
            [
                "services:",
                "  db_003:",
                "    node_type: DB Session",
                "    metrics: [Proc_User_Used_Pct, Proc_Used_Pct, Sess_Connect]",
                "  db_007:",
                "    node_type: DB Session",
                "    metrics: [Proc_User_Used_Pct, Proc_Used_Pct, Sess_Connect]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return metrics, faults, graph


def _run_dejavu(tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
    _require_dejavu_script()
    metrics, faults, graph = _write_a1_fixture(tmp_path / "A1")
    output = tmp_path / "out"
    command = [
        sys.executable,
        str(DEJAVU_SCRIPT),
        "--metrics-csv",
        str(metrics),
        "--faults-csv",
        str(faults),
        "--graph-yml",
        str(graph),
        "--output-dir",
        str(output),
        "--window-seconds",
        "1800",
        "--stride-seconds",
        "300",
        "--forecast-horizon-seconds",
        "7200",
        "--minimum-complete-triple-samples",
        "24",
        "--continuity-gap-limit-seconds",
        "120",
        "--partition-salt",
        "dejavu-a1-service-split-v1",
        "--license-name",
        "CC-BY-4.0",
        "--license-url",
        "https://creativecommons.org/licenses/by/4.0/",
        "--created-at",
        "2024-03-09T16:00:00Z",
        "--review-status",
        "reviewed-local",
        "--expect-incident-groups",
        "held_out_test=4,real_derived_shadow=3",
        "--expect-source-hashes",
    ]
    return subprocess.run(command, text=True, capture_output=True, check=False), output


def test_dejavu_a1_materializer_keeps_public_features_private_labels_and_partitions_separate(tmp_path: Path) -> None:
    completed, output = _run_dejavu(tmp_path)

    assert completed.returncode == 0, completed.stderr
    public_rows = (output / "p105-dejavu-a1-public-windows.jsonl").read_text(encoding="utf-8")
    private_ledger = json.loads((output / "p105-dejavu-a1-private-label-ledger.json").read_text(encoding="utf-8"))
    partitions = json.loads((output / "p105-dejavu-a1-pre-label-partitions.json").read_text(encoding="utf-8"))
    assert "fault_description" not in public_rows
    assert "label_positive" not in public_rows
    assert private_ledger["label_join_phase"] == "after_sampling_and_partition"
    for service, (digest, partition) in EXPECTED_PARTITIONS.items():
        assert partitions["services"][service]["partition_hash"] == digest
        assert partitions["services"][service]["partition_id"] == partition


def test_dejavu_a1_exact_seven_incident_mapping_and_source_insufficiency_are_reported(tmp_path: Path) -> None:
    completed, output = _run_dejavu(tmp_path)

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((output / "p105-dejavu-a1-reviewed-local-manifest.json").read_text(encoding="utf-8"))
    assert manifest["incident_positive_window_counts"] == EXPECTED_POSITIVE_WINDOWS
    assert manifest["incident_group_counts"] == {"held_out_test": 4, "real_derived_shadow": 3}
    assert manifest["coverage_seconds"] == {"held_out_test": 151320, "real_derived_shadow": 147780}
    assert manifest["source_insufficiency"]["family"] == "database"
    assert manifest["source_insufficiency"]["held_out_service_seconds_deficit"] == 21480
    assert manifest["release_gate"] == {"release_qualified": False, "p106_unlocked": False}


def test_dejavu_a1_license_provenance_and_actual_coverage_are_hash_bound(tmp_path: Path) -> None:
    completed, output = _run_dejavu(tmp_path)

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads((output / "p105-dejavu-a1-reviewed-local-manifest.json").read_text(encoding="utf-8"))
    assert manifest["license"] == {
        "name": "CC-BY-4.0",
        "url": "https://creativecommons.org/licenses/by/4.0/",
        "citation_text": "DejaVu A1 local dataset snapshot: metrics.csv, faults.csv, graph.yml",
        "redistribution_status": "derived-redacted-only",
    }
    assert manifest["command_argv"]
    assert manifest["command_argv_sha256"]
    assert manifest["created_at"] == "2024-03-09T16:00:00Z"
    assert manifest["coverage"]["method"] == "actual_evaluable_timestamp_interval_union"
    assert manifest["coverage"]["rejects"] == ["fixed_four_day_constant", "row_count_duration", "floor_sized_interval", "timestamp_padding"]
