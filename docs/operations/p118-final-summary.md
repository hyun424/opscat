# P118 Final Summary

P118 qualifies a **local/mock/sandbox reactive execution substrate**. It does
not qualify production remediation, auth, credentials, or operator replacement.

## Delivered

- Real P117 deterministic decision output to real signed `p115.action_pack.v1`
  verification, including canonical P115 signature/hash validation.
- Immutable P118 operation envelopes with local target prefixes, L3 ceiling,
  exact-zero nonlocal-authority counters, validation and rollback references.
- Append-only hash-chained WAL, atomic CAS/idempotency/lease acquisition,
  measured pre/post validation, evidence-bound worker transitions, rollback,
  orphan recovery, and read-only terminal replay.
- End-to-end approval receipt validation: verification, approval, lease, and
  WAL receipts must carry exact self-hashes and bind to the same operation,
  policy, freshness window, WAL position, lease owner, and CAS version before
  worker or validation progression. The decision hash includes the complete
  executable operation context plus verification and lease expiry, lease/WAL
  receipt hashes, WAL position, CAS version, decision time, and policy counters.
- Every consumed approval receipt carries the complete exact P118 authority
  counter key set with integer zeros; missing keys, empty mappings, booleans,
  and nonzero values fail closed.
- Executable crash matrix covers before/after precheck, action, postcheck,
  rollback, rollback-postcheck, and report-write boundaries.
- Persisted 338-case frozen adversarial manifest and evaluation covering 13
  safety families. Each case carries fixture input, P115 action-pack refs, P117
  decision refs, expected probes, and crash point instead of relying on
  evaluator-synthesized truth.

## Evidence

- Release profile: `bash scripts/verify.sh --profile p118-release`
- Frozen evaluation: `evals/p118/frozen-evaluation.json`
- Release evidence: `evals/p118/release-evidence.json`
- Frozen evaluation hash:
  `sha256:83b544acdc57b395f3dfebfc547116b826e2c6f39ab9294ccb2f56e699eea728`
- Release evidence hash:
  `sha256:f678180d5006260e3f08cdb7f5e790b6a4f492888d8911acd9a7a4015b5f1fc4`
- Qualified claim: `p118_local_mock_sandbox_ready`
- Duplicate action, optimistic success, rollback-without-evidence, and all
  production/nonlocal authority counters: zero in the frozen qualification.

## Limits

The fixtures are synthetic and local. Passing them proves contract behavior
against the frozen suite, not effectiveness or safety on a real production
system. Auth remains deliberately deferred and no production adapter exists.
