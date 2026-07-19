from __future__ import annotations

import argparse
from pathlib import Path

from app.services.p175_live_release import validate_release_evidence, write_release_artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize canonical P175 live-release closeout artifacts.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--review", type=Path, required=True, help="Externally produced independent review JSON.")
    args = parser.parse_args(argv)

    paths = write_release_artifacts(args.review, args.project_root)
    release = paths["release"]
    validation = validate_release_evidence(
        __import__("json").loads(release.read_text(encoding="utf-8")),
        project_root=args.project_root,
    )
    print(f"wrote {release}")
    print(f"evidence_hash {validation['evidence_hash']}")
    print(f"review_hash {validation['review_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
