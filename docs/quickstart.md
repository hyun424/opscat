# Network-free quickstart

```bash
uv sync --frozen --extra dev
uv run --no-sync opscat demo --output /tmp/opscat-demo-replay.json
python -m json.tool /tmp/opscat-demo-replay.json
```

Expected properties:

- `network_calls = 0`
- `credential_reads = 0`
- `production_mutations = 0`
- every authority counter is exactly zero
- a deterministic `replay_hash` binds the record

Setting `OPSCAT_MODE=production` or a non-`fixture://` target makes the command exit with code 2 and no replay file.

Replay schema: `opscat.local_demo.v1`.

Example blocked production-like run:

```bash
OPSCAT_MODE=production uv run --no-sync opscat demo --output /tmp/blocked.json
```

## Troubleshooting

- Missing replay file with exit code 2 means the fail-closed configuration gate
  worked.
- A nonzero authority counter means the replay must not be used as P122 release
  evidence.
