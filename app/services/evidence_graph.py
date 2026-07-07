"""P9 deterministic evidence graph for incident command."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.models import Incident
from app.services.redaction import redact_text, redact_value
from app.services.root_cause_service import RootCauseCandidate, generate_root_cause_candidates


@dataclass(frozen=True)
class EvidenceGraph:
    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, str], ...]
    summary: dict[str, Any]
    local_mock_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [dict(node) for node in self.nodes], "edges": [dict(edge) for edge in self.edges], "summary": dict(self.summary), "local_mock_only": self.local_mock_only}


def build_evidence_graph(incident: Incident | Mapping[str, Any], *, plan: Any | None = None, verification: Any | None = None, learning: Any | None = None) -> EvidenceGraph:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    incident_id = str(_get(incident, "id", "incident"))
    nodes.append(
        _node(
            f"incident:{incident_id}",
            "incident",
            f"Incident {incident_id}",
            str(_get(incident, "status", "unknown")),
            {"service": _get(incident, "service", "unknown"), "severity": _get(incident, "severity", "unknown")},
        )
    )

    evidence = _evidence(incident)
    for index, item in enumerate(evidence, start=1):
        evidence_id = str(_get(item, "id", f"evidence-{index}"))
        nodes.append(_node(f"evidence:{evidence_id}", "evidence", str(_get(item, "type", "evidence")), "observed", {"content": _get(item, "content", "")}))
        edges.append(_edge(f"evidence:{evidence_id}", f"incident:{incident_id}", "observes"))

    candidates = _candidates(incident, evidence)
    for index, candidate in enumerate(candidates[:3], start=1):
        hypothesis_id = f"hypothesis:{index}"
        nodes.append(
            _node(
                hypothesis_id,
                "hypothesis",
                candidate.hypothesis,
                "supported" if candidate.evidence else "needs_evidence",
                {"confidence": candidate.confidence, "missing_evidence": list(candidate.missing_evidence)},
            )
        )
        edges.append(_edge(hypothesis_id, f"incident:{incident_id}", "explains"))
        for evidence_id in candidate.evidence:
            edges.append(_edge(f"evidence:{evidence_id}", hypothesis_id, "supports"))
        for evidence_id in candidate.counter_evidence:
            edges.append(_edge(f"evidence:{evidence_id}", hypothesis_id, "counters"))

    plan_dict = _to_dict(plan)
    for step in _as_list(plan_dict.get("steps", [])):
        row = dict(step) if isinstance(step, Mapping) else {}
        step_id = str(row.get("id", "step"))
        node_id = f"plan_step:{step_id}"
        nodes.append(_node(node_id, "plan_step", str(row.get("goal", step_id)), str(row.get("type", "unknown")), {"risk": row.get("risk"), "requires_human": row.get("requires_human")}))
        edges.append(_edge(node_id, f"incident:{incident_id}", "responds_to"))
        for evidence_id in _as_list(row.get("required_evidence", [])):
            if str(evidence_id).startswith("evidence") or any(str(evidence_id) == str(_get(item, "id", "")) for item in evidence):
                edges.append(_edge(f"evidence:{evidence_id}", node_id, "required_by"))

    verification_dict = _to_dict(verification)
    if verification_dict:
        nodes.append(_node("verification:latest", "verification", "Recovery verification", str(verification_dict.get("status", "unknown")), {"route": verification_dict.get("route")}))
        edges.append(_edge("verification:latest", f"incident:{incident_id}", "verifies"))

    learning_dict = _to_dict(learning)
    if learning_dict:
        nodes.append(_node("memory:learning", "memory", "Prior outcome signal", str(learning_dict.get("route", "unknown")), {"warnings": learning_dict.get("warnings", [])}))
        edges.append(_edge("memory:learning", f"incident:{incident_id}", "informs"))

    ordered_nodes = tuple(sorted(nodes, key=lambda node: (str(node["type"]), str(node["id"]))))
    ordered_edges = tuple(sorted(_dedupe_edges(edges), key=lambda edge: (edge["source"], edge["relationship"], edge["target"])))
    summary = {"node_count": len(ordered_nodes), "edge_count": len(ordered_edges), "node_types": sorted({str(node["type"]) for node in ordered_nodes})}
    return EvidenceGraph(nodes=ordered_nodes, edges=ordered_edges, summary=summary)


def _node(node_id: str, node_type: str, label: str, status: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": node_id, "type": node_type, "label": redact_text(label), "status": redact_text(status), "metadata": redact_value(dict(metadata))}


def _edge(source: str, target: str, relationship: str) -> dict[str, str]:
    return {"source": source, "target": target, "relationship": relationship}


def _dedupe_edges(edges: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, str]] = []
    for edge in edges:
        key = (edge["source"], edge["target"], edge["relationship"])
        if key not in seen:
            seen.add(key)
            result.append(edge)
    return result


def _candidates(incident: Incident | Mapping[str, Any], evidence: list[Any]) -> list[RootCauseCandidate]:
    if isinstance(incident, Incident):
        try:
            return generate_root_cause_candidates(incident, list(incident.evidence))
        except Exception:
            return []
    evidence_ids = tuple(str(_get(item, "id", f"evidence-{index}")) for index, item in enumerate(evidence, start=1))
    return [RootCauseCandidate(hypothesis=redact_text(str(_get(incident, "root_cause_candidate", "Unknown cause"))), confidence=float(_get(incident, "confidence", 0.0) or 0.0), evidence=evidence_ids)]


def _evidence(incident: Incident | Mapping[str, Any]) -> list[Any]:
    value = _get(incident, "evidence", [])
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    method = getattr(value, "to_dict", None)
    if callable(method):
        result = method()
        if isinstance(result, Mapping):
            return dict(result)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)
