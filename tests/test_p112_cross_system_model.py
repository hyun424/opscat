from __future__ import annotations

import copy
import json

import pytest

from app.services.p112_cross_system_model import (
    P112ModelError,
    canonical_metric_family,
    score_cross_system_model,
    service_feature_vectors,
    train_cross_system_model,
)


def _packet(case: int, root: str, fault: str, *, rename: dict[str, str] | None = None) -> dict:
    rename = rename or {}
    services = ("alpha", "beta", "gamma")
    rows = []
    metrics = {
        "cpu": "container-cpu-usage-seconds-total",
        "mem": "container-memory-usage-bytes",
        "disk": "container-fs-reads-bytes-total",
        "delay": "istio-latency-95",
        "loss": "container-network-receive-packets-dropped-total",
    }
    for service in services:
        visible = rename.get(service, service)
        rows.append(
            {
                "evidence_id": f"ev-{case}-{visible}-latency",
                "service": visible,
                "metric": "istio-latency-50",
                "statistic": "robust_post_shift",
                "signed_score": 1.0,
            }
        )
        rows.append(
            {
                "evidence_id": f"ev-{case}-{visible}-fault",
                "service": visible,
                "metric": metrics[fault],
                "statistic": "robust_rate_shift",
                "signed_score": 20.0 if service == root else 0.5,
            }
        )
    return {
        "schema_version": "p112.re1_candidate_packet.v1",
        "case_id": f"opaque-{case}",
        "service_catalog": [rename.get(item, item) for item in services],
        "evidence": [],
        "diagnostic_evidence": rows,
    }


def _training() -> list[tuple[dict, dict]]:
    samples = []
    for index, fault in enumerate(("cpu", "mem", "disk", "delay", "loss"), start=1):
        root = ("alpha", "beta", "gamma")[(index - 1) % 3]
        samples.append((_packet(index, root, fault), {"root_service": root, "fault_type": fault}))
    return samples


def test_feature_schema_is_service_rename_invariant() -> None:
    original = service_feature_vectors(_packet(1, "alpha", "loss"))
    renamed = service_feature_vectors(
        _packet(1, "alpha", "loss", rename={"alpha": "one", "beta": "two", "gamma": "three"})
    )
    assert original["alpha"]["feature_names"] == renamed["one"]["feature_names"]
    assert original["alpha"]["vector"] == renamed["one"]["vector"]


def test_model_artifact_excludes_training_identities_and_scores_allowlist() -> None:
    artifact = train_cross_system_model(
        _training(),
        training_source_hash="sha256:" + "1" * 64,
        training_repetitions=(1, 2, 3),
    )
    rendered = json.dumps(artifact, sort_keys=True)
    assert "opaque-" not in rendered
    assert "alpha" not in rendered
    assert "beta" not in rendered
    assert "gamma" not in rendered
    scored = score_cross_system_model(_packet(9, "beta", "loss"), artifact)
    assert scored["ranked_services"][0] == "beta"
    assert scored["ranked_faults"][0] == "loss"


def test_model_rejects_tampering_and_invalid_training_split() -> None:
    artifact = train_cross_system_model(
        _training(),
        training_source_hash="sha256:" + "1" * 64,
        training_repetitions=(1, 2, 3),
    )
    tampered = copy.deepcopy(artifact)
    tampered["pair_weight"] = 2.0
    with pytest.raises(P112ModelError, match="tampered"):
        score_cross_system_model(_packet(9, "beta", "loss"), tampered)
    with pytest.raises(P112ModelError, match="invalid_training_repetitions"):
        train_cross_system_model(
            _training(),
            training_source_hash="sha256:" + "1" * 64,
            training_repetitions=(1, 2, 4),
        )


def test_canonical_metric_mapping_covers_loss_and_delay() -> None:
    assert canonical_metric_family("container-network-receive-packets-dropped-total") == "net_drop"
    assert canonical_metric_family("container-network-transmit-errors-total") == "net_error"
    assert canonical_metric_family("istio-latency-95") == "latency"
    assert canonical_metric_family("istio-error-total") == "error"
