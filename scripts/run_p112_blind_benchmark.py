#!/usr/bin/env python3
"""Run one frozen P112 paired blind batch in baseline or candidate mode."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_candidate_runner import NvidiaP110CandidateProvider  # noqa: E402
from app.services.p111_multistage_rca import P111_SYSTEM_PROMPT, run_p111_candidate_diagnostics  # noqa: E402
from app.services.p112_benchmark_runtime import (  # noqa: E402
    OB_HASH,
    SS_HASH,
    baseline_config,
    baseline_request,
    blind_cases,
    candidate_config,
    candidate_request,
    full_blind_packets,
    implementation_hash,
    to_p110_source_packet,
)
from app.services.p112_evaluation import evaluate_p112_predictions  # noqa: E402
from app.services.p112_freeze_guard import validate_p112_freeze  # noqa: E402
from app.services.p112_multistage_rca import SYSTEM_PROMPT, run_p112_candidate_diagnostics  # noqa: E402
from app.services.p112_re1_loader import load_pinned_re1_cases  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("baseline", "candidate"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--case-offset", type=int, required=True)
    parser.add_argument("--max-cases", type=int, default=5)
    parser.add_argument("--freeze-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    _load_env(args.env_file)

    key = (ROOT / "evals/real_datasets/external/p110/raw/.p110-case-id-key").read_bytes()
    ob = load_pinned_re1_cases(
        ROOT / "evals/real_datasets/external/p110/raw/RE1-OB.zip",
        ROOT / "evals/real_datasets/external/p112/source-manifest-re1-ob.json",
        hmac_key=key,
    )
    model = _read(args.freeze_dir / "p112-model.json")
    prior = _read(args.freeze_dir / "p111-baseline-prior.json")
    frozen = _read(args.freeze_dir / "freeze-manifest.json")
    baseline_packets, candidate_packets = full_blind_packets(ob, p112_model=model, p111_prior=prior)
    validate_p112_freeze(
        frozen,
        model_artifact_hash=str(model["artifact_hash"]),
        implementation_hash=implementation_hash(ROOT),
        training_source_hashes=(SS_HASH, OB_HASH),
        blind_source_hash=OB_HASH,
        baseline_packets=baseline_packets,
        candidate_packets=candidate_packets,
        baseline_request=baseline_request(),
        candidate_request=candidate_request(),
    )
    all_blind = blind_cases(ob)
    selected = all_blind[args.case_offset : args.case_offset + args.max_cases]
    source_packets = [case.to_candidate_packet() for case in selected]
    if args.arm == "baseline":
        config = baseline_config(max_cases=len(selected), max_calls=len(selected))
        provider = NvidiaP110CandidateProvider(system_prompt=P111_SYSTEM_PROMPT)
        report = run_p111_candidate_diagnostics(
            [to_p110_source_packet(packet) for packet in source_packets],
            mode="nvidia",
            provider=provider,
            config=config,
            fault_prior_artifact=prior,
        )
    else:
        config = candidate_config(max_cases=len(selected), max_calls=len(selected))
        provider = NvidiaP110CandidateProvider(system_prompt=SYSTEM_PROMPT)
        report = run_p112_candidate_diagnostics(
            source_packets,
            mode="nvidia",
            provider=provider,
            config=config,
            model_artifact=model,
        )
    report["benchmark_provenance"] = {
        "schema_version": "p112.blind_batch_provenance.v1",
        "arm": args.arm,
        "run_id": args.run_id,
        "benchmark_role": "blind",
        "repetition": 4,
        "case_offset": args.case_offset,
        "selected_case_count": len(selected),
        "selected_case_ids": [case.case_id for case in selected],
        "freeze_hash": frozen["freeze_hash"],
        "implementation_hash": implementation_hash(ROOT),
        "blind_source_hash": OB_HASH,
        "request": baseline_request() if args.arm == "baseline" else candidate_request(),
    }
    truth = [case.to_scorer_truth() for case in selected]
    evaluation = evaluate_p112_predictions(
        truth,
        report["predictions"],
        expected_source_hash=OB_HASH,
        allowed_root_services=("adservice", "cartservice", "checkoutservice", "currencyservice", "productcatalogservice"),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write(args.output_dir / "candidate-nvidia.json", report)
    _write(args.output_dir / "evaluation-nvidia.json", evaluation)
    print(json.dumps({"arm": args.arm, "run_id": args.run_id, "metrics": evaluation["metrics"], "safety": evaluation["safety"]}, sort_keys=True))
    return 0


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "NVIDIA_API_KEY" and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip("\"'")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
