# P131 Verification Handoff

## Implemented

- `app/services/p131_always_on_monitor.py` — strict config, bounded JSONL tail,
  monotonic scheduler, lease, checkpoint, canary, freshness, reports, watchdog.
- `app/monitor_cli.py` — explicit bounded or `--forever` run, watchdog, status.
- `app/api/health.py` — fail-closed monitor health/readiness HTTP surfaces.
- `app/services/p131_release_evidence.py` and
  `scripts/run_p131_always_on_monitor.py` — deterministic promoted evidence.

## Reproduce

```bash
bash scripts/verify.sh --profile p131-release
```

The profile runs P131 tests, Ruff, Mypy, deterministic evidence generation, and
fails unless cadence, restart, dead-man, tamper, canary, freshness, bounded
authority, and no-network/no-action gates all pass.

Promoted artifacts:

- `evals/p131/runtime-report.json`
- `evals/p131/watchdog-matrix.json`
- `evals/p131/release-evidence.json`

## Honest boundary

This qualifies a credential-free local read-only monitoring process. It does
not qualify direct live connectors, multi-host deployment, automatic external
notification, remediation, production autonomy, or operator replacement.
