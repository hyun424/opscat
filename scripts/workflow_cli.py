"""Local workflow worker operations for OSS/self-hosted OpsCat."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import SessionLocal  # noqa: E402
from app.models import WorkflowJob  # noqa: E402
from app.services.workflow_service import process_next_workflow_job  # noqa: E402

DEFAULT_QUEUE = "incident.workflow"


@contextmanager
def _session_scope(provided: Session | None = None):  # type: ignore[no-untyped-def]
    if provided is not None:
        yield provided
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_workflow_cli(argv: Sequence[str] | None = None, *, db: Session | None = None) -> int:
    """Run local workflow queue commands and return a process-style exit code."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    with _session_scope(db) as active_db:
        if args.command == "stats":
            return _print_stats(active_db, queue_name=args.queue)
        if args.command == "drain":
            return _drain_queue(active_db, queue_name=args.queue, limit=args.limit, worker_id=args.worker_id)
        if args.command == "dead-letter-failed":
            return _dead_letter_failed(active_db, queue_name=args.queue, reason=args.reason)
    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the local OpsCat workflow queue.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    stats = subparsers.add_parser("stats", help="Print queue counts by status.")
    stats.add_argument("--queue", default=DEFAULT_QUEUE)

    drain = subparsers.add_parser("drain", help="Process pending workflow jobs in FIFO order.")
    drain.add_argument("--queue", default=DEFAULT_QUEUE)
    drain.add_argument("--limit", type=_positive_int, default=1)
    drain.add_argument("--worker-id", default="local-worker")

    dead_letter = subparsers.add_parser("dead-letter-failed", help="Move failed jobs to the dead-letter state.")
    dead_letter.add_argument("--queue", default=DEFAULT_QUEUE)
    dead_letter.add_argument("--reason", required=True)
    return parser


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def _print_stats(db: Session, *, queue_name: str) -> int:
    statuses = ["pending", "running", "completed", "failed", "dead_letter"]
    counts = {status: _count_jobs(db, queue_name=queue_name, status=status) for status in statuses}
    total = db.query(WorkflowJob).filter(WorkflowJob.queue_name == queue_name).count()
    fields = [f"queue={queue_name}", *(f"{status}={counts[status]}" for status in statuses), f"total={total}"]
    print(" ".join(fields))
    return 0


def _count_jobs(db: Session, *, queue_name: str, status: str) -> int:
    return db.query(WorkflowJob).filter(WorkflowJob.queue_name == queue_name, WorkflowJob.status == status).count()


def _drain_queue(db: Session, *, queue_name: str, limit: int, worker_id: str) -> int:
    processed = 0
    for _ in range(limit):
        job = process_next_workflow_job(db, queue_name=queue_name, worker_id=worker_id)
        if job is None:
            break
        processed += 1
        db.commit()
    print(f"queue={queue_name} processed={processed}")
    return 0


def _dead_letter_failed(db: Session, *, queue_name: str, reason: str) -> int:
    now = datetime.now(UTC)
    jobs = db.query(WorkflowJob).filter(WorkflowJob.queue_name == queue_name, WorkflowJob.status == "failed").all()
    for job in jobs:
        job.status = "dead_letter"
        job.last_error = reason
        job.updated_at = now
        db.add(job)
    db.commit()
    print(f"queue={queue_name} dead_lettered={len(jobs)}")
    return 0


def main() -> None:
    raise SystemExit(run_workflow_cli())


if __name__ == "__main__":
    main()
