# P163 Plan Review

Decision: approved for supervised process-owned lab only.

- Require explicit approval capability for each mutation.
- Use only fixed actions: restart worker, rollback canary, tune pool.
- Capture pre-state hash before action.
- Verify with a fresh observation independent from the action receipt.
- Roll back harmful, stale, or insufficiently improved outcomes.
- Never translate this result into production authority.
