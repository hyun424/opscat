from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, cast

import pytest

from app.services.p114_adjudicator import (
    NvidiaP114AdjudicatorProvider,
    P114AdjudicationError,
    build_p114_adjudication_packet,
    replay_p114_adjudication,
    run_p114_adjudication,
)
from app.services.p114_hypothesis_lattice import build_p114_hypothesis_lattice


def _candidate() -> dict[str, object]:
    node = {
        "node_id": "ev-a",
        "modality": "metric",
        "subject": "payment",
        "signal": "cpu",
        "pre_value": 1.0,
        "post_value": 9.0,
        "delta": 8.0,
        "support": ["metric_increase"],
        "contradiction": [],
        "missing": [],
    }
    return {
        "schema_version": "p114.re2_candidate_packet.v1",
        "case_id": "case-a",
        "system": "test",
        "injection_timestamp": 1.0,
        "evidence_graph": {"nodes": [node], "edges": []},
        "source_integrity": {},
    }


def _packet() -> dict[str, object]:
    candidate = _candidate()
    return build_p114_adjudication_packet(candidate, build_p114_hypothesis_lattice(candidate))


class Provider:
    name = "fake"
    model_calls_enabled = False

    def __init__(self, response: Mapping[str, Any] | str | Exception) -> None:
        self.response = response

    def diagnose(self, packet: Mapping[str, Any], prompt: str) -> Mapping[str, Any] | str:
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _valid_raw(packet: dict[str, object]) -> dict[str, object]:
    hypotheses = cast(tuple[Mapping[str, Any], ...], packet["hypotheses"])
    hypothesis = next(
        item
        for item in hypotheses
        if item["hypothesis_id"] == packet["deterministic_fallback_hypothesis_id"]
    )
    return {
        "hypothesis_id": hypothesis["hypothesis_id"],
        "abstain": False,
    }


def test_valid_selection_is_limited_to_supplied_hypothesis_and_evidence() -> None:
    packet = _packet()
    result = run_p114_adjudication(packet, provider=Provider(_valid_raw(packet)))

    assert result["status"] == "valid"
    assert result["selection_source"] == "llm"
    assert result["selected_hypothesis_id"] == packet["deterministic_fallback_hypothesis_id"]
    assert result["action_contract_status"] == "disabled"
    assert result["executed_actions"] == []


@pytest.mark.parametrize(
    "raw, expected",
    [
        ({"hypothesis_id": "invented", "abstain": False}, "unknown_or_invalid_hypothesis_id"),
        ({"hypothesis_id": "", "abstain": True, "evidence_ids": ["invented"]}, "unknown_output_field:evidence_ids"),
        ({"hypothesis_id": "", "abstain": True, "action": "kubectl restart"}, "unknown_output_field:action"),
    ],
)
def test_invalid_output_fails_closed_to_deterministic_top_candidate(raw: Mapping[str, Any] | str, expected: str) -> None:
    packet = _packet()
    result = replay_p114_adjudication(packet, raw)

    assert result["status"] == "fail_closed"
    assert result["selection_source"] == "deterministic_fallback"
    assert expected in result["validation_errors"]
    assert result["selected_hypothesis_id"] == packet["deterministic_fallback_hypothesis_id"]


def test_provider_failure_and_replay_are_deterministic_and_never_enable_actions() -> None:
    packet = _packet()
    first = run_p114_adjudication(packet, provider=Provider(RuntimeError("offline")))
    replay = replay_p114_adjudication(packet, first["raw_response"])

    assert first["status"] == "fail_closed"
    assert first["result_hash"] == replay["result_hash"]
    assert first["executed_actions"] == replay["executed_actions"] == []


def test_packet_builder_rejects_lattice_drift() -> None:
    candidate = _candidate()
    lattice = build_p114_hypothesis_lattice(candidate)
    forged = copy.deepcopy(lattice)
    forged["ranked_services"] = ["attacker"]

    with pytest.raises(P114AdjudicationError, match="lattice_hash_mismatch"):
        build_p114_adjudication_packet(candidate, forged)


def test_nvidia_nano_provider_uses_bounded_official_family_profile() -> None:
    captured: dict[str, object] = {}

    class Completions:
        def create(self, **kwargs: object) -> object:
            captured.update(kwargs)
            message = type("Message", (), {"content": '{"abstain":true}'})()
            choice = type("Choice", (), {"message": message})()
            return type("Completion", (), {"choices": [choice]})()

    client = type(
        "Client",
        (),
        {"chat": type("Chat", (), {"completions": Completions()})()},
    )()
    provider = NvidiaP114AdjudicatorProvider(client=client)

    assert provider.diagnose({}, "prompt") == '{"abstain":true}'
    assert captured["model"] == "nvidia/nemotron-3-nano-30b-a3b"
    assert captured["max_tokens"] == 512
    assert captured["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert captured["stream"] is False


def test_prompt_blinds_deterministic_rank_and_raw_scores() -> None:
    from app.services.p114_adjudicator import build_p114_adjudication_prompt

    prompt = build_p114_adjudication_prompt(_packet())

    assert "deterministic_fallback_hypothesis_id" not in prompt
    assert '"score"' not in prompt
