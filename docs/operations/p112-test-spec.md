# P112 test specification

## Acquisition and parsing

- Reject network acquisition unless explicitly enabled.
- Reject URL redirect, filename, byte-size, MD5, SHA-256, case-count, path, or
  repetition mismatch.
- Parse RE1-SS without hard-coded Online Boutique service names.
- Prove candidate packets contain no truth, source path, repetition, or label.

## Cross-system model

- Feature schema is invariant to service renaming and service order.
- Training repetitions are explicit, non-empty, and disjoint from validation,
  confirmation, and blind roles.
- Artifact hashes cover feature schema, scaling statistics, prototypes,
  training source hash, and repetition role declaration.
- Loss/delay coupling features have deterministic finite values for zero and
  missing denominators.
- Scoring rejects unknown/tampered artifacts and returns only allowlisted
  services/faults.

## Freeze and provenance

- Freeze binds both baseline and candidate model/request envelopes.
- Any source, packet, prompt, decoding, implementation, endpoint, API, or
  system-prompt mismatch fails before blind execution.
- Partial batch merges cannot bypass full-corpus freeze validation.
- Baseline artifacts without the required request-envelope fields fail closed.

## Evaluation and safety

- Metrics are recomputed from scorer-only truth and predictions.
- Paired rows require identical case IDs and official source hashes.
- Repeat agreement, calibration, per-fault floors, and safety counters are
  evaluator-owned.
- Release remains false when any quality, safety, freeze, or cryptographic
  review gate fails.
- Provider output and deterministic synthesis output both replay exactly.

## Verification commands

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_p112_*.py
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev ruff check app/services/p112_*.py scripts/*p112*.py tests/test_p112_*.py
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev mypy app/services/p112_*.py scripts/*p112*.py
bash scripts/verify.sh --profile p112-release
```
