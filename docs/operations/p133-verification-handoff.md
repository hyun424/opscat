# P133 Verification Handoff

Status: complete. Implementation, promoted P133 evidence, independent review,
and the dedicated release profile pass within the local, credential-free scope.

Independent review findings were closed before promotion: first-run path-space
checks, acknowledgement retry identity, retention races, launchd overclaiming,
credential-like value rejection, exact source and manifest bindings, real
cross-process lease contention, post-validation path swaps, same-inode same-size
rewrite detection immediately before retention deletion, trusted owner-only
retention-directory enforcement, cursor rollback,
substantive subprocess evidence, exact resource measurement, and static-check
coverage were all added or corrected.

P133 was implemented with tests first. The final focused suite covers 29 core
outbox behaviors plus release-evidence validation, adversarial artifact mutation,
supervisor mutation, source omission, raw/promoted drift, resource-boundary type
confusion, and P132 compatibility. The canonical `p133-release` profile passes.

Promoted artifacts are under `evals/p133/`. The transition/fault matrix passes
20 of 20 cases, and the real process matrix records eight substantive CLI cases.
The canonical run measured 1,541 ms wall time, 464 ms combined CPU time, and
37,666,816 bytes peak resident memory. Runtime authority counters remain exact
integer zero; evaluator-owned process and signal activity is reported separately.

Canonical artifact hashes:

- outbox report: `sha256:649fb77b2bdb4e8e42ba097a174e52de83a8aef0ab89cbda795b12bde5e56419`
- process matrix: `sha256:78be53f75b07804568490aeb34879d7c0d3a580b82e21b807f7d9c08d1b7a820`
- supervisor validation: `sha256:8a8b21ea2276ccb1397e3b42455f2f35c71d414e34f85c9c440871310c534319`
- authority ledger: `sha256:fae6de567ccffe4a299c338f22994c271ab6e2279a8b0bdd967133d3f7b6ae9d`
- release evidence: `sha256:ba47502a7b82cea2521c581716801563f4ea31746cc243dfbbbd639707ffe73f`

Reproduce the bounded qualification with:

```bash
bash scripts/verify.sh --profile p133-release
```

The systemd and Compose manifests are qualified configuration contracts. The
launchd plist is intentionally recorded as an example only because it cannot by
itself enforce no-network and read-only-monitor-state isolation. No real service
manager boot, external destination, 24/7 soak, multi-host failover, notification
delivery, remediation, or malicious same-UID writer resistance was qualified.
Those claims remain closed.
