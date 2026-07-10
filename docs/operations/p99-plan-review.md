# P99 Plan Review

## Approved design

1. Preserve the original P97 120-case contract and compose a versioned P99 catalog around it.
2. Add 40 operational families selected by failure domain, not by vendor product.
3. Reuse the same 10 variants for every family so noisy evidence, ineffective first action, partial recovery, peak load, missing/conflicting telemetry, natural recovery, human approval, and compound failure remain comparable.
4. Give selectors only symptom, visible evidence, measured state, allowed local actions, and boundary metadata.
5. Keep every new action as a named in-memory mutation inside P97's closed registry.
6. Measure broad coverage and causal outcomes separately; family count is not evidence of good remediation quality.

## Adversarial review

### Rejected: claiming every possible incident is covered

Production failures are open-ended and organization-specific. P99 is a broad,
vendor-neutral taxonomy baseline, not a proof of exhaustive coverage.

### Rejected: adding vendor-specific shell commands

Commands such as `kubectl`, cloud CLIs, SQL, and system utilities would expand risk
without improving taxonomy coverage. P99 actions remain abstract, enumerated lab
transitions.

### Rejected: one happy-path case per family

Every family must include ambiguity, natural recovery, human-required, and compound
variants. This prevents a selector from scoring well by always acting.

### Rejected: evaluating only action selection accuracy

The benchmark continues to derive success from observed post-action and durability
measurements, with no-action and curated human-runbook controls.

## Acceptance review

- 52 total families and 520 unique cases.
- 312 development, 104 validation, and 104 blind cases.
- Resource, storage, database, network, dependency, platform, messaging, scheduler,
  configuration, security, data-integrity, regional, and cascading domains represented.
- All 40 new obvious-family runbooks produce measurable recovery in the local lab.
- Natural-recovery variants discourage unnecessary actions.
- Missing/conflicting telemetry and privileged families preserve escalation behavior.
- Zero unknown action execution, out-of-scope mutation, unsafe action, data loss,
  false recovery declaration, initial-state mismatch, or route-contract violation.
