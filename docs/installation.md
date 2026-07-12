# Installation

Schema marker: `p129.installation_policy.v1`.

OpsCat distribution maturity uses the existing local, credential-free install
path. It does not add auth, production credentials, live provider writes, or
production/staging mutation.

Supported interpreter declarations:

- Python 3.12
- Python 3.13
- Python 3.14

An unavailable declared interpreter is recorded as pending evidence rather than
treated as a silent pass.

```bash
uv sync --frozen --extra dev
uv run --no-sync opscat contracts
uv run --no-sync opscat demo --output /tmp/opscat-demo-replay.json
```

The default demo uses local fixtures, no credentials, and no network authority.
Release checks rely on the existing P122 wheel/sdist, clean install, contract,
demo, uninstall, SBOM, license, and security evidence.

