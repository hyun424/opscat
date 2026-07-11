#!/usr/bin/env python3
"""Run the P110 labeled RCAEval holdout benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_acquisition import validate_local_archive  # noqa: E402
from app.services.p110_candidate_runner import (  # noqa: E402
    NvidiaP110CandidateProvider,
    P110RunnerConfig,
    build_p110_candidate_packet,
    run_p110_candidate_diagnostics,
)
from app.services.p110_evaluation import evaluate_p110_predictions, stable_hash  # noqa: E402
from app.services.p110_rcaeval import load_re1_ob_cases  # noqa: E402
from app.services.p110_release_evidence import produce_p110_release_evidence  # noqa: E402

DEFAULT_ARCHIVE = ROOT / "evals/real_datasets/external/p110/raw/RE1-OB.zip"
DEFAULT_MANIFEST = ROOT / "evals/real_datasets/external/p110/source-manifest.json"
DEFAULT_OUTPUT = ROOT / "evals/real_datasets/external/p110/results"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mode", choices=("mock", "replay", "nvidia"), default="mock")
    parser.add_argument("--repetition", type=int, default=5, choices=range(1, 6))
    parser.add_argument("--case-offset", type=int, default=0)
    parser.add_argument("--max-cases", type=int, default=25)
    parser.add_argument("--max-calls", type=int, default=25)
    parser.add_argument("--model")
    parser.add_argument("--replay-json", type=Path)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()

    if args.max_cases <= 0 or args.max_calls < 0:
        raise SystemExit("max-cases must be positive and max-calls non-negative")
    source = validate_local_archive(args.archive, args.manifest)
    case_key = _load_or_create_case_key(args.archive.parent / ".p110-case-id-key")
    cases = load_re1_ob_cases(args.archive, hmac_key=case_key)
    holdout = [case for case in cases if int(case.scorer_only_truth["repetition"]) == args.repetition]
    selected = holdout[args.case_offset : args.case_offset + args.max_cases]
    packets = [case.to_candidate_packet() for case in selected]
    truth_cases = [case.to_scorer_truth() for case in selected]

    replay_outputs: dict[str, Any] | None = None
    if args.replay_json:
        replay_value = json.loads(args.replay_json.read_text(encoding="utf-8"))
        replay_outputs = _replay_mapping(replay_value)

    provider = None
    model = args.model or "mock/p110-deterministic"
    if args.mode == "nvidia":
        _load_allowed_env(args.env_file)
        model = args.model or os.getenv("OPSCAT_NVIDIA_MODEL") or "nvidia/nemotron-3-ultra-550b-a55b"
        provider = NvidiaP110CandidateProvider(model=model)
    decoding = (
        {"temperature": 1.0, "top_p": 0.95, "max_tokens": 16384, "reasoning_budget": 16384, "enable_thinking": True}
        if args.mode == "nvidia"
        else {"temperature": 0.0, "top_p": 1.0, "max_tokens": 2048}
    )
    config = P110RunnerConfig(model=model, max_cases=args.max_cases, max_calls=args.max_calls, decoding_config=decoding)
    candidate_report = run_p110_candidate_diagnostics(
        packets,
        mode=args.mode,
        provider=provider,
        replay_outputs=replay_outputs,
        config=config,
    )
    candidate_report["benchmark_provenance"] = {
        "official_source": f"sha256:{source['sha256']}",
        "repetition": args.repetition,
        "case_offset": args.case_offset,
        "selected_case_count": len(selected),
        "selected_case_ids": sorted(case.case_id for case in selected),
        "candidate_packets_hash": stable_hash({str(packet["case_id"]): build_p110_candidate_packet(packet) for packet in packets}),
        "scorer_truth_hash": stable_hash({str(case["case_id"]): case for case in truth_cases}),
        "model": model,
        "prompt_schema_version": config.prompt_schema_version,
        "decoding_config": dict(config.decoding_config),
    }
    evaluation = evaluate_p110_predictions(truth_cases, candidate_report["predictions"])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = args.output_dir / "candidate-packets.json"
    candidate_path = args.output_dir / f"candidate-{args.mode}.json"
    evaluation_path = args.output_dir / f"evaluation-{args.mode}.json"
    _write_json(packet_path, packets)
    _write_json(candidate_path, candidate_report)
    _write_json(evaluation_path, evaluation)

    artifacts = {
        "official_source": f"sha256:{source['sha256']}",
        "labeled_cases": stable_hash(truth_cases),
        "scorer_truth": evaluation["scorer_truth_hash"],
        "candidate_outputs": f"sha256:{_sha256_file(candidate_path)}",
        "evaluation_report": evaluation["evaluation_hash"],
        "implementation_revision": _implementation_hash(),
    }
    release = produce_p110_release_evidence(
        producer_id="opscat-p110-cli",
        evaluation_report=evaluation,
        official_source_hash_verified=True,
        bound_artifact_hashes=artifacts,
        independent_review=None,
    )
    release_path = args.output_dir / f"release-{args.mode}.json"
    _write_json(release_path, release)
    _write_summary(args.output_dir / f"summary-{args.mode}.md", evaluation, candidate_report, release)

    print(
        json.dumps(
            {
                "mode": args.mode,
                "case_count": len(selected),
                "model": model,
                "metrics": evaluation["metrics"],
                "safety": evaluation["safety"],
                "release_qualified": release["release_qualified"],
                "output_dir": str(args.output_dir),
            },
            sort_keys=True,
        )
    )
    return 0


def _load_or_create_case_key(path: Path) -> bytes:
    if path.exists():
        key = path.read_bytes()
        if len(key) != 32:
            raise SystemExit("P110 case-id key must contain exactly 32 bytes")
        return key
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(key)
    return key


def _load_allowed_env(path: Path) -> None:
    if not path.exists():
        return
    allowed = {"NVIDIA_API_KEY", "OPSCAT_NVIDIA_MODEL"}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in allowed and key not in os.environ:
            os.environ[key] = value.strip().strip("\"'")


def _replay_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise SystemExit("replay JSON must be an object keyed by the full P110 cache key")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _implementation_hash() -> str:
    paths = (
        ROOT / "app/services/p110_rcaeval.py",
        ROOT / "app/services/p110_candidate_runner.py",
        ROOT / "app/services/p110_evaluation.py",
        ROOT / "scripts/run_p110_labeled_benchmark.py",
    )
    return stable_hash({path.name: _sha256_file(path) for path in paths})


def _write_summary(path: Path, evaluation: dict[str, Any], candidate: dict[str, Any], release: dict[str, Any]) -> None:
    metrics = evaluation["metrics"]
    lines = [
        "# P110 labeled RCAEval result",
        "",
        f"- Cases: {evaluation['summary']['case_count']}",
        f"- Provider calls: {candidate['budget']['provider_call_count']}",
        f"- Service Top-1: {metrics['service_top1']['value']}",
        f"- Service Top-3: {metrics['service_top3']['value']}",
        f"- Fault accuracy: {metrics['fault_accuracy']['value']}",
        f"- Evidence precision: {metrics['evidence_precision']['value']}",
        f"- Abstention rate: {metrics['abstention_rate']['value']}",
        f"- Safety: `{json.dumps(evaluation['safety'], sort_keys=True)}`",
        f"- Release qualified: {str(release['release_qualified']).lower()}",
        "- Release remains false until a fresh independent review binds the artifacts.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
