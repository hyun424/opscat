# OpsCat P18B Final Summary — Model Judgment Quality Lab

P18B adds a local/mock model judgment quality lab that measures raw provider behavior separately from the P17 policy-calibrated OpsCat result. It is designed to answer whether an LLM is actually useful for incident judgment before trusting it as an advisory brain.

## Tickets closed

- P18B-001 Raw vs calibrated score split: `raw_provider_score`, `calibrated_score`, and `calibration_delta`.
- P18B-002 Judgment quality dimension expansion: raw route, calibrated route, hypothesis, citation, required evidence, missing evidence, action proposal, forbidden action, and safety.
- P18B-003 Provider failure taxonomy: route over-auto, too conservative, missing evidence ignored, hallucinated citation, unsafe action allowed, weak hypothesis, low action quality, schema/parse failure.
- P18B-004 P18A snapshot case selector: loads P18A replay `snapshots` into `JudgmentCase` records.
- P18B-005 Prompt contract hardening v2: stricter `local_mock_auto_allowed` preconditions and rollback/restart/no-data handling.
- P18B-006 Model quality report CLI: `scripts/run_model_quality_eval.py`.
- P18B-007 NVIDIA live regression evidence: opt-in path supported via `--provider nvidia --env-file .env`; normal verification remains mock/offline.
- P18B-008 Release evidence: verification smoke, roadmap, and release evidence updated.

## Artifacts

- `app/services/model_quality_lab.py`
- `scripts/run_model_quality_eval.py`
- `tests/test_model_quality_lab.py`
- `tests/test_p18b_release_evidence.py`
- `docs/operations/p18b-ticket-roadmap.md`
- `docs/operations/p18b-final-summary.md`
- `/tmp/opscat-model-quality-latest.md`

## Verification

Targeted:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_model_quality_lab.py tests/test_p18b_release_evidence.py
```

Full:

```bash
bash scripts/verify.sh --profile full
```

Live NVIDIA evidence captured after full verification:

- Command shape: `UV_CACHE_DIR=/private/tmp/uv-cache uv run --extra llm python scripts/run_model_quality_eval.py --provider nvidia --env-file .env ...`
- Output JSON: `/tmp/opscat-nvidia-model-quality-p18b.json`
- Output Markdown: `/tmp/opscat-nvidia-model-quality-p18b.md`
- Provider/model: `nvidia` / `nvidia/nemotron-3-ultra-550b-a55b`
- Cases: 5
- raw_provider_score: 0.778
- calibrated_score: 0.957
- calibration_delta: 0.179
- calibration_wins: 5
- Secret marker scan: passed for JSON and Markdown outputs.

## Boundary

P18B is no-auth/local-mock by default. It does not add login/session UI, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, action execution, or unattended production-operation claims; it does not claim unattended production operation.

Live NVIDIA use remains explicit opt-in:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run --extra llm python scripts/run_model_quality_eval.py \
  --cases evals/judgment/seed/cases.json \
  --p18a-replay-json /tmp/opscat-realtime-real-cache-p18a.json \
  --provider nvidia \
  --env-file .env \
  --max-cases 6 \
  --output-json /tmp/opscat-nvidia-model-quality-p18b.json \
  --output-md /tmp/opscat-nvidia-model-quality-p18b.md
```

The report separates raw provider quality from calibrated OpsCat safety behavior, so model weaknesses stay visible even when the policy layer prevents bad automation.
