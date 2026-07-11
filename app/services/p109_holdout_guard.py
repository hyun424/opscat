"""P109 holdout split and duplicate guard.

The guard is deterministic and data-only: it inspects caller-supplied rows,
never fetches data, and never executes remediation authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

HOLDOUT_GUARD_SCHEMA_VERSION = "p109.holdout_guard.v1"
AUTHORED_SOURCE_KINDS = frozenset({"authored_fixture", "fixture", "smoke_fixture", "synthetic_fixture"})
FIXTURE_SOURCE_ID_RE = re.compile(r"(?:^|[-_:/.])(fixture|synthetic|smoke|test)(?:$|[-_:/.])", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def evaluate_p109_holdout_guard(
    rows: Sequence[Mapping[str, Any]],
    *,
    cutoff_at: str,
    allowed_source_ids: Sequence[str] | None = None,
    near_duplicate_threshold: float = 0.8,
) -> dict[str, Any]:
    canonical_rows = sorted((_canonical_row(row) for row in rows), key=lambda item: item["row_id"])
    train_rows = [row for row in canonical_rows if row["split"] == "train"]
    holdout_rows = [row for row in canonical_rows if row["split"] == "holdout"]
    train_groups = {row["group_id"] for row in train_rows}
    holdout_groups = {row["group_id"] for row in holdout_rows}
    overlap_group_ids = sorted(train_groups & holdout_groups)
    time_violations = _time_split_violations(canonical_rows, cutoff_at=cutoff_at)
    exact_duplicates, near_duplicates = _duplicates(train_rows, holdout_rows, near_duplicate_threshold=near_duplicate_threshold)
    source_kind_counts = dict(sorted(Counter(row["source_kind"] for row in canonical_rows).items()))
    source_id_counts = dict(sorted(Counter(row["source_id"] for row in canonical_rows).items()))
    allowed_source_id_set = set(allowed_source_ids or ())
    missing_source_ids = sorted(row["row_id"] for row in canonical_rows if not row["source_id"])
    missing_provenance = sorted(row["row_id"] for row in canonical_rows if not row["provenance_hash"])
    disallowed_source_ids = sorted({row["source_id"] for row in canonical_rows if allowed_source_id_set and row["source_id"] not in allowed_source_id_set})
    fixture_source_ids = sorted({row["source_id"] for row in canonical_rows if _is_fixture_source_id(row["source_id"])})
    authored_fixture_present = any(kind in AUTHORED_SOURCE_KINDS for kind in source_kind_counts)

    reasons: list[str] = []
    if not train_rows:
        reasons.append("train split is empty")
    if not holdout_rows:
        reasons.append("holdout split is empty")
    if overlap_group_ids:
        reasons.append("group split overlaps holdout and train")
    if time_violations:
        reasons.append("time split violates cutoff")
    if exact_duplicates:
        reasons.append("exact duplicate evidence crosses train/holdout")
    if near_duplicates:
        reasons.append("near duplicate evidence crosses train/holdout")
    if missing_source_ids:
        reasons.append("source_id is required for every holdout row")
    if missing_provenance:
        reasons.append("provenance_hash is required for every holdout row")
    if disallowed_source_ids:
        reasons.append("source_id outside allowed provenance manifest")
    if authored_fixture_present or fixture_source_ids:
        reasons.append("authored fixtures or fixture-like source IDs cannot qualify for real release")

    core = {
        "schema_version": HOLDOUT_GUARD_SCHEMA_VERSION,
        "accepted": not reasons,
        "release_eligible": not reasons and not authored_fixture_present,
        "cutoff_at": cutoff_at,
        "row_count": len(canonical_rows),
        "split_counts": {"holdout": len(holdout_rows), "train": len(train_rows)},
        "group_split": {
            "train_group_ids": sorted(train_groups),
            "holdout_group_ids": sorted(holdout_groups),
            "overlap_group_ids": overlap_group_ids,
        },
        "time_split": {"cutoff_at": cutoff_at, "violations": time_violations},
        "duplicate_detection": {
            "near_duplicate_threshold": near_duplicate_threshold,
            "exact_duplicates": exact_duplicates,
            "near_duplicates": near_duplicates,
        },
        "source_provenance": {
            "allowed_source_ids": sorted(allowed_source_id_set),
            "source_id_counts": source_id_counts,
            "missing_source_row_ids": missing_source_ids,
            "missing_provenance_row_ids": missing_provenance,
            "disallowed_source_ids": disallowed_source_ids,
            "fixture_source_ids": fixture_source_ids,
        },
        "source_kind_counts": source_kind_counts,
        "authored_fixture_present": authored_fixture_present or bool(fixture_source_ids),
        "reasons": reasons,
    }
    return {**core, "holdout_report_hash": stable_hash(core)}


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def render_p109_holdout_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# P109 Holdout Guard",
        "",
        f"- Accepted: `{str(report.get('accepted') is True).lower()}`",
        f"- Release eligible: `{str(report.get('release_eligible') is True).lower()}`",
        f"- Holdout report hash: `{report.get('holdout_report_hash')}`",
        f"- Cutoff: `{report.get('cutoff_at')}`",
        "",
        "## Split",
        f"- Train rows: `{_nested(report, 'split_counts', 'train')}`",
        f"- Holdout rows: `{_nested(report, 'split_counts', 'holdout')}`",
        f"- Overlap groups: `{', '.join(_nested(report, 'group_split', 'overlap_group_ids') or [])}`",
        "",
        "## Duplicate Detection",
        f"- Exact duplicates: `{len(_nested(report, 'duplicate_detection', 'exact_duplicates') or [])}`",
        f"- Near duplicates: `{len(_nested(report, 'duplicate_detection', 'near_duplicates') or [])}`",
    ]
    reasons = report.get("reasons")
    if isinstance(reasons, Sequence) and not isinstance(reasons, (str, bytes)) and reasons:
        lines.extend(["", "## Reasons"])
        lines.extend(f"- {reason}" for reason in reasons)
    return "\n".join(lines) + "\n"


def write_p109_holdout_outputs(report: Mapping[str, Any], *, output_json: str | Path, output_md: str | Path) -> None:
    Path(output_json).write_text(stable_json(report), encoding="utf-8")
    Path(output_md).write_text(render_p109_holdout_markdown(report), encoding="utf-8")


def _canonical_row(row: Mapping[str, Any]) -> dict[str, str]:
    return {
        "row_id": _required_text(row, "row_id"),
        "split": _required_text(row, "split"),
        "group_id": _required_text(row, "group_id"),
        "observed_at": _required_text(row, "observed_at"),
        "evidence_text": _required_text(row, "evidence_text"),
        "source_id": _optional_text(row, "source_id"),
        "provenance_hash": _optional_text(row, "provenance_hash"),
        "source_kind": str(row.get("source_kind") or "real_import"),
    }


def _required_text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"P109 holdout row missing {key}")
    return value.strip()


def _optional_text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _is_fixture_source_id(source_id: str) -> bool:
    return bool(source_id and FIXTURE_SOURCE_ID_RE.search(source_id))


def _time_split_violations(rows: Sequence[Mapping[str, str]], *, cutoff_at: str) -> list[dict[str, str]]:
    cutoff = _parse_utc(cutoff_at)
    violations: list[dict[str, str]] = []
    for row in rows:
        observed = _parse_utc(row["observed_at"])
        if row["split"] == "train" and observed.timestamp() > cutoff.timestamp():
            violations.append({"row_id": row["row_id"], "split": row["split"], "observed_at": row["observed_at"]})
        if row["split"] == "holdout" and observed.timestamp() <= cutoff.timestamp():
            violations.append({"row_id": row["row_id"], "split": row["split"], "observed_at": row["observed_at"]})
    return sorted(violations, key=lambda item: (item["row_id"], item["split"], item["observed_at"]))


def _duplicates(
    train_rows: Sequence[Mapping[str, str]],
    holdout_rows: Sequence[Mapping[str, str]],
    *,
    near_duplicate_threshold: float,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    exact: list[dict[str, str]] = []
    near: list[dict[str, Any]] = []
    for train in train_rows:
        train_norm = _normalize_text(train["evidence_text"])
        train_tokens = set(_TOKEN_RE.findall(train_norm))
        for holdout in holdout_rows:
            holdout_norm = _normalize_text(holdout["evidence_text"])
            if train_norm == holdout_norm:
                exact.append({"train_row_id": train["row_id"], "holdout_row_id": holdout["row_id"]})
                continue
            holdout_tokens = set(_TOKEN_RE.findall(holdout_norm))
            similarity = _jaccard(train_tokens, holdout_tokens)
            if similarity >= near_duplicate_threshold:
                near.append(
                    {
                        "train_row_id": train["row_id"],
                        "holdout_row_id": holdout["row_id"],
                        "similarity": round(similarity, 6),
                    }
                )
    return (
        sorted(exact, key=lambda item: (item["train_row_id"], item["holdout_row_id"])),
        sorted(near, key=lambda item: (item["train_row_id"], item["holdout_row_id"])),
    )


def _normalize_text(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.lower()))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _parse_utc(value: str) -> datetime:
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include UTC offset")
    return parsed


def _nested(report: Mapping[str, Any], section: str, key: str) -> Any:
    value = report.get(section)
    return value.get(key) if isinstance(value, Mapping) else None
