# P140 Final Summary

P140 is qualified as a credential-free, network-free local P139-to-P133
dead-man adapter. It does not implement notification delivery or remediation.

## What changed

- P139 health and terminal evidence are revalidated through its public status
  API and mapped into the closed P133 watchdog contract.
- P133 remains the sole durable event/cursor/acknowledgement writer.
- Stable projection excludes volatile observation time and status hash.
- Invalid target state becomes a deterministic redacted fingerprint.
- P140 and P133 leases serialize whole runs and durable writes.
- P133 write roots are contained by P140 roots; descriptor-relative no-follow
  reads reduce path replacement races.
- CLI, systemd, and Compose surfaces are explicit, non-root, and networkless.

## Verified evidence

- P140 matrix: 32 expected, 32 passed, 0 failed.
- Matrix hash:
  `sha256:a30f3aa123efa3b1c06a764567c0ed443b4433c25acf37a13eef371365afda21`.
- Final review hash:
  `sha256:507e1d354eb1982a03e5a4b94614e13250c967c2fc583a90ddc6d13c7b3f5621`.
- Final evidence hash:
  `sha256:d8b7ac9a539228fce6505dda8876088d5f3489dcdb8e7e146655b4e7cea209eb`.
- `bash scripts/verify.sh --profile p140-release` reproduces the complete
  P133 and refreshed P136-P139 dependency chain plus P140 final mode.

## Defect found before release

The adversarial P140 suite proved that P139 treated a future-dated control
timestamp as fresh. P139 now rejects negative control age, and P136-P140 release
evidence was refreshed in dependency order rather than accepting stale hashes.

## Remaining limits

- Local outbox evidence is not delivered notification evidence.
- No authenticated external reviewer identity is proven.
- Deployment review is static; no live systemd or Compose host was qualified.
- No auth, credential, network, notification, action, remediation,
  staging/production mutation, unattended-operation, or operator-replacement
  authority is granted.
