SHELL := /usr/bin/env bash
UV ?= uv
HOST ?= 127.0.0.1
PORT ?= 8000

.PHONY: help install test demo evals verify run quickstart

help:
	@printf 'OpsCat local commands:\n'
	@printf '  make install     Install Python dependencies with uv.\n'
	@printf '  make demo        Run deterministic local/mock demo.\n'
	@printf '  make evals       Run incident and connector eval reports.\n'
	@printf '  make test        Run pytest regression suite.\n'
	@printf '  make verify      Run full release gate.\n'
	@printf '  make run         Start local FastAPI app.\n'
	@printf '  make quickstart  Run demo plus evals with no external credentials.\n'

install:
	$(UV) sync --extra dev

test:
	$(UV) run --no-sync --extra dev pytest -q

demo:
	$(UV) run --no-sync --extra dev python scripts/demo.py

evals:
	$(UV) run --no-sync --extra dev python scripts/run_evals.py --output-json /tmp/opscat-evals.json --output-md /tmp/opscat-evals.md >/tmp/opscat-evals-latest.md
	$(UV) run --no-sync --extra dev python scripts/run_connector_evals.py --output-json /tmp/opscat-connector-evals.json --output-md /tmp/opscat-connector-evals.md >/tmp/opscat-connector-evals-latest.md
	@printf 'Wrote /tmp/opscat-evals-latest.md and /tmp/opscat-connector-evals-latest.md\n'

verify:
	bash scripts/verify.sh

run:
	$(UV) run --no-sync --extra dev uvicorn app.main:app --host $(HOST) --port $(PORT)

quickstart: demo evals
	@printf 'OpsCat quickstart complete. No auth setup or production credentials were required.\n'
