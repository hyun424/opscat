# P104-010 - CLI, Docs, and Release Integration

## Goal

Integrate P104 with the offline CLI, JSON/Markdown report writer, release docs,
roadmap, README, and verification script after implementation and independent
review.

## Tests First

- CLI rejects invalid bounds without traceback.
- Default CLI writes JSON and Markdown reports with zero model/network calls.
- `tests/test_p104_release_evidence.py` checks roadmap, final summary,
  release evidence, README, `ROADMAP.md`, and `scripts/verify.sh` references.
- Verification script includes targeted tests and P104 smoke command.

## Implementation Notes

- Add `scripts/run_evidence_gap_investigator.py` with deterministic defaults.
- Optional `--include-nvidia` mode must be explicit opt-in and advisory-only.
- Do not create `docs/operations/p104-plan-review.md`; independent review owns
  that artifact.

## Acceptance

- Release docs state the synthetic/local boundary and no-production-mutation
  limitation.
- P104 verification can run network-free by default.

## Verification

Run:

```bash
./.venv/bin/python -m pytest tests/test_evidence_gap_investigator.py
./.venv/bin/python -m pytest tests/test_p104_release_evidence.py
./.venv/bin/python scripts/run_evidence_gap_investigator.py --max-cases 16 --sample-size 5
./scripts/verify.sh fast
./scripts/verify.sh docs
```
