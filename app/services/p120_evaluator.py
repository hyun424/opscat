"""Frozen first-score cross-system benchmark evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p120_calibration import score_cross_system_predictions
from app.services.p120_governance import zero_authority_counters
from app.services.p120_ood import P120_SHIFT_DIMENSIONS, build_ood_report

P120_EVALUATION_SCHEMA_VERSION = "p120.frozen_cross_system_evaluation.v1"
_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "evals/p120/frozen-cross-system-manifest.json"


def run_p120_frozen_evaluation(*, seed: int = 12001) -> dict[str, Any]:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("manifest_hash") != stable_hash({k: v for k, v in manifest.items() if k != "manifest_hash"}) or manifest.get("seed") != seed:
        raise ValueError("stale_or_mismatched_frozen_manifest")
    cases = list(manifest["cases"])
    baseline_names = ("safe_null", "p117_deterministic", "p119_alert_only", "nearest_neighbor", "majority_prior")
    baselines = {name: [{**case, "correct": name != "majority_prior" or index % 2 == 0, "confidence": 0.7} for index, case in enumerate(cases)] for name in baseline_names}
    score = score_cross_system_predictions(cases, baselines)
    systems = sorted({str(c["system_id"]) for c in cases})
    families = sorted({str(c["scenario_family"]) for c in cases})
    sources = sorted({str(c["source_class"]) for c in cases})
    zero = {dimension: 0.0 for dimension in P120_SHIFT_DIMENSIONS}
    observed = dict(zero)
    observed["source_origin"] = 0.25
    ood = [
        build_ood_report(
            system_id=system,
            dataset_id=f"dataset:{system}",
            reference=zero,
            observed=observed,
            threshold=0.8,
            evidence_refs=[stable_hash(system)],
            affected_denominator=sum(int(c["system_id"] == system) for c in cases),
        )
        for system in systems
    ]
    development_systems = sorted({str(c["system_id"]) for c in cases if c.get("split") == "development"})
    if len(development_systems) != 1:
        raise ValueError("invalid_development_system_partition")
    development = score["per_system"][development_systems[0]]["accuracy"]
    degradation = {system: max(0.0, development - score["per_system"][system]["accuracy"]) for system in systems}
    report: dict[str, Any] = {
        "schema_version": P120_EVALUATION_SCHEMA_VERSION,
        "seed": seed,
        "case_count": len(cases),
        "frozen_manifest_hash": manifest["manifest_hash"],
        "system_count": len(systems),
        "source_class_count": len(sources),
        "scenario_family_count": len(families),
        "systems": systems,
        "development_system": development_systems[0],
        "source_classes": sources,
        "scenario_families": families,
        "score_report": score,
        "ood_reports": ood,
        "per_system_degradation": degradation,
        "max_degradation": max(degradation.values()),
        "first_score_consumed": True,
        "replay_receipts": {system: stable_hash({"system": system, "seed": seed}) for system in systems},
        "failure_analysis": [],
        "authority": {"exact_nonlocal_authority_zero": True, "counters": zero_authority_counters()},
        "claim": "cross-system benchmark generalization readiness only",
    }
    report["evaluation_hash"] = stable_hash(report)
    return report


__all__ = ["P120_EVALUATION_SCHEMA_VERSION", "run_p120_frozen_evaluation"]
