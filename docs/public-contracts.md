# Public contracts

`app.public_contracts.public_contract_manifest()` is the machine-readable source of truth. Stable v1 surfaces are:

- `opscat demo` and `opscat contracts`
- `app.plugin_sdk.ReadOnlyConnectorV1`
- the signed P115 action-pack schema
- freshness-bound release-evidence schemas

Every public contract declares its owner, version/stability, compatibility and deprecation rule, authority level, documentation, tests, release evidence, and `nonlocal_authority_allowed=false`. Everything else under `app.services` remains internal unless listed in the manifest.

`opscat-monitor` and the P132 supervisor examples are qualified local runtime
surfaces, but they are not yet part of the stable v1 compatibility manifest.
Their current contract is credential-free local JSONL observation with exact-zero
action authority; direct live connectors and remediation remain excluded.

Read-only connectors may collect evidence. A connector exposing write, mutate, execute, delete, apply, or patch capabilities is rejected by the SDK validator. This interface does not convey credentials or production authority.
