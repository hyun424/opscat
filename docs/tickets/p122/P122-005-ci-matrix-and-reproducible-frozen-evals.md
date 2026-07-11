# P122-005: CI matrix and reproducible frozen evals

## Goal

Create a release CI matrix that proves tests, contracts, packaging, docs,
security, licenses, SBOM, frozen evals, and release evidence across supported
environments.

## Contract

- CI covers supported OS, Python, and container modes.
- CI runs unit, integration, contract, authority-boundary, packaging,
  install/uninstall, docs, security, secret, SBOM, license, supply-chain,
  reproducibility, and release-evidence consistency checks.
- Frozen evals rerun from pinned manifests and produce stable hashes or
  documented deterministic tolerances.
- Release evidence rejects stale hashes, missing manifests, self-reviewed
  evidence, partial evals, tampering, aggregate-only metrics, missing
  denominators, missing confidence intervals, and nonzero authority counters.
- Release claims are machine-checkable against evidence refs.

## Acceptance

The declared CI matrix is complete for P122 release scope, required gates
cannot be silently skipped, stale caches cannot generate release evidence, and
frozen eval reproducibility can be verified from a clean checkout. Every public
release claim traces to evidence or a limitation.

## Stop Rules

Stop if CI skips required gates, accepts stale cached evidence, promotes
partial evals, ignores flaky gates, omits authority-boundary checks, reuses
consumed holdouts for tuning, hides aggregate-only metrics, allows self-review,
or permits release evidence with nonzero authority counters or untraced public
claims.
