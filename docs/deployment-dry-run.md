# Deployment Dry Run

This guide describes a local deployment dry run for OpsCat. It is not a production deployment guide. auth remains deferred and no production credentials are required.

## stable vs experimental

Stable for local/mock OSS use:

- FastAPI app process;
- SQLite quickstart;
- Docker Compose config validation;
- local Postgres via Docker Compose;
- fixture incidents and connector evals;
- `bash scripts/verify.sh --profile full`.

Experimental and not production-ready:

- real hosted auth;
- real provider OAuth/token setup;
- production workflow workers;
- external secret manager;
- real Slack/GitHub/Sentry mutations;
- customer production traffic.

## SQLite dry run

```bash
cp .env.example .env
make install
make verify
make run
```

The default local `DATABASE_URL` can point at SQLite for quick demos.

## Docker Compose and local Postgres

Validate the Docker Compose file without starting services:

```bash
docker compose config
```

Run a local Postgres-backed API:

```bash
docker compose up --build
curl http://localhost:8000/health
```

Example local Postgres `DATABASE_URL` shape:

```text
DATABASE_URL=postgresql+psycopg://opscat:opscat@localhost:5432/opscat
```

Use only local fixture data. Do not paste no production credentials, customer logs, provider tokens, or real incident payloads into local dry runs.

## Release evidence before publishing

Run:

```bash
bash scripts/verify.sh --profile full
```

Then review:

- `/tmp/opscat-evals-latest.md`;
- `/tmp/opscat-connector-evals-latest.md`;
- `docs/release-evidence.md`;
- `CHANGELOG.md`.
