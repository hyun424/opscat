from __future__ import annotations

import hashlib
import hmac
import json
import zipfile
from pathlib import Path

import pytest

from app.services.p110_rcaeval import (
    OFFICIAL_RE1_OB_MD5,
    OFFICIAL_RE1_OB_SHA256,
    OFFICIAL_RE1_OB_SIZE_BYTES,
    P110RCAEvalError,
    build_candidate_packets,
    load_re1_ob_cases,
    validate_official_archive,
)

HMAC_KEY = b"p110-test-key"


def _write_case(root: Path, service: str, fault: str, repetition: int, *, inject_time: int = 100) -> None:
    case_dir = root / f"{service}_{fault}" / str(repetition)
    case_dir.mkdir(parents=True)
    (case_dir / "inject_time").write_text(f"{inject_time}\n", encoding="utf-8")
    (case_dir / "data.csv").write_text(
        "\n".join(
            [
                "time,frontend_latency,checkoutservice_latency,cartservice_cpu",
                f"{inject_time - 10},100,50,0.4",
                f"{inject_time - 5},120,55,0.5",
                f"{inject_time + 5},260,90,0.7",
                f"{inject_time + 10},300,110,0.9",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_125_case_tree(root: Path) -> None:
    services = ("adservice", "cartservice", "checkoutservice", "frontend", "paymentservice")
    faults = ("cpu", "mem", "disk", "delay", "loss")
    for service in services:
        for fault in faults:
            for repetition in range(1, 6):
                _write_case(root, service, fault, repetition)


def _zip_tree(root: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(root).as_posix())


def test_official_source_constants_are_pinned() -> None:
    assert OFFICIAL_RE1_OB_SIZE_BYTES == 30966778
    assert OFFICIAL_RE1_OB_MD5 == "47cce26ed24140e8974e68f9db2a5e9c"
    assert OFFICIAL_RE1_OB_SHA256 == "4a709297e0a829f0f2ee8a7792a6d74da32d663c600565b7fffc860963b840c4"


def test_validate_official_archive_rejects_checksum_mismatch_before_open(tmp_path: Path) -> None:
    archive = tmp_path / "RE1-OB.zip"
    archive.write_bytes(b"not the official zip")

    with pytest.raises(P110RCAEvalError, match="archive_size_mismatch"):
        validate_official_archive(archive)


def test_loads_125_official_shape_cases_from_extracted_directory_with_truth_separation(tmp_path: Path) -> None:
    _write_125_case_tree(tmp_path)

    cases = load_re1_ob_cases(tmp_path, hmac_key=HMAC_KEY)

    assert len(cases) == 125
    first = cases[0]
    assert first.source_path == "adservice_cpu/1"
    assert first.scorer_only_truth == {"root_service": "adservice", "fault_type": "cpu", "repetition": 1}
    scorer_truth = first.to_scorer_truth()
    assert scorer_truth["schema_version"] == "p110.rcaeval_scorer_truth.v1"
    assert scorer_truth["official_source_hash"] == "sha256:4a709297e0a829f0f2ee8a7792a6d74da32d663c600565b7fffc860963b840c4"
    assert scorer_truth["evidence_ids"] == [feature.evidence_id for feature in first.features]
    assert set(first.raw_hashes) == {"data.csv", "inject_time"}
    assert first.inject_time == "100"
    assert first.case_id == _expected_case_id("adservice_cpu/1")

    packet = first.to_candidate_packet()
    rendered = json.dumps(packet, sort_keys=True)
    assert packet["schema_version"] == "p110.rcaeval_candidate_packet.v1"
    assert packet["case_id"] == first.case_id
    assert "adservice_cpu" not in rendered
    assert "root_service" not in rendered
    assert "fault_type" not in rendered
    assert first.raw_hashes["inject_time"] not in rendered
    assert first.raw_hashes["data.csv"] in rendered
    assert all(evidence["evidence_id"].startswith("ev_") for evidence in packet["evidence"])
    assert {evidence["window"] for evidence in packet["evidence"]} == {"pre", "post", "delta"}


def test_loads_same_cases_from_zip_after_safe_archive_scan(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_125_case_tree(source)
    archive = tmp_path / "RE1-OB.zip"
    _zip_tree(source, archive)

    cases = load_re1_ob_cases(archive, hmac_key=HMAC_KEY, strict_archive=False)

    assert len(cases) == 125
    assert cases[0].raw_hashes["data.csv"] == hashlib.sha256((source / "adservice_cpu" / "1" / "data.csv").read_bytes()).hexdigest()
    assert cases[0].features


@pytest.mark.parametrize(
    ("name", "payload", "error"),
    [
        ("../escape", b"x", "archive_traversal"),
        ("/absolute", b"x", "archive_traversal"),
    ],
)
def test_zip_rejects_traversal_members(tmp_path: Path, name: str, payload: bytes, error: str) -> None:
    archive = tmp_path / "RE1-OB.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(name, payload)

    with pytest.raises(P110RCAEvalError, match=error):
        load_re1_ob_cases(archive, hmac_key=HMAC_KEY, strict_archive=False)


def test_zip_rejects_symlink_members(tmp_path: Path) -> None:
    archive = tmp_path / "RE1-OB.zip"
    info = zipfile.ZipInfo("adservice_cpu/1/data.csv")
    info.create_system = 3
    info.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(info, "target")

    with pytest.raises(P110RCAEvalError, match="archive_symlink"):
        load_re1_ob_cases(archive, hmac_key=HMAC_KEY, strict_archive=False)


def test_zip_rejects_duplicate_paths(tmp_path: Path) -> None:
    archive = tmp_path / "RE1-OB.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("adservice_cpu/1/data.csv", "time,svc_metric\n1,2\n")
        zf.writestr("adservice_cpu/1/data.csv", "time,svc_metric\n1,3\n")

    with pytest.raises(P110RCAEvalError, match="archive_duplicate_path"):
        load_re1_ob_cases(archive, hmac_key=HMAC_KEY, strict_archive=False)


def test_rejects_duplicate_case_identity_from_wrapped_archive(tmp_path: Path) -> None:
    archive = tmp_path / "RE1-OB.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("one/adservice_cpu/1/data.csv", "time,svc_metric\n90,1\n110,2\n")
        zf.writestr("one/adservice_cpu/1/inject_time", "100\n")
        zf.writestr("two/adservice_cpu/1/data.csv", "time,svc_metric\n90,3\n110,4\n")
        zf.writestr("two/adservice_cpu/1/inject_time", "100\n")

    with pytest.raises(P110RCAEvalError, match="duplicate_case_identity"):
        load_re1_ob_cases(archive, hmac_key=HMAC_KEY, strict_archive=False, expected_case_count=1)


def test_accepts_inject_time_txt_alias_but_preserves_canonical_hash_key(tmp_path: Path) -> None:
    case_dir = tmp_path / "adservice_cpu" / "1"
    case_dir.mkdir(parents=True)
    (case_dir / "inject_time.txt").write_text("100\n", encoding="utf-8")
    (case_dir / "data.csv").write_text("time,svc_metric\n90,1\n110,2\n", encoding="utf-8")

    case = load_re1_ob_cases(tmp_path, hmac_key=HMAC_KEY, expected_case_count=1)[0]

    assert set(case.raw_hashes) == {"data.csv", "inject_time"}


def test_rejects_invalid_case_identity_and_missing_125_cases(tmp_path: Path) -> None:
    _write_case(tmp_path, "unknown", "cpu", 1)
    with pytest.raises(P110RCAEvalError, match="unknown_service"):
        load_re1_ob_cases(tmp_path, hmac_key=HMAC_KEY, expected_case_count=1)

    valid_root = tmp_path / "valid"
    _write_case(valid_root, "adservice", "cpu", 1)
    with pytest.raises(P110RCAEvalError, match="case_count_mismatch"):
        load_re1_ob_cases(valid_root, hmac_key=HMAC_KEY)


def test_rejects_symlink_in_extracted_directory(tmp_path: Path) -> None:
    case_dir = tmp_path / "adservice_cpu" / "1"
    case_dir.mkdir(parents=True)
    (case_dir / "inject_time").write_text("100\n", encoding="utf-8")
    (case_dir / "target.csv").write_text("time,svc_metric\n1,2\n", encoding="utf-8")
    (case_dir / "data.csv").symlink_to(case_dir / "target.csv")

    with pytest.raises(P110RCAEvalError, match="extracted_symlink"):
        load_re1_ob_cases(tmp_path, hmac_key=HMAC_KEY, expected_case_count=1)


def test_candidate_packet_collection_is_label_free_and_stable(tmp_path: Path) -> None:
    _write_case(tmp_path, "frontend", "delay", 3)
    cases = load_re1_ob_cases(tmp_path, hmac_key=HMAC_KEY, expected_case_count=1)

    first = build_candidate_packets(cases)
    second = build_candidate_packets(load_re1_ob_cases(tmp_path, hmac_key=HMAC_KEY, expected_case_count=1))

    assert first == second
    content = json.dumps(first, sort_keys=True)
    assert first[0]["injection_timestamp"] == "100"
    forbidden = ("frontend_delay", "root_service", "fault_type", "delay", "repetition", "truth", "scorer", "data.csv", "'inject_time'")
    assert all(token not in content for token in forbidden)
    assert first[0]["service_catalog"] == ["cartservice", "checkoutservice", "frontend"]
    assert first[0]["metric_catalog"] == ["cpu", "latency"]


def test_evidence_ids_bind_metric_service_window_statistic_and_source_hash(tmp_path: Path) -> None:
    _write_case(tmp_path, "checkoutservice", "loss", 2)

    case = load_re1_ob_cases(tmp_path, hmac_key=HMAC_KEY, expected_case_count=1)[0]
    packet = case.to_candidate_packet()
    evidence = packet["evidence"]
    ids = [row["evidence_id"] for row in evidence]

    assert len(ids) == len(set(ids))
    checkout_post = next(row for row in evidence if row["service"] == "checkoutservice" and row["window"] == "post")
    assert checkout_post["statistic"] == "mean"
    assert checkout_post["source_binding"] == {"raw_sha256": case.raw_hashes["data.csv"], "raw_path_token": "metric_source"}

    mutated = tmp_path / "checkoutservice_loss" / "2" / "data.csv"
    mutated.write_text(mutated.read_text(encoding="utf-8").replace("90", "91"), encoding="utf-8")
    changed = load_re1_ob_cases(tmp_path, hmac_key=HMAC_KEY, expected_case_count=1)[0].to_candidate_packet()["evidence"]
    assert {row["evidence_id"] for row in changed} != set(ids)


def test_rejects_non_metric_truth_leak_columns(tmp_path: Path) -> None:
    case_dir = tmp_path / "adservice_cpu" / "1"
    case_dir.mkdir(parents=True)
    (case_dir / "inject_time").write_text("100\n", encoding="utf-8")
    (case_dir / "data.csv").write_text("time,root_service\n90,adservice\n110,adservice\n", encoding="utf-8")

    with pytest.raises(P110RCAEvalError, match="candidate_visible_truth_leak"):
        load_re1_ob_cases(tmp_path, hmac_key=HMAC_KEY, expected_case_count=1)


def test_rejects_zip_ceiling_overruns(tmp_path: Path) -> None:
    archive = tmp_path / "RE1-OB.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("adservice_cpu/1/data.csv", "time,svc_metric\n1,2\n")
        zf.writestr("adservice_cpu/1/inject_time", "1\n")

    with pytest.raises(P110RCAEvalError, match="archive_file_count_exceeded"):
        load_re1_ob_cases(archive, hmac_key=HMAC_KEY, strict_archive=False, max_archive_files=1)
    with pytest.raises(P110RCAEvalError, match="archive_uncompressed_size_exceeded"):
        load_re1_ob_cases(archive, hmac_key=HMAC_KEY, strict_archive=False, max_archive_uncompressed_bytes=1)


def _expected_case_id(source_path: str) -> str:
    digest = hmac.new(HMAC_KEY, f"p110.rcaeval.case-id.v1:{source_path}".encode(), hashlib.sha256).hexdigest()
    return f"p110_{digest[:24]}"
