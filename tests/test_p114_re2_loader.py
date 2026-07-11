from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

import app.services.p114_acquisition as p114_acquisition
from app.services.p114_acquisition import P114_SOURCE_PINS
from app.services.p114_re2_loader import P114RE2Case, P114RE2Error, load_pinned_re2_cases


def _pin_fixture(monkeypatch: pytest.MonkeyPatch, source_id: str, payload: bytes, *, case_count: int = 1) -> None:
    pins = dict(P114_SOURCE_PINS)
    pins[source_id] = replace(
        pins[source_id],
        compressed_bytes=len(payload),
        upstream_md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        verified_sha256=hashlib.sha256(payload).hexdigest(),
        expected_case_count=case_count,
    )
    monkeypatch.setattr(p114_acquisition, "P114_SOURCE_PINS", pins)


def _manifest(path: Path, payload: bytes, *, source_id: str = "rcaeval-re2-ss", system: str = "sock_shop") -> Path:
    pin = P114_SOURCE_PINS[source_id]
    target = path / f"source-manifest-{source_id}.json"
    target.write_text(
        json.dumps(
            {
                "schema_version": "p114.source_manifest.v1",
                "source_id": source_id,
                "system": system,
                "canonical_record": "https://zenodo.org/records/14590730",
                "canonical_download_url": pin.canonical_download_url,
                "file_name": pin.file_name,
                "compressed_bytes": len(payload),
                "expected_case_count": 1,
                "upstream_md5": hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                "verified_sha256": hashlib.sha256(payload).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return target


def _archive(
    tmp_path: Path,
    *,
    metric_value: str = "8",
    include_cluster_info: bool = True,
    include_logts: bool = True,
    traversal: bool = False,
    duplicate: bool = False,
    include_blank_metric_timestamp: bool = False,
) -> Path:
    archive = tmp_path / "RE2-SS.zip"
    root = "../escape" if traversal else "RE2-SS"
    prefix = f"{root}/payment_cpu/1"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(f"{prefix}/inject_time.txt", "10\n")
        zf.writestr(
            f"{prefix}/simple_metrics.csv",
            f"time,payment_cpu,orders_latency-90\n1,1,5\n2,1,5\n10,{metric_value},6\n11,9,7\n" + (",100,100\n" if include_blank_metric_timestamp else ""),
        )
        if include_logts:
            zf.writestr(f"{prefix}/logts.csv", "time,payment_1,orders_2\n1,1,5\n10,4,5\n11,6,5\n")
        if include_cluster_info:
            zf.writestr(
                f"{prefix}/cluster_info.json",
                json.dumps(
                    {
                        "1": {"template": "payment health took <:TIME:>", "container": ["payment"]},
                        "2": {"template": "orders stable", "container": ["orders"]},
                    }
                ),
            )
        zf.writestr(f"{prefix}/metrics.csv", "large file must not be read\n")
        zf.writestr(f"{prefix}/logs.csv", "large file must not be read\n")
        zf.writestr(f"{prefix}/traces.csv", "large file must not be read\n")
        zf.writestr(f"{prefix}/tracets_err.csv", "large file must not be read\n")
        zf.writestr(f"{prefix}/tracets_lat.csv", "large file must not be read\n")
        zf.writestr(f"{root}/.DS_Store", "upstream metadata\n")
        zf.writestr(f"{root}/payment_cpu/multi-source-data.zip", "upstream bundle\n")
        if duplicate:
            zf.writestr(f"{prefix}/inject_time.txt", "10\n")
    return archive


def _load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, archive: Path) -> tuple[P114RE2Case, ...]:
    payload = archive.read_bytes()
    _pin_fixture(monkeypatch, "rcaeval-re2-ss", payload)
    return load_pinned_re2_cases(archive, _manifest(tmp_path, payload), hmac_key=b"test-key")


def test_loader_builds_hidden_truth_case_and_label_free_candidate_packet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = _load(tmp_path, monkeypatch, _archive(tmp_path))

    assert len(cases) == 1
    case = cases[0]
    assert case.scorer_only_truth == {"root_service": "payment", "fault_type": "cpu", "repetition": 1}
    assert case.case_id.startswith("p114_")
    packet = case.to_candidate_packet()
    rendered = json.dumps(packet, sort_keys=True, allow_nan=False)
    assert packet["schema_version"] == "p114.re2_candidate_packet.v1"
    assert packet["evidence_graph"]["nodes"]
    assert all({"support", "contradiction", "missing"} <= set(node) for node in packet["evidence_graph"]["nodes"])
    assert "root_service" not in rendered
    assert "fault_type" not in rendered
    assert "repetition" not in rendered
    assert "source_path" not in rendered
    assert "payment_cpu/1" not in rendered
    assert "metrics.csv" not in rendered
    assert "logs.csv" not in rendered


def test_loader_evidence_ordering_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _archive(tmp_path)
    first = _load(tmp_path, monkeypatch, archive)[0].to_candidate_packet()
    second = _load(tmp_path, monkeypatch, archive)[0].to_candidate_packet()

    assert first == second
    node_ids = [node["node_id"] for node in first["evidence_graph"]["nodes"]]
    edge_ids = [edge["edge_id"] for edge in first["evidence_graph"]["edges"]]
    assert node_ids == sorted(node_ids)
    assert edge_ids == sorted(edge_ids)


def test_loader_drops_and_marks_nonfinite_metric_samples(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _archive(tmp_path, metric_value="NaN")
    case = _load(tmp_path, monkeypatch, archive)[0]

    node = next(node for node in case.nodes if node.modality == "metric" and node.signal == "cpu")
    assert "nonfinite_samples" in node.missing
    assert node.source["dropped_nonfinite_count"] == 1
    assert node.source["sample_count"] == 3


def test_loader_drops_unanchored_rows_and_records_missing_timestamp_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _archive(tmp_path, include_blank_metric_timestamp=True)
    case = _load(tmp_path, monkeypatch, archive)[0]

    metric_nodes = [node for node in case.nodes if node.modality == "metric"]
    assert metric_nodes
    assert all("missing_timestamp_rows" in node.missing for node in metric_nodes)
    assert all(node.source["dropped_timestamp_row_count"] == 1 for node in metric_nodes)


def test_loader_rejects_malformed_required_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _archive(tmp_path, include_cluster_info=False)
    with pytest.raises(P114RE2Error, match="missing_case_file"):
        _load(tmp_path, monkeypatch, archive)

    archive = _archive(tmp_path, include_logts=False)
    with pytest.raises(P114RE2Error, match="missing_case_file"):
        _load(tmp_path, monkeypatch, archive)


def test_loader_rejects_traversal_and_duplicate_through_acquisition_validator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _archive(tmp_path, traversal=True)
    with pytest.raises(P114RE2Error, match="archive_traversal"):
        _load(tmp_path, monkeypatch, archive)

    archive = _archive(tmp_path, duplicate=True)
    with pytest.raises(P114RE2Error, match="archive_duplicate_path"):
        _load(tmp_path, monkeypatch, archive)


def test_loader_requires_hmac_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _archive(tmp_path)
    payload = archive.read_bytes()
    _pin_fixture(monkeypatch, "rcaeval-re2-ss", payload)
    with pytest.raises(P114RE2Error, match="hmac_key_required"):
        load_pinned_re2_cases(archive, _manifest(tmp_path, payload), hmac_key=b"")


def test_real_re2_ss_smoke_if_archive_exists() -> None:
    archive = Path("evals/real_datasets/external/p114/raw/RE2-SS.zip")
    manifest = Path("evals/real_datasets/external/p114/source-manifest-re2-ss.json")
    if not archive.exists():
        pytest.skip("local RE2-SS archive is not present")

    cases = load_pinned_re2_cases(archive, manifest, hmac_key=b"test-key", max_cases=2)

    assert len(cases) == 2
    assert all(case.nodes for case in cases)
    assert all(case.to_candidate_packet()["evidence_graph"]["nodes"] for case in cases)
