# Installation

## Supported matrix

- Python 3.12, 3.13, or 3.14 on current macOS and Ubuntu Linux
- `uv` with the tracked `uv.lock`
- Container images are not P122 release artifacts; Docker is optional and is
  outside the declared clean-wheel support matrix.

```bash
git clone <repository-url>
cd opscat
uv sync --frozen --extra dev
uv run --no-sync opscat contracts
```

Build two clean source copies, canonicalize the sdist, compare both wheel/sdist
outputs byte-for-byte, and write checksums with:

```bash
uv run --extra dev python scripts/verify_p122_reproducible_build.py
uv run --extra dev python scripts/verify_p122_clean_install.py
```

The second command installs the wheel into a clean temporary virtual
environment, runs `opscat demo` and `opscat contracts`, uninstalls the package,
and checks for import residue. The default configuration uses
`fixture://local-demo`, performs no network calls, and reads no credentials.
The container/config CI job also parses `config/opscat.local.example.json` and
requires `production_mutation_enabled` plus every execution or live-call toggle
to remain `false`; it builds and runs a package container with networking
disabled and no credentials.

Production or staging mode is deliberately rejected by the public demo. Auth is deferred and no production mutation path is part of the supported release.

Schema checks used by install verification include
`p122.clean_install.v1`, `p122.reproducible_build.v1`, and
`opscat.public_contracts.v1`.

## Troubleshooting

- `uv sync --frozen` fails: the lock file and Python version are out of the
  supported matrix; rerun on Python 3.12, 3.13, or 3.14.
- `opscat demo` exits with code 2: unset production-like `OPSCAT_MODE` or use a
  `fixture://` target.
- Import residue after uninstall blocks the clean-install gate.
- A container config failure means the example JSON or composed service no
  longer preserves the local, credential-free boundary.
