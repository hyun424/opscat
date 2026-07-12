# Compatibility

Schema marker: `p129.compatibility_policy.v1`.

OpsCat public contracts are `stable-v1` only where listed in
`docs/public-contracts.md` and `app.public_contracts.public_contract_manifest`.
Everything else remains internal.

Supported interpreter declarations:

- Python 3.12
- Python 3.13
- Python 3.14

Compatibility policy:

- Additive changes are allowed within the current minor line.
- Breaking public-contract changes require a new major contract version.
- Deprecation must be documented for at least one minor release before removal.
- Migration notes must describe changed schemas, commands, and evidence files.
- Local/mock/sandbox qualification must not be described as production autonomy.

Out of scope: auth, credentials, production/staging mutation, enterprise
support readiness, and operator replacement unless a later accepted roadmap adds
evidence for them.
