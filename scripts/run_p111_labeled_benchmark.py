#!/usr/bin/env python3
"""Run one governed P111 RCAEval benchmark slice."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_acquisition import validate_local_archive  # noqa: E402
from app.services.p110_candidate_runner import NvidiaP110CandidateProvider, P110RunnerConfig, build_p110_candidate_packet  # noqa: E402
from app.services.p110_evaluation import evaluate_p110_predictions, stable_hash  # noqa: E402
from app.services.p110_rcaeval import load_re1_ob_cases  # noqa: E402
from app.services.p111_benchmark_guard import benchmark_role, validate_frozen_run  # noqa: E402
from app.services.p111_fault_prior import train_fault_prior  # noqa: E402
from app.services.p111_multistage_rca import (  # noqa: E402
    P111_PROMPT_SCHEMA_VERSION,
    P111_SYSTEM_PROMPT,
    build_evidence_digest,
    build_p111_packet,
    run_p111_candidate_diagnostics,
)

DEFAULT_ROOT = ROOT / "evals/real_datasets/external/p110"
DEFAULT_DECODING = {
    "temperature": 1.0,
    "top_p": 0.95,
    "max_tokens": 16384,
    "reasoning_budget": 16384,
    "enable_thinking": True,
    "provider_endpoint": "https://integrate.api.nvidia.com/v1",
    "provider_api": "openai-chat-completions-v1",
    "stream": True,
    "system_prompt_sha256": hashlib.sha256(P111_SYSTEM_PROMPT.encode()).hexdigest(),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ROOT / "raw/RE1-OB.zip")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_ROOT / "source-manifest.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("mock", "nvidia"), default="mock")
    parser.add_argument("--repetition", type=int, choices=range(1, 6), required=True)
    parser.add_argument("--case-offset", type=int, default=0)
    parser.add_argument("--max-cases", type=int, default=25)
    parser.add_argument("--max-calls", type=int, default=25)
    parser.add_argument("--model")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--freeze-manifest", type=Path)
    args = parser.parse_args()

    source = validate_local_archive(args.archive, args.manifest)
    key = (args.archive.parent / ".p110-case-id-key").read_bytes()
    cases = load_re1_ob_cases(args.archive, hmac_key=key)
    role_cases = [case for case in cases if int(case.scorer_only_truth["repetition"]) == args.repetition]
    selected = role_cases[args.case_offset : args.case_offset + args.max_cases]
    packets = [case.to_candidate_packet() for case in selected]
    truth = [case.to_scorer_truth() for case in selected]
    role = benchmark_role(args.repetition)
    training_repetitions = tuple(range(1, args.repetition)) if role in {"validation", "blind"} else ()
    fault_prior = _train_prior(cases, training_repetitions) if training_repetitions else None
    p111_packets = [
        build_p111_packet(build_p110_candidate_packet(packet), fault_prior_artifact=fault_prior) for packet in packets
    ]

    _load_allowed_env(args.env_file)
    model = args.model or os.getenv("OPSCAT_NVIDIA_MODEL") or "nvidia/nemotron-3-ultra-550b-a55b"
    decoding = DEFAULT_DECODING if args.mode == "nvidia" else {"temperature": 0.0, "top_p": 1.0, "max_tokens": 2048}
    config = P110RunnerConfig(
        model=model if args.mode == "nvidia" else "mock/p111-deterministic",
        prompt_schema_version=P111_PROMPT_SCHEMA_VERSION,
        decoding_config=decoding,
        max_cases=args.max_cases,
        max_calls=args.max_calls,
    )
    implementation_hash = _implementation_hash()
    if role == "blind":
        if args.freeze_manifest is None:
            raise SystemExit("blind P111 run requires --freeze-manifest")
        frozen = json.loads(args.freeze_manifest.read_text(encoding="utf-8"))
        validate_frozen_run(
            frozen,
            target_repetition=args.repetition,
            model=config.model,
            prompt_schema_version=config.prompt_schema_version,
            decoding_config=config.decoding_config,
            implementation_hash=implementation_hash,
            official_source_hash=f"sha256:{source['sha256']}",
            candidate_packets=[
                build_p111_packet(build_p110_candidate_packet(case.to_candidate_packet()), fault_prior_artifact=fault_prior)
                for case in role_cases
            ],
        )
    elif role == "reserve":
        raise SystemExit("reserve repetition is protected")

    provider = NvidiaP110CandidateProvider(
        model=model,
        system_prompt=P111_SYSTEM_PROMPT,
    ) if args.mode == "nvidia" else _mock_provider()
    report = run_p111_candidate_diagnostics(
        packets, mode=args.mode, provider=provider, config=config, fault_prior_artifact=fault_prior
    )
    report["benchmark_provenance"] = {
        "official_source": f"sha256:{source['sha256']}",
        "benchmark_role": role,
        "repetition": args.repetition,
        "case_offset": args.case_offset,
        "selected_case_count": len(selected),
        "selected_case_ids": sorted(case.case_id for case in selected),
        "candidate_packets_hash": stable_hash({str(packet["case_id"]): packet for packet in p111_packets}),
        "scorer_truth_hash": stable_hash({str(case["case_id"]): case for case in truth}),
        "implementation_hash": implementation_hash,
        "fault_prior_artifact_hash": fault_prior.get("artifact_hash") if fault_prior else None,
        "training_repetitions": list(training_repetitions),
        "model": config.model,
        "prompt_schema_version": config.prompt_schema_version,
        "decoding_config": dict(config.decoding_config),
    }
    evaluation = evaluate_p110_predictions(truth, report["predictions"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write(args.output_dir / f"candidate-{args.mode}.json", report)
    _write(args.output_dir / f"evaluation-{args.mode}.json", evaluation)
    if fault_prior is not None:
        _write(args.output_dir / "fault-prior.json", fault_prior)
    print(json.dumps({"role": role, "metrics": evaluation["metrics"], "safety": evaluation["safety"], "output_dir": str(args.output_dir)}, sort_keys=True))
    return 0


def _mock_provider() -> Any:
    from app.services.p110_candidate_runner import MockP110CandidateProvider

    return MockP110CandidateProvider()


def _load_allowed_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"NVIDIA_API_KEY", "OPSCAT_NVIDIA_MODEL"} and key not in os.environ:
            os.environ[key] = value.strip().strip("\"'")


def _implementation_hash() -> str:
    paths = (
        ROOT / "app/services/p110_candidate_runner.py",
        ROOT / "app/services/p111_multistage_rca.py",
        ROOT / "app/services/p111_benchmark_guard.py",
        ROOT / "app/services/p111_fault_prior.py",
        ROOT / "app/services/p111_comparison.py",
        ROOT / "app/services/p111_release_evidence.py",
        ROOT / "app/services/p110_evaluation.py",
        ROOT / "scripts/run_p111_labeled_benchmark.py",
        ROOT / "scripts/freeze_p111_configuration.py",
        ROOT / "scripts/merge_p111_labeled_batches.py",
        ROOT / "scripts/merge_p111_baseline_batches.py",
        ROOT / "scripts/build_p111_release_evidence.py",
    )
    return stable_hash({path.name: _sha256(path) for path in paths})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _train_prior(cases: list[Any] | tuple[Any, ...], repetitions: tuple[int, ...]) -> dict[str, Any]:
    samples = []
    for case in cases:
        if int(case.scorer_only_truth["repetition"]) not in repetitions:
            continue
        packet = build_p110_candidate_packet(case.to_candidate_packet())
        samples.append((build_evidence_digest(packet), case.scorer_only_truth))
    return train_fault_prior(samples, training_repetitions=repetitions)


if __name__ == "__main__":
    raise SystemExit(main())
