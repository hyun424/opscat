#!/usr/bin/env python3
"""Run or inspect OpsCat database migrations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.migrations.runner import migration_status, run_migrations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="OpsCat migration runner")
    parser.add_argument("command", choices=("upgrade", "status"), nargs="?", default="upgrade")
    args = parser.parse_args()

    if args.command == "status":
        for item in migration_status():
            marker = "applied" if item.applied else "pending"
            print(f"{item.version}\t{marker}\t{item.description}")
        return 0

    applied = run_migrations()
    if applied:
        print("Applied migrations: " + ", ".join(applied))
    else:
        print("No pending migrations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
