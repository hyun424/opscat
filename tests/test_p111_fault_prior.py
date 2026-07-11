from __future__ import annotations

import copy
from typing import Any

import pytest

from app.services.p111_fault_prior import P111FaultPriorError, score_fault_priors, train_fault_prior, validate_fault_prior


def _digest(metric: str) -> dict[str, object]:
    entries = []
    for name in ("cpu", "mem", "load", "latency", "error"):
        entries.append(
            {
                "service": "svc",
                "metric": name,
                "relative_change": 10.0 if name == metric else 0.1,
                "magnitude_percentile": 1.0 if name == metric else 0.0,
            }
        )
    return {"entries": entries}


def _artifact() -> dict[str, Any]:
    mapping = {"cpu": "cpu", "mem": "mem", "disk": "load", "delay": "latency", "loss": "error"}
    samples = [(_digest(metric), {"root_service": "svc", "fault_type": fault}) for fault, metric in mapping.items()]
    return train_fault_prior(samples, training_repetitions=[1])


def test_fault_prior_is_deterministic_and_separates_signatures() -> None:
    artifact = _artifact()
    assert artifact == _artifact()
    scores = score_fault_priors(_digest("error"), ["svc"], artifact)
    assert scores["ranked_services"][0] == "svc"
    assert scores["ranked_faults"][0] == "loss"


def test_fault_prior_tamper_fails_closed() -> None:
    artifact = copy.deepcopy(_artifact())
    artifact["prototypes"][0]["vector"][0] = 999
    with pytest.raises(P111FaultPriorError, match="tampered"):
        validate_fault_prior(artifact)
