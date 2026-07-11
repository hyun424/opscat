# P122 tickets

P122 defines the open-source production-packaging phase for OpsCat. It packages
the verified local/mock/sandbox system as an installable, inspectable,
reproducible incident-response agent with stable public contracts, clean local
demo, secure release gates, contributor paths, release artifacts, and
independent review.

P122 is implemented as an installable local release-candidate scope. Auth is
deferred, credentials are out of scope, production and staging mutation are
forbidden, live connector authority is forbidden, and every
production/nonlocal authority counter must remain exactly zero.

1. `[implemented] P122-001` - architecture cleanup and stable public contracts
2. `[implemented] P122-002` - packaging, clean install, sample deployment, and local demo
3. `[implemented] P122-003` - public docs, tutorials, contributor guide, and limitations
4. `[implemented] P122-004` - security threat model, secret scanning, SBOM, licenses, and supply chain
5. `[implemented] P122-005` - CI matrix and reproducible frozen evals
6. `[implemented] P122-006` - performance, soak, crash/replay, and agent observability
7. `[implemented] P122-007` - upgrade, migration, compatibility, and release artifacts
8. `[verification pending] P122-008` - release candidate review, verification handoff, and public limitations

See `docs/operations/p122-open-source-production-packaging-roadmap.md`,
`docs/operations/p122-test-spec.md`,
`docs/operations/p122-plan-review.md`, and
`docs/operations/p122-verification-handoff.md`.

Schema marker: `p122.ticket_index.v1`.

Generated P122 reports use `p122.performance_soak.v2`,
`p122.migration_compatibility.v1`, and `p122.docs_verification.v1`. The
performance report includes the executed 12-point release crash matrix and the
migration report requires the exact P121 authority key set with integer-zero
values.

Executable P122-specific verification examples:

```bash
uv run --no-sync --extra dev python scripts/verify_p122_docs.py
uv run --no-sync --extra dev python scripts/verify_p122_migration_compatibility.py --workdir /tmp/opscat-p122-migration
```

Every P122 ticket preserves architecture/public contracts, clean install and
demo, docs/tutorials, security/SBOM/licenses/supply chain, CI and reproducible
evals, performance/soak/agent observability, migrations/compatibility/release
artifacts, independent review, auth deferred, no production mutations,
exact-zero authority, honest local-vs-production claims, no credentialed
execution, no live connector writes, no Kubernetes/cloud/database/network
mutation, no online policy writes, no L4+ actions, no free-form action
execution, and no LLM command execution.

## Troubleshooting

- If a ticket says implemented but verifier evidence is missing, mark the
  release-candidate gate pending.
- If a ticket requires live production proof, it is out of P122 scope.
