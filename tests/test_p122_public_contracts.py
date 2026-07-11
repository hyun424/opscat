from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from app.plugin_sdk import MutationDenied, validate_read_only_connector
from app.public_contracts import REQUIRED_PUBLIC_CONTRACTS, public_contract_manifest


class FixtureConnector:
    connector_id = "fixture-v1"

    def collect(self, query: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
        return [{"query": query, "source": "fixture"}]


class UnsafeConnector(FixtureConnector):
    def write(self) -> None:
        return None


def test_public_contracts_have_stability_compatibility_docs_tests_and_zero_nonlocal_authority() -> None:
    manifest = public_contract_manifest()
    assert manifest["schema_version"] == "opscat.public_contracts.v1"
    assert manifest["required_contracts"] == REQUIRED_PUBLIC_CONTRACTS
    assert {contract["name"]: contract["category"] for contract in manifest["contracts"]} == REQUIRED_PUBLIC_CONTRACTS
    assert set(REQUIRED_PUBLIC_CONTRACTS) >= {
        "configuration",
        "policy-packs",
        "incident",
        "evidence",
        "approval",
        "validation",
        "rollback",
        "learning",
        "replay",
        "observability",
        "frozen-eval",
    }
    for contract in manifest["contracts"]:
        assert contract["name"] in REQUIRED_PUBLIC_CONTRACTS
        assert contract["category"] == REQUIRED_PUBLIC_CONTRACTS[contract["name"]]
        assert contract["stability"] and contract["backward_compatibility"] and contract["deprecation"]
        assert contract["test_ref"] and contract["doc_ref"] and contract["release_evidence_ref"]
        assert contract["nonlocal_authority_allowed"] is False
        assert importlib.util.find_spec(contract["owner_module"]) is not None
        owner = importlib.import_module(contract["owner_module"])
        owned_interface = getattr(owner, contract["owner_symbol"])
        assert callable(owned_interface) or isinstance(owned_interface, str)
        if isinstance(owned_interface, str) and contract["interface_ref"].startswith("p"):
            assert contract["interface_ref"].startswith(owned_interface)
        assert Path(contract["test_ref"]).is_file()
        assert Path(contract["doc_ref"]).is_file()


def test_connector_sdk_accepts_read_only_and_denies_mutation_surface() -> None:
    validate_read_only_connector(FixtureConnector())
    with pytest.raises(MutationDenied):
        validate_read_only_connector(UnsafeConnector())
