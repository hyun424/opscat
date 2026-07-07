# OpsCat P16 Final Summary — LLM Provider Evaluation Runner

P16 adds a provider evaluation layer that measures whether mock and opt-in NVIDIA LLM judgments are safe and useful across incident judgment cases. The runner scores schema validity, evidence citations, route judgment, hypothesis coverage, required evidence coverage, forbidden-action handling, and safety-gate outcomes.

## Boundary

- no-auth/local-mock by default.
- Normal verification uses the mock provider and performs no external model/API calls.
- NVIDIA live evaluation is explicit opt-in through a locally parsed env file; API keys are not printed or persisted.
- No production mutation, Kubernetes/cloud/database execution, unrestricted shell, action execution, or hosted unattended operation.
- This evidence does not claim unattended production operation.

## Ticket closure map

| Ticket | Result | Artifact |
| --- | --- | --- |
| P16-001 | DONE | `app/services/llm_provider_evaluation.py` case-level dimension scoring |
| P16-002 | DONE | `run_llm_provider_evaluation` aggregate provider runner |
| P16-003 | DONE | mock baseline smoke in `scripts/verify.sh` |
| P16-004 | DONE | `scripts/run_llm_provider_eval.py --provider nvidia --env-file .env --max-cases ...` |
| P16-005 | DONE | JSON and Markdown reports with aggregate and case-level results |
| P16-006 | DONE | explicit failure reasons and safety regression list |
| P16-007 | DONE | this summary, roadmap update, and release evidence index |

## Verification commands

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_llm_provider_evaluation.py tests/test_p16_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev ruff check app tests scripts`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev mypy app tests scripts`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`

## NVIDIA live opt-in command

Use only when evaluating the live provider intentionally. The env file is parsed as text, not sourced as shell.

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run --extra llm python scripts/run_llm_provider_eval.py \
  --cases evals/judgment/seed/cases.json \
  --provider nvidia \
  --env-file .env \
  --max-cases 4 \
  --output-json /tmp/opscat-nvidia-provider-eval.json \
  --output-md /tmp/opscat-nvidia-provider-eval.md
```

## Key artifacts

- `app/services/llm_provider_evaluation.py`
- `scripts/run_llm_provider_eval.py`
- `tests/test_llm_provider_evaluation.py`
- `tests/test_p16_release_evidence.py`
- `/tmp/opscat-llm-provider-eval-latest.md` from mock verification smoke.
