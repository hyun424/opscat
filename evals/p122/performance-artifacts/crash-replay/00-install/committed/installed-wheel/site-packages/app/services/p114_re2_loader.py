"""Multimodal RCAEval RE2 archive loader for P114."""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import math
import posixpath
import statistics
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from app.services.p114_acquisition import P114AcquisitionError, validate_re2_archive

CASE_SCHEMA_VERSION = "p114.re2_case.v1"
CANDIDATE_SCHEMA_VERSION = "p114.re2_candidate_packet.v1"
TRUTH_SCHEMA_VERSION = "p114.re2_scorer_truth.v1"
ALLOWED_FAULTS = frozenset({"cpu", "mem", "disk", "delay", "loss", "socket"})
REQUIRED_CASE_FILES = frozenset({"inject_time.txt", "simple_metrics.csv", "logts.csv", "cluster_info.json"})
IGNORED_CASE_FILES = frozenset(
    {
        "metrics.csv",
        "logs.csv",
        "metrics_postprocess.log",
        "pod-node-1.csv",
        "pod-node-2.csv",
        "traces.csv",
        "tracets_err.csv",
        "tracets_lat.csv",
    }
)
_CASE_ID_DOMAIN = "p114.re2.case-id.v1"
_NODE_ID_DOMAIN = "p114.re2.node-id.v1"
_EDGE_ID_DOMAIN = "p114.re2.edge-id.v1"
_MAX_REQUIRED_FILE_BYTES = 8 * 1024 * 1024


class P114RE2Error(ValueError):
    """Raised when an RE2 archive violates the P114 loader contract."""


@dataclass(frozen=True)
class P114EvidenceNode:
    node_id: str
    modality: str
    subject: str
    signal: str
    statistic: str
    pre_value: float
    post_value: float
    delta: float
    support: tuple[str, ...]
    contradiction: tuple[str, ...]
    missing: tuple[str, ...]
    source: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "modality": self.modality,
            "subject": self.subject,
            "signal": self.signal,
            "statistic": self.statistic,
            "pre_value": self.pre_value,
            "post_value": self.post_value,
            "delta": self.delta,
            "support": list(self.support),
            "contradiction": list(self.contradiction),
            "missing": list(self.missing),
            "source": dict(self.source),
        }


@dataclass(frozen=True)
class P114EvidenceEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation: str
    support: tuple[str, ...]
    contradiction: tuple[str, ...]
    missing: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "relation": self.relation,
            "support": list(self.support),
            "contradiction": list(self.contradiction),
            "missing": list(self.missing),
        }


@dataclass(frozen=True)
class P114RE2Case:
    case_id: str
    system: str
    inject_time: float
    official_source_hash: str
    raw_hashes: Mapping[str, str]
    scorer_only_truth: Mapping[str, Any]
    nodes: tuple[P114EvidenceNode, ...]
    edges: tuple[P114EvidenceEdge, ...]
    source_path: str
    schema_version: str = CASE_SCHEMA_VERSION

    def to_candidate_packet(self) -> dict[str, Any]:
        packet = {
            "schema_version": CANDIDATE_SCHEMA_VERSION,
            "case_id": self.case_id,
            "system": self.system,
            "injection_timestamp": self.inject_time,
            "evidence_graph": {
                "nodes": [node.to_dict() for node in self.nodes],
                "edges": [edge.to_dict() for edge in self.edges],
            },
            "source_integrity": _candidate_hashes(self.raw_hashes),
        }
        reject_candidate_truth_leak((packet,))
        return packet

    def to_scorer_truth(self) -> dict[str, Any]:
        return {
            "schema_version": TRUTH_SCHEMA_VERSION,
            "case_id": self.case_id,
            "scorer_only_truth": dict(self.scorer_only_truth),
            "official_source_hash": self.official_source_hash,
            "source_path": self.source_path,
            "evidence_node_ids": [node.node_id for node in self.nodes],
        }


def load_pinned_re2_cases(
    archive_path: str | Path,
    manifest_path: str | Path,
    *,
    hmac_key: bytes,
    max_cases: int | None = None,
) -> tuple[P114RE2Case, ...]:
    """Validate and load label-free RE2 evidence packets from a pinned archive."""

    if not hmac_key:
        raise P114RE2Error("hmac_key_required")
    archive = Path(archive_path)
    manifest_file = Path(manifest_path)
    try:
        source = validate_re2_archive(archive, manifest_file)
    except P114AcquisitionError as exc:
        raise P114RE2Error(str(exc)) from exc
    manifest = _read_manifest(manifest_file)
    system = str(manifest.get("system", source.get("source_id", "re2"))).strip()
    if not system:
        raise P114RE2Error("missing_manifest_system")
    source_hash = f"sha256:{source['sha256']}"
    with zipfile.ZipFile(archive) as zf:
        groups = _index_archive(zf)
        if len(groups) != int(source["case_count"]):
            raise P114RE2Error(f"case_count_mismatch:{len(groups)}")
        selected = sorted(groups.items())
        if max_cases is not None:
            if max_cases <= 0:
                raise P114RE2Error("invalid_max_cases")
            selected = selected[:max_cases]
        cases = [
            _read_case(
                zf,
                case_path,
                members,
                system=system,
                source_hash=source_hash,
                hmac_key=hmac_key,
            )
            for case_path, members in selected
        ]
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise P114RE2Error("duplicate_case_id")
    return tuple(cases)


def reject_candidate_truth_leak(packets: Sequence[Mapping[str, Any]]) -> None:
    rendered = json.dumps(list(packets), sort_keys=True, ensure_ascii=True, allow_nan=False, default=str).lower()
    forbidden = (
        "scorer_only",
        "root_service",
        "fault_type",
        "source_path",
        "case_group",
        "repetition",
        "inject_time.txt",
        "simple_metrics.csv",
        "logts.csv",
        "cluster_info.json",
        "metrics.csv",
        "logs.csv",
        "re2-ss/",
        "re2-ob/",
    )
    if any(token in rendered for token in forbidden):
        raise P114RE2Error("candidate_visible_truth_leak")


def _read_manifest(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise P114RE2Error("source_manifest_not_object")
    return value


def _candidate_hashes(raw_hashes: Mapping[str, str]) -> dict[str, str]:
    aliases = {
        "inject_time.txt": "time_anchor",
        "simple_metrics.csv": "metric_series",
        "logts.csv": "log_template_series",
        "cluster_info.json": "log_template_catalog",
    }
    return {aliases[key]: value for key, value in sorted(raw_hashes.items())}


def _index_archive(zf: zipfile.ZipFile) -> dict[str, dict[str, zipfile.ZipInfo]]:
    groups: dict[str, dict[str, zipfile.ZipInfo]] = {}
    seen_paths: set[str] = set()
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = _normalize_name(info.filename)
        if name in seen_paths:
            raise P114RE2Error("archive_duplicate_path")
        seen_paths.add(name)
        parts = name.split("/")
        if len(parts) < 4 or not parts[2].isdigit():
            continue
        if len(parts) != 4:
            raise P114RE2Error("invalid_case_file_layout")
        _root, group, repetition_text, file_name = parts
        service, fault = _parse_group(group)
        repetition = _parse_repetition(repetition_text)
        if file_name not in REQUIRED_CASE_FILES and file_name not in IGNORED_CASE_FILES:
            raise P114RE2Error(f"unexpected_case_file:{file_name}")
        case_path = f"{service}_{fault}/{repetition}"
        members = groups.setdefault(case_path, {})
        if file_name in members:
            raise P114RE2Error("duplicate_case_file")
        members[file_name] = info
    for case_path, members in groups.items():
        missing = REQUIRED_CASE_FILES - set(members)
        if missing:
            raise P114RE2Error(f"missing_case_file:{case_path}:{','.join(sorted(missing))}")
        for file_name in REQUIRED_CASE_FILES:
            if members[file_name].file_size > _MAX_REQUIRED_FILE_BYTES:
                raise P114RE2Error(f"required_file_too_large:{file_name}")
    return groups


def _read_case(
    zf: zipfile.ZipFile,
    case_path: str,
    members: Mapping[str, zipfile.ZipInfo],
    *,
    system: str,
    source_hash: str,
    hmac_key: bytes,
) -> P114RE2Case:
    group, repetition_text = case_path.split("/", 1)
    service, fault = _parse_group(group)
    repetition = _parse_repetition(repetition_text)
    raw = {name: zf.read(members[name]) for name in sorted(REQUIRED_CASE_FILES)}
    raw_hashes = {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()}
    inject_time = _parse_inject_time(raw["inject_time.txt"])
    case_id = _case_id(f"{system}:{case_path}", hmac_key=hmac_key)
    metric_nodes = _parse_metric_nodes(raw["simple_metrics.csv"], case_id=case_id, inject_time=inject_time)
    log_nodes = _parse_log_nodes(raw["logts.csv"], raw["cluster_info.json"], case_id=case_id, inject_time=inject_time)
    nodes = tuple(sorted((*metric_nodes, *log_nodes), key=lambda node: node.node_id))
    if not nodes:
        raise P114RE2Error("missing_evidence_nodes")
    edges = _build_edges(nodes, case_id=case_id)
    case = P114RE2Case(
        case_id=case_id,
        system=system,
        inject_time=inject_time,
        official_source_hash=source_hash,
        raw_hashes=raw_hashes,
        scorer_only_truth={"root_service": service, "fault_type": fault, "repetition": repetition},
        nodes=nodes,
        edges=edges,
        source_path=case_path,
    )
    reject_candidate_truth_leak((case.to_candidate_packet(),))
    return case


def _parse_metric_nodes(data: bytes, *, case_id: str, inject_time: float) -> tuple[P114EvidenceNode, ...]:
    rows = _csv_rows(data, required_first_column="time")
    headers = [header for header in rows.fieldnames or () if header != "time"]
    if not headers:
        raise P114RE2Error("missing_metric_columns")
    values: dict[str, dict[str, list[float]]] = {header: {"pre": [], "post": []} for header in headers}
    dropped = {header: 0 for header in headers}
    dropped_timestamp_rows = 0
    for row in rows:
        timestamp = _optional_timestamp(row.get("time"), "metric_time")
        if timestamp is None:
            dropped_timestamp_rows += 1
            continue
        window = "pre" if timestamp < inject_time else "post"
        for header in headers:
            cell = row.get(header)
            if cell is None or cell.strip() == "":
                continue
            number = _optional_finite_float(cell, f"metric_value:{header}")
            if number is None:
                dropped[header] += 1
                continue
            values[header][window].append(number)
    nodes: list[P114EvidenceNode] = []
    for header in sorted(headers):
        pre = values[header]["pre"]
        post = values[header]["post"]
        if not pre or not post:
            continue
        missing = ["nonfinite_samples"] if dropped[header] else []
        if dropped_timestamp_rows:
            missing.append("missing_timestamp_rows")
        pre_value = _round(statistics.fmean(pre))
        post_value = _round(statistics.fmean(post))
        delta = _round(post_value - pre_value)
        direction = _direction(delta)
        subject, signal = _split_signal(header)
        nodes.append(
            P114EvidenceNode(
                node_id=_node_id(case_id, f"metric:{header}"),
                modality="metric",
                subject=subject,
                signal=signal,
                statistic="post_minus_pre_mean",
                pre_value=pre_value,
                post_value=post_value,
                delta=delta,
                support=(f"metric_{direction}",) if direction != "flat" else (),
                contradiction=("no_metric_shift",) if direction == "flat" else (),
                missing=tuple(missing),
                source={
                    "source_token": "metrics",
                    "column_hash": _short_hash(header),
                    "sample_count": len(pre) + len(post),
                    "dropped_nonfinite_count": dropped[header],
                    "dropped_timestamp_row_count": dropped_timestamp_rows,
                },
            )
        )
    return tuple(nodes)


def _parse_log_nodes(data: bytes, cluster_info_data: bytes, *, case_id: str, inject_time: float) -> tuple[P114EvidenceNode, ...]:
    cluster_info = _cluster_info(cluster_info_data)
    rows = _csv_rows(data, required_first_column="time")
    headers = [header for header in rows.fieldnames or () if header != "time"]
    if not headers:
        raise P114RE2Error("missing_log_columns")
    values: dict[str, dict[str, list[float]]] = {header: {"pre": [], "post": []} for header in headers}
    dropped = {header: 0 for header in headers}
    dropped_timestamp_rows = 0
    for row in rows:
        timestamp = _optional_timestamp(row.get("time"), "log_time")
        if timestamp is None:
            dropped_timestamp_rows += 1
            continue
        window = "pre" if timestamp < inject_time else "post"
        for header in headers:
            cell = row.get(header)
            if cell is None or cell.strip() == "":
                continue
            number = _optional_finite_float(cell, f"log_value:{header}")
            if number is None:
                dropped[header] += 1
                continue
            values[header][window].append(number)
    nodes: list[P114EvidenceNode] = []
    for header in sorted(headers):
        template_id = _template_id(header)
        if template_id not in cluster_info:
            raise P114RE2Error(f"missing_cluster_info:{template_id}")
        pre = values[header]["pre"]
        post = values[header]["post"]
        if not pre or not post:
            continue
        missing = ["nonfinite_samples"] if dropped[header] else []
        if dropped_timestamp_rows:
            missing.append("missing_timestamp_rows")
        pre_value = _round(statistics.fmean(pre))
        post_value = _round(statistics.fmean(post))
        delta = _round(post_value - pre_value)
        direction = _direction(delta)
        info = cluster_info[template_id]
        containers = tuple(str(item) for item in info.get("container", ()) if str(item))
        subject = containers[0] if containers else _split_signal(header)[0]
        nodes.append(
            P114EvidenceNode(
                node_id=_node_id(case_id, f"log:{header}"),
                modality="log_template",
                subject=subject,
                signal=f"template_{template_id}",
                statistic="post_minus_pre_mean_count",
                pre_value=pre_value,
                post_value=post_value,
                delta=delta,
                support=(f"log_{direction}",) if direction != "flat" else (),
                contradiction=("no_log_shift",) if direction == "flat" else (),
                missing=tuple(missing),
                source={
                    "source_token": "logs",
                    "template_hash": _short_hash(str(info.get("template", ""))),
                    "sample_count": len(pre) + len(post),
                    "dropped_nonfinite_count": dropped[header],
                    "dropped_timestamp_row_count": dropped_timestamp_rows,
                },
            )
        )
    return tuple(nodes)


def _build_edges(nodes: Sequence[P114EvidenceNode], *, case_id: str) -> tuple[P114EvidenceEdge, ...]:
    edges: list[P114EvidenceEdge] = []
    for left_index, left in enumerate(nodes):
        for right in nodes[left_index + 1 :]:
            if left.subject != right.subject or left.modality == right.modality:
                continue
            left_direction = _direction(left.delta)
            right_direction = _direction(right.delta)
            relation = "support" if left_direction == right_direction and left_direction != "flat" else "contradiction"
            edges.append(
                P114EvidenceEdge(
                    edge_id=_edge_id(case_id, left.node_id, right.node_id, relation),
                    source_node_id=left.node_id,
                    target_node_id=right.node_id,
                    relation=relation,
                    support=("same_subject_same_direction",) if relation == "support" else (),
                    contradiction=("same_subject_different_direction",) if relation == "contradiction" else (),
                    missing=(),
                )
            )
    return tuple(sorted(edges, key=lambda edge: edge.edge_id))


def _csv_rows(data: bytes, *, required_first_column: str) -> csv.DictReader[str]:
    text = data.decode("utf-8")
    rows = csv.DictReader(StringIO(text))
    if not rows.fieldnames or rows.fieldnames[0] != required_first_column:
        raise P114RE2Error(f"malformed_csv:{required_first_column}")
    if len(rows.fieldnames) != len(set(rows.fieldnames)):
        raise P114RE2Error("duplicate_csv_column")
    return rows


def _cluster_info(data: bytes) -> Mapping[str, Mapping[str, Any]]:
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, Mapping):
        raise P114RE2Error("cluster_info_not_object")
    normalized: dict[str, Mapping[str, Any]] = {}
    for key, item in value.items():
        if not str(key).isdigit() or not isinstance(item, Mapping) or not isinstance(item.get("template"), str):
            raise P114RE2Error("malformed_cluster_info")
        container = item.get("container", ())
        if isinstance(container, str) or not isinstance(container, Sequence):
            raise P114RE2Error("malformed_cluster_info")
        normalized[str(key)] = item
    return normalized


def _parse_inject_time(data: bytes) -> float:
    value = _finite_float(data.decode("utf-8").strip(), "inject_time")
    if value <= 0:
        raise P114RE2Error("invalid_inject_time")
    return value


def _finite_float(value: Any, name: str) -> float:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise P114RE2Error(f"malformed_numeric:{name}") from exc
    if not math.isfinite(result):
        raise P114RE2Error(f"nonfinite_numeric:{name}")
    return result


def _optional_finite_float(value: Any, name: str) -> float | None:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise P114RE2Error(f"malformed_numeric:{name}") from exc
    return result if math.isfinite(result) else None


def _optional_timestamp(value: Any, name: str) -> float | None:
    if value is None or not str(value).strip():
        return None
    return _optional_finite_float(value, name)


def _normalize_name(name: str) -> str:
    raw = name.replace("\\", "/")
    if raw.startswith("/") or raw.startswith("../") or "/../" in raw:
        raise P114RE2Error("archive_traversal")
    normalized = posixpath.normpath(raw)
    if normalized.startswith("../") or normalized in {".", ".."} or posixpath.isabs(normalized):
        raise P114RE2Error("archive_traversal")
    return normalized


def _parse_group(group: str) -> tuple[str, str]:
    service, separator, fault = group.rpartition("_")
    if not separator or not service or fault not in ALLOWED_FAULTS:
        raise P114RE2Error("invalid_case_identity")
    return service, fault


def _parse_repetition(value: str) -> int:
    if not value.isdigit() or int(value) <= 0:
        raise P114RE2Error("invalid_repetition")
    return int(value)


def _template_id(header: str) -> str:
    _prefix, separator, template_id = header.rpartition("_")
    if not separator or not template_id.isdigit():
        raise P114RE2Error("invalid_log_template_column")
    return template_id


def _split_signal(name: str) -> tuple[str, str]:
    subject, separator, signal = name.rpartition("_")
    if not separator:
        return "global", name
    return subject, signal


def _case_id(value: str, *, hmac_key: bytes) -> str:
    digest = hmac.new(hmac_key, f"{_CASE_ID_DOMAIN}:{value}".encode(), hashlib.sha256).hexdigest()
    return f"p114_{digest[:24]}"


def _node_id(case_id: str, value: str) -> str:
    return "ev_" + hashlib.sha256(f"{_NODE_ID_DOMAIN}:{case_id}:{value}".encode()).hexdigest()[:24]


def _edge_id(case_id: str, left: str, right: str, relation: str) -> str:
    return "edge_" + hashlib.sha256(f"{_EDGE_ID_DOMAIN}:{case_id}:{left}:{right}:{relation}".encode()).hexdigest()[:24]


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _direction(delta: float) -> str:
    if abs(delta) <= 1e-12:
        return "flat"
    return "increase" if delta > 0 else "decrease"


def _round(value: float) -> float:
    return round(value, 12)
