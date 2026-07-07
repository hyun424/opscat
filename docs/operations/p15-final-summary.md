# OpsCat P15 Final Summary — NVIDIA LLM Provider Opt-in

P15-mini adds an explicit NVIDIA/OpenAI-compatible provider for live model judgment while preserving no-auth/local-mock by default behavior. The selected default model is `nvidia/nemotron-3-ultra-550b-a55b`. Normal verification still uses mock/fake clients and performs no network calls. Live use requires `NVIDIA_API_KEY` and explicit `--provider nvidia`.

## Boundary

- no-auth/local-mock by default.
- No login/session UI, committed API keys, production credentials, hosted SaaS operations, Kubernetes/cloud/database mutation, unrestricted shell execution, default external model/API calls during verification, or action execution.
- This evidence does not claim unattended production operation.

## Ticket closure map

| Ticket | Result | Artifact |
| --- | --- | --- |
| P15-001 | DONE | `NvidiaLLMJudgmentProvider` OpenAI-compatible provider in `app/services/llm_judgment.py` |
| P15-002 | DONE | `NVIDIA_API_KEY` key gate with `LLMProviderConfigurationError` |
| P15-003 | DONE | `build_llm_judgment_prompt_messages` JSON-only/evidence-citation/safety prompt contract |
| P15-004 | DONE | NVIDIA response JSON parsing and P14 validation path |
| P15-005 | DONE | `scripts/run_llm_judgment.py --provider nvidia --model ...` selection |
| P15-006 | DONE | offline fake-client tests; normal verify avoids live calls |
| P15-007 | DONE | this summary, roadmap update, and release evidence index |

## Live opt-in command

```bash
export NVIDIA_API_KEY="..."
# install/use the optional live provider dependency with uv run --extra llm
OPSCAT_NVIDIA_MODEL=nvidia/nemotron-3-ultra-550b-a55b \
uv run --extra llm python scripts/run_llm_judgment.py \
  --cases evals/judgment/seed/cases.json \
  --case-id seed-loghub-injection-block \
  --provider nvidia \
  --output-json /tmp/opscat-nvidia-judgment.json \
  --output-md /tmp/opscat-nvidia-judgment.md
```

The output still passes through schema validation, evidence citation checking, and safety gate. It does not execute actions.

## Verification commands

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_nvidia_llm_provider.py tests/test_p15_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_llm_judgment.py tests/test_llm_judgment_cli.py tests/test_p14_release_evidence.py tests/test_nvidia_llm_provider.py tests/test_p15_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache bash scripts/verify.sh --profile full`
