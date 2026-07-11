#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.services.p110_evaluation import stable_hash  # noqa: E402

CORE_DOCS = (
    Path("docs/migration.md"),
    Path("docs/install.md"),
    Path("docs/quickstart.md"),
    Path("docs/performance.md"),
    Path("docs/operations/p122-verification-handoff.md"),
    Path("docs/operations/p122-final-summary.md"),
    Path("docs/tickets/p122/README.md"),
)
ROOT_DOCS = (
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path("SECURITY.md"),
    Path("CHANGELOG.md"),
)
RELEASE_AND_SECURITY_DOCS = (
    Path("docs/release-notes-0.2.0.md"),
    Path("docs/security-threat-model.md"),
    Path("docs/threat-model.md"),
    Path("docs/supply-chain.md"),
)
P122_DOCS = tuple(
    sorted(
        {
            *(path.relative_to(ROOT) for path in ROOT.glob("docs/**/*p122*.md")),
            *(path.relative_to(ROOT) for path in (ROOT / "docs/tickets/p122").glob("*.md")),
        },
        key=str,
    )
)
DOCS = tuple(
    sorted(
        {
            *CORE_DOCS,
            *ROOT_DOCS,
            *RELEASE_AND_SECURITY_DOCS,
            *P122_DOCS,
            Path("docs/public-contracts.md"),
            Path("docs/release-evidence.md"),
            Path("docs/limitations.md"),
            *(path.relative_to(ROOT) for path in (ROOT / "docs/operations").glob("p122*.md")),
            *(path.relative_to(ROOT) for path in (ROOT / "docs/tickets/p122").glob("*.md")),
        },
        key=str,
    )
)
LOCAL_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
JSON_BLOCK = re.compile(r"```json\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
SHELL_BLOCK = re.compile(r"```(?:bash|sh|shell|console)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
SCRIPT_COMMAND = re.compile(r"(?:python(?:3)?\s+|bash\s+)(scripts/[A-Za-z0-9_.\-/]+)")
SCHEMA_REF = re.compile(r"\b[a-z][a-z0-9_.-]*\.v[0-9]+\b")
SCHEMA_CANDIDATE = re.compile(r"\b(?:opscat|p[0-9]{3})[a-z0-9_.-]*\.v[a-z0-9_-]+\b", re.IGNORECASE)
UNBOUNDED_CLAIM = re.compile(r"\b(?:production[- ]ready|fully autonomous|zero risk|safe for production|operator replacement complete)\b", re.IGNORECASE)
BOUNDED_TERMS = ("not ", "does not", "no claim", "local", "fixture", "planned", "blocked", "disabled")
REQUIRED_CLAIMS = {
    Path("README.md"): ("Public limitation:", "docs/limitations.md", "opscat demo"),
    Path("CONTRIBUTING.md"): ("Capability claims must link", "production autonomy", "P122 security"),
    Path("SECURITY.md"): ("not a production security boundary", "Do not submit secrets", "production credentials"),
    Path("CHANGELOG.md"): ("Unreleased", "local/mock release evidence"),
    Path("docs/release-notes-0.2.0.md"): ("bounded P115-P122", "open-source alpha", "Production autonomy"),
    Path("docs/security-threat-model.md"): ("local and non-production", "scripts/run_p122_security_gate.py", "uv.lock"),
    Path("docs/threat-model.md"): ("must not claim real production safety", "Auth remains deferred"),
    Path("docs/supply-chain.md"): ("CycloneDX", "uv.lock", "scripts/run_p122_vulnerability_audit.py"),
    Path("docs/performance.md"): ("p122.performance_soak.v2", "release_stage_crash_replay", "authority rejection"),
    Path("docs/migration.md"): ("p122.migration_compatibility.v1", "P121_AUTHORITY_COUNTER_KEYS", "exact key set"),
    Path("docs/install.md"): ("config/opscat.local.example.json", "production_mutation_enabled"),
    Path("docs/quickstart.md"): ("opscat demo", "opscat.local_demo.v1"),
    Path("docs/operations/p122-verification-handoff.md"): ("p122.docs_verification.v1", "p122.migration_compatibility.v1", "current status"),
    Path("docs/operations/p122-final-summary.md"): ("p122.performance_soak.v2", "p122.docs_verification.v1"),
    Path("docs/tickets/p122/README.md"): ("p122.performance_soak.v2", "p122.migration_compatibility.v1"),
}
EXAMPLE_REQUIRED_DOCS = (*CORE_DOCS, Path("README.md"), Path("CONTRIBUTING.md"), Path("docs/supply-chain.md"))


def verify_docs(*, root: Path = ROOT) -> dict[str, Any]:
    broken_links: list[str] = []
    missing_troubleshooting: list[str] = []
    missing_schema: list[str] = []
    missing_examples: list[str] = []
    invalid_json_examples: list[str] = []
    stale_script_examples: list[str] = []
    malformed_schema_references: list[str] = []
    unbounded_claims: list[str] = []
    missing_required_claims: list[str] = []
    document_hashes: dict[str, str] = {}
    schema_markers: dict[str, list[str]] = {}
    link_checked_docs: list[str] = []
    claim_checked_docs: list[str] = []
    schema_checked_docs: list[str] = []
    example_checked_docs: list[str] = []
    for doc in DOCS:
        path = root / doc
        text = path.read_text(encoding="utf-8")
        document_hashes[str(doc)] = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
        schema_markers[str(doc)] = sorted(set(SCHEMA_REF.findall(text)))
        link_checked_docs.append(str(doc))
        claim_checked_docs.append(str(doc))
        schema_checked_docs.append(str(doc))
        example_checked_docs.append(str(doc))
        for link in LOCAL_LINK.findall(text):
            target = link.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                broken_links.append(f"{doc}:{link}:outside_repo")
                continue
            if not resolved.exists():
                broken_links.append(f"{doc}:{link}:missing")
        for candidate in SCHEMA_CANDIDATE.findall(text):
            if SCHEMA_REF.fullmatch(candidate) is None:
                malformed_schema_references.append(f"{doc}:{candidate}")
        for ordinal, example in enumerate(JSON_BLOCK.findall(text), start=1):
            try:
                json.loads(example)
            except json.JSONDecodeError:
                invalid_json_examples.append(f"{doc}:json-block-{ordinal}")
        for block in SHELL_BLOCK.findall(text):
            for script in SCRIPT_COMMAND.findall(block):
                if not (root / script).is_file():
                    stale_script_examples.append(f"{doc}:{script}")
        for line_no, line in enumerate(text.splitlines(), start=1):
            lowered_line = line.lower()
            if UNBOUNDED_CLAIM.search(line) and not any(term in lowered_line for term in BOUNDED_TERMS):
                unbounded_claims.append(f"{doc}:{line_no}:{line.strip()}")
        if doc in CORE_DOCS:
            lowered = text.lower()
            if "troubleshooting" not in lowered:
                missing_troubleshooting.append(str(doc))
            if not schema_markers[str(doc)]:
                missing_schema.append(str(doc))
        if doc in EXAMPLE_REQUIRED_DOCS and "```" not in text:
            missing_examples.append(str(doc))
        for claim in REQUIRED_CLAIMS.get(doc, ()):
            if claim.lower() not in text.lower():
                missing_required_claims.append(f"{doc}:{claim}")
    report: dict[str, Any] = {
        "schema_version": "p122.docs_verification.v1",
        "checked_docs": [str(path) for path in DOCS],
        "core_docs": [str(path) for path in CORE_DOCS],
        "document_hashes": document_hashes,
        "schema_markers": schema_markers,
        "link_checked_docs": link_checked_docs,
        "claim_checked_docs": claim_checked_docs,
        "schema_checked_docs": schema_checked_docs,
        "example_checked_docs": example_checked_docs,
        "broken_links": broken_links,
        "missing_troubleshooting": missing_troubleshooting,
        "missing_schema": missing_schema,
        "missing_examples": missing_examples,
        "invalid_json_examples": invalid_json_examples,
        "stale_script_examples": stale_script_examples,
        "malformed_schema_references": malformed_schema_references,
        "unbounded_claims": unbounded_claims,
        "missing_required_claims": missing_required_claims,
    }
    report["valid"] = not any(
        (
            broken_links,
            missing_troubleshooting,
            missing_schema,
            missing_examples,
            invalid_json_examples,
            stale_script_examples,
            malformed_schema_references,
            unbounded_claims,
            missing_required_claims,
        )
    )
    report["report_hash"] = stable_hash(report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = verify_docs()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"valid": report["valid"], "report_hash": report["report_hash"]}, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
