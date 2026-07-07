# OpsCat P17 Final Summary — LLM Policy Calibration

P17 makes LLM provider output advisory rather than authoritative. OpsCat now runs a deterministic policy calibration step after provider judgment and the P14 safety gate. The calibrated decision is what provider evaluation scores, while the raw provider route remains visible for audit.

Boundary: no-auth/local-mock by default; no default external model/API calls; no action execution; no production mutation; no Kubernetes/cloud/database mutation; no unrestricted shell; does not claim unattended production operation.

## Ticket closure

| Ticket | Result | Artifact |
| --- | --- | --- |
| P17-001 | DONE | `app/services/policy_calibrator.py` defines `PolicyCalibrationResult` with provider route, safety-gate route, calibrated route, retained/removed actions, fatal risk flags, and reasons. |
| P17-002 | DONE | Context risk classification covers prompt injection, unsafe action requests, no-data/metric-only ambiguity, missing evidence, and deploy/rollback-sensitive situations. |
| P17-003 | DONE | Conservative route precedence blocks fatal risks and forces human review for insufficient evidence or over-aggressive auto routes. |
| P17-004 | DONE | Action filtering removes risky automatic candidates and retains no automatic actions for `human_required` or `blocked`. |
| P17-005 | DONE | `app/services/llm_provider_evaluation.py` scores calibrated route/action output while preserving provider and safety-gate routes. |
| P17-006 | DONE | Provider eval Markdown and `scripts/verify.sh` include policy calibration evidence in mock mode. |
| P17-007 | DONE | P17 roadmap, tickets, release evidence, and this final summary document the local/mock safety boundary. |

## Implementation evidence

- `app/services/policy_calibrator.py`
- `app/services/llm_provider_evaluation.py`
- `tests/test_policy_calibrator.py`
- `tests/test_p17_release_evidence.py`
- `scripts/verify.sh`
- `docs/operations/p17-ticket-roadmap.md`
- `docs/tickets/p17/README.md`
- `docs/release-evidence.md`

## Behavioral evidence

P17 specifically guards the NVIDIA-style failures observed in P16:

- no-data metric cases cannot auto-approve restart-like actions;
- deploy-regression cases cannot auto-approve rollback-like actions;
- prompt-injection evidence forces `blocked` even if a provider recommends automation;
- provider evaluation reports `provider_route`, `safety_gate_route`, and calibrated `final_route` separately.

## Verification

- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_policy_calibrator.py tests/test_p17_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_llm_provider_evaluation.py tests/test_p16_release_evidence.py`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev ruff check app tests scripts`
- `UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev mypy app tests scripts`
- `bash scripts/verify.sh --profile full`

## Safety position

P17 does not make OpsCat an unattended production operator. It makes OpsCat safer to evaluate with LLMs by proving the runtime can override provider recommendations before any execution layer exists.
