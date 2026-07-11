# P113 test specification

## Diagnosis/narrative separation

- A valid diagnosis survives malformed JSON, timeout, provider exception,
  excessive services, excessive suggestions, unsupported evidence, prompt
  injection text, and harmful narrative output.
- Narrative can neither change ranked services/faults nor add executed actions.
- Diagnostic invalidity still fails the entire diagnosis closed.
- Every status and hash is deterministic and replayable.
- Result fields are explicitly separated into `deterministic_judgment`,
  `llm_advisory`, and disabled `action_contract_status`; no evaluator treats
  deterministic output as provider-authored output.

## Model regression

- Service rename/order invariance remains exact.
- Disk features cover utilization, capacity, filesystem, I/O latency,
  throughput, queue, read, and write metric aliases.
- Missing/zero/counter-reset values remain finite and deterministic.
- Consumed OB/SS regression reports include per-service and per-fault slices.
- No model-selection code reads TT labels before freeze.
- A taint ledger rejects P112 repetition-4 case IDs, labels, per-case errors,
  fixtures, thresholds, weights, and prompt examples from P113 release inputs.

## Provider contract fuzzing

- Fuzz extra keys, reordered keys, duplicate suggestions, oversized arrays,
  markdown wrappers, strings instead of arrays, NaN/Infinity, Unicode, unknown
  citations, unknown services, and action-like text.
- Normalization is bounded and cannot manufacture evidence or action authority.
- Invalid narrative produces an empty narrative and explicit validation errors.
- Raw and normalized contract-validity metrics are both retained; truncation or
  normalization cannot convert a raw failure into a raw success.

## Freeze and blind evaluation

- Freeze binds source bytes, complete TT case set, model, P112 baseline,
  diagnosis/narrative packets, system prompt, endpoint/API/decoding, code, gates,
  and narrative subset IDs.
- Partial batches cannot bypass full-corpus validation.
- Evaluator owns labels, paired metrics, repeat metrics, and safety counters.
- Same report/run IDs cannot satisfy independent repeat evidence.

## Verification commands

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_p113_*.py
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev ruff check app/services/p113_*.py scripts/*p113*.py tests/test_p113_*.py
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev mypy app/services/p113_*.py scripts/*p113*.py
bash scripts/verify.sh --profile p113-release
```
