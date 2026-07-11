from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from app.services.p112_re1_loader import P112RE1Error, load_pinned_re1_cases


def _archive(tmp_path: Path, *, traversal: bool = False, nonfinite: bool = False) -> tuple[Path, Path]:
    archive = tmp_path / "RE1-SS.zip"
    prefix = "../escape" if traversal else "RE1-SS"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(f"{prefix}/carts_cpu/1/inject_time.txt", "2\n")
        metric_rows = "1,1,1\n2,1,2\n3,5,5\n4,5,8\n"
        if nonfinite:
            metric_rows += "5,NaN,NaN\n"
        zf.writestr(
            f"{prefix}/carts_cpu/1/data.csv",
            "time,carts_istio-latency-95,carts_container-cpu-usage-seconds-total\n" + metric_rows,
        )
        zf.writestr(f"{prefix}/carts_cpu/1/simple_data.csv", "ignored\n")
    data = archive.read_bytes()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "p112.source_manifest.v1",
                "system": "sock_shop",
                "file_name": archive.name,
                "compressed_bytes": len(data),
                "expected_case_count": 1,
                "upstream_md5": hashlib.md5(data, usedforsecurity=False).hexdigest(),
                "verified_sha256": hashlib.sha256(data).hexdigest(),
                "root_services": ["carts"],
                "fault_families": ["cpu", "mem", "disk", "delay", "loss"],
            }
        ),
        encoding="utf-8",
    )
    return archive, manifest


def test_loader_parses_manifest_services_and_hides_truth(tmp_path: Path) -> None:
    archive, manifest = _archive(tmp_path)
    cases = load_pinned_re1_cases(archive, manifest, hmac_key=b"test-key")

    assert len(cases) == 1
    assert cases[0].scorer_only_truth == {"root_service": "carts", "fault_type": "cpu", "repetition": 1}
    packet = cases[0].to_candidate_packet()
    rendered = json.dumps(packet, sort_keys=True)
    assert packet["system"] == "sock_shop"
    assert packet["diagnostic_evidence"]
    assert "root_service" not in rendered
    assert "fault_type" not in rendered
    assert "repetition" not in rendered
    assert "source_path" not in rendered


def test_loader_rejects_wrong_archive_hash(tmp_path: Path) -> None:
    archive, manifest = _archive(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["verified_sha256"] = "0" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_pinned_re1_cases(archive, manifest, hmac_key=b"test-key")


def test_loader_rejects_archive_traversal(tmp_path: Path) -> None:
    archive, manifest = _archive(tmp_path, traversal=True)
    with pytest.raises(P112RE1Error, match="archive_traversal"):
        load_pinned_re1_cases(archive, manifest, hmac_key=b"test-key")


def test_loader_requires_hmac_key(tmp_path: Path) -> None:
    archive, manifest = _archive(tmp_path)
    with pytest.raises(P112RE1Error, match="hmac_key_required"):
        load_pinned_re1_cases(archive, manifest, hmac_key=b"")


def test_loader_excludes_nonfinite_observations_before_canonical_hashing(tmp_path: Path) -> None:
    archive, manifest = _archive(tmp_path, nonfinite=True)

    packet = load_pinned_re1_cases(archive, manifest, hmac_key=b"test-key")[0].to_candidate_packet()

    rendered = json.dumps(packet, sort_keys=True, allow_nan=False)
    assert "NaN" not in rendered
