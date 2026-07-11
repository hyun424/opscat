# Supply Chain

## Deterministic Artifacts

The P122 security gate writes:

- `evals/p122/security-report.json`
- `evals/p122/sbom.json`
- `evals/p122/license-inventory.json`
- `evals/p122/vulnerability-audit.json`

The SBOM is CycloneDX-shaped and generated from `uv.lock`. Package hashes are
copied from locked source distributions and wheels when present. The license
inventory is generated from installed package metadata or the documented
allowlist embedded in `scripts/run_p122_security_gate.py`.

Known-vulnerability evidence is produced separately by
`scripts/run_p122_vulnerability_audit.py`. It exports the hash-pinned runtime
graph from `uv.lock`, runs pinned `pip-audit==2.10.1`, and binds the result to
the exact lockfile hash. Any reported vulnerability or stale lock fails closed.

## Release Rules

- Dependencies must come from the lockfile and include hashes where available.
- Unknown and incompatible licenses block release.
- GPL and AGPL-family findings are treated as incompatible for this
  local/sample release gate unless a later legal review changes the policy.
  LGPL runtime dependencies are allowed when they are identified explicitly in
  the license inventory.
- Generated security reports redact candidate secret values and expose only
  fingerprints.
- Generated reports are excluded from subsequent scans to avoid self-noise.

## Invocation

Run the scoped gate locally:

```bash
python3 scripts/run_p122_security_gate.py
python3 scripts/run_p122_vulnerability_audit.py
```

For evidence refresh while other P122 work is still in progress:

```bash
python3 scripts/run_p122_security_gate.py --no-fail
```

`--no-fail` is only for artifact generation during development; a release gate
must exit nonzero when blocking findings remain.
