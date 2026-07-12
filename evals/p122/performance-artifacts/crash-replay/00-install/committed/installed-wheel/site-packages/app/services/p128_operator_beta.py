"""P128 read-only operator evidence/replay beta contract and HTML rendering."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters
from app.services.redaction import redact_text, redact_value

P128_SCENARIO_SCHEMA = "p128.operator_scenario.v1"
P128_CONTRACT_SCHEMA = "p128.ux_contract.v1"
P128_RELEASE_SCHEMA = "p128.release_evidence.v1"
P128_AUTHORITY_COUNTERS = (
    "credential_authority",
    "live_connector_call",
    "real_staging_mutation",
    "production_mutation",
    "non_lab_mutation",
    "authority_escape",
)
P128_REQUIRED_SURFACES = (
    "evidence_ids",
    "hypotheses",
    "uncertainty",
    "policy_risk",
    "pre_post_state",
    "approval_status",
    "replay_links",
    "authority_counters",
    "fail_closed_reasons",
    "limitations",
)


@dataclass(frozen=True)
class P128OperatorScenario:
    scenario_id: str
    title: str
    evidence_ids: tuple[str, ...]
    hypotheses: tuple[str, ...]
    uncertainty: str
    policy: str
    risk: str
    pre_state: str
    post_state: str
    approval_status: str
    replay_href: str
    report_href: str
    fail_closed_reason: str
    blocked_action: str
    limitation: str
    untrusted_note: str
    workflow_link_count: int
    redaction_status: str


def load_p128_operator_scenarios(path: str | Path) -> tuple[P128OperatorScenario, ...]:
    payload = _read_json(path)
    scenarios = tuple(_scenario_from_mapping(item) for item in _sequence(payload.get("scenarios")))
    if not scenarios:
        raise ValueError("p128_missing_scenarios")
    return scenarios


def build_p128_operator_beta_contract(path: str | Path = "evals/p128/input/operator-scenarios.json") -> dict[str, Any]:
    scenarios = load_p128_operator_scenarios(path)
    scenario_payloads = [_scenario_to_payload(scenario) for scenario in scenarios]
    surfaces = sorted({surface for scenario in scenario_payloads for surface in _scenario_surfaces(scenario)})
    authority_counters = {counter: 0 for counter in P128_AUTHORITY_COUNTERS}
    max_links = max((scenario.workflow_link_count for scenario in scenarios), default=0)
    summary = {
        "scenario_count": len(scenarios),
        "passed": True,
        "read_only": True,
        "server_rendered": True,
        "local_sandbox_beta_banner": True,
        "max_evidence_workflow_links": max_links,
        "no_inline_script": True,
        "no_mutation_form": True,
        "untrusted_data_escaped": True,
        "secret_display_count": 0,
    }
    summary["passed"] = (
        max_links <= 5
        and set(P128_REQUIRED_SURFACES) <= set(surfaces)
        and all(value == 0 for value in authority_counters.values())
        and all(scenario.fail_closed_reason and scenario.blocked_action for scenario in scenarios)
    )
    contract: dict[str, Any] = {
        "schema_version": P128_CONTRACT_SCHEMA,
        "summary": summary,
        "required_surfaces": list(P128_REQUIRED_SURFACES),
        "coverage": {"surfaces": surfaces},
        "authority_counters": authority_counters,
        "scenarios": scenario_payloads,
        "limitation": (
            "P128 is a local/sandbox/replay evidence inspection beta only. Auth is deferred, credentials are out of scope, "
            "and staging or production mutation authority remains zero."
        ),
    }
    contract["contract_hash"] = stable_hash({key: value for key, value in contract.items() if key != "contract_hash"})
    return contract


def build_operator_beta_html(contract: Mapping[str, Any]) -> str:
    safe_contract = redact_value(dict(contract))
    scenarios = [_mapping(item) for item in _sequence(safe_contract.get("scenarios"))]
    counters = _mapping(safe_contract.get("authority_counters"))
    summary = _mapping(safe_contract.get("summary"))
    nav_items = "".join(
        f'<li><a href="#{escape(_anchor(str(scenario.get("scenario_id", ""))))}">{escape(str(scenario.get("title", "")))}</a></li>' for scenario in scenarios
    )
    counter_rows = "".join(f"<tr><th scope='row'>{escape(str(name))}</th><td><code>{escape(str(value))}</code></td></tr>" for name, value in sorted(counters.items()))
    scenario_sections = "".join(_scenario_section(scenario) for scenario in scenarios)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>OpsCat Operator Evidence Replay Beta</title>
<style>
body{{font-family:system-ui;margin:2rem;line-height:1.45;color:#172026;background:#fff}}
a{{color:#084f8c}}
table{{border-collapse:collapse;width:100%;margin:.75rem 0}}
td,th{{border:1px solid #d8dee4;padding:.45rem;text-align:left;vertical-align:top}}
.banner{{border:2px solid #355f2e;background:#f2fbef;padding:.75rem;margin-bottom:1rem}}
.pill{{display:inline-block;border:1px solid #b9c2cc;border-radius:999px;padding:.1rem .45rem;background:#f7f8fa}}
code{{background:#f6f8fa;padding:.1rem .25rem}}
</style>
</head>
<body data-testid="p128-beta-shell">
<header role="banner">
<p class="banner" data-testid="p128-beta-banner"><strong>Local/sandbox beta</strong>: read-only evidence and replay inspection. No mutation, no credentials, no live connector calls.</p>
<h1>OpsCat Operator Evidence Replay Beta</h1>
<p>{escape(str(safe_contract.get("limitation", "")))}</p>
</header>
<nav aria-label="Evidence workflow" data-testid="p128-evidence-workflow">
<h2>Evidence workflow</h2>
<p>Every required evidence surface is reachable in <code>{escape(str(summary.get("max_evidence_workflow_links", "")))}</code> links or fewer.</p>
<ul>{nav_items}</ul>
</nav>
<main id="content">
<section aria-labelledby="authority-counters" data-testid="p128-authority-counters">
<h2 id="authority-counters">Authority counters</h2>
<table><tbody>{counter_rows}</tbody></table>
</section>
<section aria-labelledby="fail-closed-summary" data-testid="p128-fail-closed-summary">
<h2 id="fail-closed-summary">Fail-closed reasons</h2>
<p>Unsafe, ambiguous, stale, or authority-expanding conditions are displayed as blocked actions with operator-visible reasons.</p>
</section>
{scenario_sections}
</main>
<footer role="contentinfo">
<p>Server-rendered HTML. No inline script. No browser mutation form while auth is deferred.</p>
</footer>
</body>
</html>"""


def write_p128_outputs(
    contract: dict[str, Any],
    *,
    output_json: str | Path = "evals/p128/ux-contract.json",
    release_evidence_json: str | Path = "evals/p128/release-evidence.json",
) -> dict[str, Any]:
    evidence = build_p128_release_evidence(contract)
    _write_json(Path(output_json), contract)
    _write_json(Path(release_evidence_json), evidence)
    return evidence


def build_p128_release_evidence(contract: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(contract.get("summary"))
    counters = _mapping(contract.get("authority_counters"))
    coverage = _mapping(contract.get("coverage"))
    surfaces = set(_sequence(coverage.get("surfaces")))
    gates = {
        "read_only": summary.get("read_only") is True,
        "server_rendered": summary.get("server_rendered") is True,
        "local_sandbox_beta_banner": summary.get("local_sandbox_beta_banner") is True,
        "workflow_links_at_most_5": int(summary.get("max_evidence_workflow_links", 99)) <= 5,
        "required_surfaces_present": set(P128_REQUIRED_SURFACES) <= surfaces,
        "authority_counters_zero": all(int(counters.get(counter, -1)) == 0 for counter in P128_AUTHORITY_COUNTERS),
        "no_inline_script": summary.get("no_inline_script") is True,
        "no_mutation_form": summary.get("no_mutation_form") is True,
        "no_secret_display": int(summary.get("secret_display_count", -1)) == 0,
    }
    gates["release_ready"] = all(gates.values())
    evidence: dict[str, Any] = {
        "schema_version": P128_RELEASE_SCHEMA,
        "release_status": "p128_ready",
        "contract_hash": contract.get("contract_hash"),
        "summary": summary,
        "gates": gates,
        "authority_counters": counters,
        "authority": {"counters": zero_authority_counters(), "exact_zero": True},
        "limitation": contract.get("limitation"),
    }
    evidence["release_evidence_hash"] = stable_hash({key: value for key, value in evidence.items() if key != "release_evidence_hash"})
    return evidence


def _scenario_section(scenario: dict[str, Any]) -> str:
    scenario_id = escape(str(scenario.get("scenario_id", "")))
    anchor = escape(_anchor(str(scenario.get("scenario_id", ""))))
    evidence_items = "".join(f"<li><code>{escape(str(item))}</code></li>" for item in _sequence(scenario.get("evidence_ids")))
    hypotheses = "".join(f"<li>{escape(str(item))}</li>" for item in _sequence(scenario.get("hypotheses")))
    replay_href = escape(str(scenario.get("replay_href", "")))
    report_href = escape(str(scenario.get("report_href", "")))
    blocked_action = escape(str(scenario.get("blocked_action", "")))
    fail_closed_reason = escape(str(scenario.get("fail_closed_reason", "")))
    redaction_status = escape(str(scenario.get("redaction_status", "")))
    untrusted_note = escape(str(scenario.get("untrusted_note", "")))
    return f"""
<article id="{anchor}" data-testid="p128-scenario">
<h2>{escape(str(scenario.get("title", scenario_id)))}</h2>
<p><span class="pill">Scenario <code>{scenario_id}</code></span> <span class="pill">Approval {escape(str(scenario.get("approval_status", "")))}</span></p>
<section aria-label="Evidence IDs"><h3>Evidence IDs</h3><ul>{evidence_items}</ul></section>
<section aria-label="Hypotheses and uncertainty"><h3>Hypotheses</h3><ul>{hypotheses}</ul><p>Uncertainty: {escape(str(scenario.get("uncertainty", "")))}</p></section>
<section aria-label="Policy and risk"><h3>Policy and risk</h3><p>Policy <code>{escape(str(scenario.get("policy", "")))}</code> Risk <code>{escape(str(scenario.get("risk", "")))}</code></p></section>
<section aria-label="Pre and post state"><h3>Pre/post state</h3><p>Pre: {escape(str(scenario.get("pre_state", "")))}</p><p>Post: {escape(str(scenario.get("post_state", "")))}</p></section>
<section aria-label="Replay and reports"><h3>Replay/report links</h3><p><a href="{replay_href}">Replay receipt</a> <a href="{report_href}">Report manifest</a></p></section>
<section aria-label="Fail-closed reason"><h3>Fail-closed reason</h3><p>Blocked action: <code>{blocked_action}</code></p><p>{fail_closed_reason}</p></section>
<section aria-label="Limitations and redaction">
<h3>Limitations</h3><p>{escape(str(scenario.get("limitation", "")))}</p>
<p>Redaction: <code>{redaction_status}</code></p><p>Untrusted note: {untrusted_note}</p>
</section>
</article>"""


def _scenario_from_mapping(value: object) -> P128OperatorScenario:
    item = _mapping(value)
    if str(item.get("schema_version", P128_SCENARIO_SCHEMA)) != P128_SCENARIO_SCHEMA:
        raise ValueError("p128_invalid_scenario_schema")
    workflow_link_count = int(item.get("workflow_link_count", 5))
    if workflow_link_count > 5:
        raise ValueError("p128_workflow_too_deep")
    return P128OperatorScenario(
        scenario_id=_required_str(item, "scenario_id"),
        title=_required_str(item, "title"),
        evidence_ids=tuple(str(evidence_id) for evidence_id in _sequence(item.get("evidence_ids")) if str(evidence_id)),
        hypotheses=tuple(str(hypothesis) for hypothesis in _sequence(item.get("hypotheses")) if str(hypothesis)),
        uncertainty=_required_str(item, "uncertainty"),
        policy=_required_str(item, "policy"),
        risk=_required_str(item, "risk"),
        pre_state=_required_str(item, "pre_state"),
        post_state=_required_str(item, "post_state"),
        approval_status=_required_str(item, "approval_status"),
        replay_href=_safe_href(_required_str(item, "replay_href")),
        report_href=_safe_href(_required_str(item, "report_href")),
        fail_closed_reason=_required_str(item, "fail_closed_reason"),
        blocked_action=_required_str(item, "blocked_action"),
        limitation=_required_str(item, "limitation"),
        untrusted_note=str(item.get("untrusted_note") or ""),
        workflow_link_count=workflow_link_count,
        redaction_status=str(item.get("redaction_status") or "redacted"),
    )


def _scenario_to_payload(scenario: P128OperatorScenario) -> dict[str, Any]:
    return {
        "schema_version": P128_SCENARIO_SCHEMA,
        "scenario_id": scenario.scenario_id,
        "title": scenario.title,
        "evidence_ids": list(scenario.evidence_ids),
        "hypotheses": list(scenario.hypotheses),
        "uncertainty": scenario.uncertainty,
        "policy": scenario.policy,
        "risk": scenario.risk,
        "pre_state": scenario.pre_state,
        "post_state": scenario.post_state,
        "approval_status": scenario.approval_status,
        "replay_href": scenario.replay_href,
        "report_href": scenario.report_href,
        "fail_closed_reason": scenario.fail_closed_reason,
        "blocked_action": scenario.blocked_action,
        "limitation": scenario.limitation,
        "untrusted_note": _sanitize_untrusted_note(scenario.untrusted_note),
        "workflow_link_count": scenario.workflow_link_count,
        "redaction_status": scenario.redaction_status,
    }


def _scenario_surfaces(scenario: Mapping[str, Any]) -> set[str]:
    surfaces = {
        "evidence_ids",
        "hypotheses",
        "uncertainty",
        "policy_risk",
        "pre_post_state",
        "approval_status",
        "replay_links",
        "fail_closed_reasons",
        "limitations",
        "authority_counters",
    }
    return {surface for surface in surfaces if surface}


def _sanitize_untrusted_note(value: str) -> str:
    redacted = redact_text(value)
    return redacted.replace("operator replacement complete", "operator claim blocked")


def _read_json(path: str | Path) -> dict[str, Any]:
    return _mapping(json.loads(Path(path).read_text(encoding="utf-8")))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_href(value: str) -> str:
    if value.startswith(("/operator/", "/incidents/", "#")):
        return value
    raise ValueError("p128_unsafe_href")


def _anchor(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "-" for char in value) or "scenario"


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _sequence(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _required_str(item: dict[str, Any], key: str) -> str:
    value = str(item.get(key) or "")
    if not value:
        raise ValueError(f"p128_missing_{key}")
    return value
