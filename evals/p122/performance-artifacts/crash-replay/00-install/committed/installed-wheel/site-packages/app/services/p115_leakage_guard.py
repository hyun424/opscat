"""Fail-closed leakage scanner for P115 candidate-visible artifacts."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from app.services.p110_evaluation import stable_hash

_FORBIDDEN_KEYS = frozenset(
    {
        "answer",
        "answer_key",
        "expected_action",
        "expected_fault",
        "expected_label",
        "expected_root_cause",
        "fault_type",
        "ground_truth",
        "hidden_outcome",
        "oracle",
        "provider_reasoning",
        "root_cause",
        "root_service",
        "scorer_only_truth",
        "truth",
        "truth_hash",
    }
)
_FORBIDDEN_PATH_TOKENS = frozenset({"answer", "ground_truth", "hidden_outcome", "labels", "oracle", "scorer_truth"})
_FORBIDDEN_TEXT_PATTERNS = (
    re.compile(r"\b(?:ground[ _-]?truth|hidden[ _-]?outcome|answer[ _-]?key|scorer[ _-]?only)\b", re.I),
    re.compile(r"\b(?:api[_ -]?key|access[_ -]?token|secret|password)\b\s*[:=]", re.I),
    re.compile(r"\b(?:kubectl|ansible-playbook|terraform apply|sudo|rm -rf|DROP TABLE)\b", re.I),
    re.compile(r"\b(?:production|prod)\s*(?:cluster|namespace|account|database|target)\b", re.I),
)


class P115LeakageError(ValueError):
    """Raised when hidden outcomes or executable authority leak."""


@dataclass(frozen=True)
class P115LeakageReport:
    clean: bool
    findings: tuple[Mapping[str, str], ...]
    report_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "p115.leakage_report.v1",
            "clean": self.clean,
            "finding_count": len(self.findings),
            "findings": [dict(item) for item in self.findings],
            "report_hash": self.report_hash,
        }


def scan_candidate_visible_artifact(value: Any, *, artifact_path: str = "candidate.json") -> P115LeakageReport:
    findings: list[dict[str, str]] = []
    _scan_artifact_path(artifact_path, findings)
    _scan(value, "$", findings)
    ordered = tuple(sorted(findings, key=lambda item: (item["path"], item["code"], item["detail"])))
    payload = {"schema_version": "p115.leakage_report.v1", "clean": not ordered, "finding_count": len(ordered), "findings": list(ordered)}
    return P115LeakageReport(not ordered, ordered, stable_hash(payload))


def require_leakage_free(value: Any, *, artifact_path: str = "candidate.json") -> P115LeakageReport:
    report = scan_candidate_visible_artifact(value, artifact_path=artifact_path)
    if not report.clean:
        first = report.findings[0]
        raise P115LeakageError(f"{first['code']}:{first['path']}")
    return report


def _scan_artifact_path(path: str, findings: list[dict[str, str]]) -> None:
    for part in PurePosixPath(path.replace("\\", "/")).parts:
        normalized = _normalize(part.rsplit(".", 1)[0])
        if normalized in _FORBIDDEN_PATH_TOKENS:
            findings.append({"code": "filename_outcome_leak", "path": path, "detail": part})


def _scan(value: Any, path: str, findings: list[dict[str, str]]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            normalized = _normalize(key_text)
            child_path = f"{path}.{key_text}"
            if normalized in _FORBIDDEN_KEYS:
                findings.append({"code": "hidden_outcome_key", "path": child_path, "detail": key_text})
            if normalized in {"command", "commands", "shell", "script", "argv", "credential", "credentials"}:
                findings.append({"code": "authority_or_credential_field", "path": child_path, "detail": key_text})
            _scan(item, child_path, findings)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _scan(item, f"{path}[{index}]", findings)
    elif isinstance(value, str):
        for pattern in _FORBIDDEN_TEXT_PATTERNS:
            match = pattern.search(value)
            if match:
                findings.append({"code": "forbidden_text_leak", "path": path, "detail": match.group(0)})


def _normalize(value: Any) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value))
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")


__all__ = ["P115LeakageError", "P115LeakageReport", "require_leakage_free", "scan_candidate_visible_artifact"]
