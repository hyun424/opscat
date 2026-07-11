# Upgrade and compatibility

## 0.1.x to 0.2.0

Schema marker: `p122.migration_compatibility.v1`.

Executable fixture verification:

```bash
uv run --no-sync --extra dev python scripts/verify_p122_migration_compatibility.py \
  --workdir /tmp/opscat-p122-migration \
  --output /tmp/opscat-p122-migration/report.json
```

The verifier creates a local `0.1.x` fixture, backs it up, upgrades it to the
`0.2.0` local-state schema, restores the backup, rolls the upgraded state back
to the prior record set, and verifies public-contract compatibility. Upgrade,
restore, and rollback must each preserve the exact
`P121_AUTHORITY_COUNTER_KEYS` key set with integer (not Boolean) zero values;
missing keys, extra keys, Boolean zeros, and nonzero integers fail
compatibility. It uses local JSON fixtures only and grants no additional
authority.

The persisted report records the exact key set check explicitly:

```json
{
  "schema_version": "p122.migration_compatibility.v1",
  "authority_key_set_exact": true,
  "authority_values_int_zero": true,
  "compatibility_verified": true,
  "rollback_verified": true
}
```

Manual operator sequence:

1. Back up local SQLite/PostgreSQL state and replay artifacts before installing.
2. Install from the tracked lock or verified wheel.
3. Run existing migration tooling in local/test mode.
4. Run `opscat contracts` and compare contract version `1.0.0`.
5. Run the fixture demo and frozen release profiles before restoring local state.

Unsupported schema or release-evidence versions fail closed; they are never silently rewritten. CLI and public contract removals receive at least one minor-release deprecation period. Rollback restores the backup and prior package artifact. Auth remains deferred and migrations do not add authority.

## Troubleshooting

- `unsupported_legacy_fixture`: keep the original backup and do not rewrite the
  state file until a version-specific migration exists.
- `rollback_verified = false`: restore the backup artifact and block release.
- `compatibility_verified = false`: compare `opscat contracts` output against
  `app.public_contracts.PUBLIC_CONTRACT_VERSION`.
- `authority_key_set_exact = false`: compare the artifact with the exact key
  set from `app.services.p121_signals.P121_AUTHORITY_COUNTER_KEYS`; do not add
  compatibility aliases or silently drop unknown keys.
