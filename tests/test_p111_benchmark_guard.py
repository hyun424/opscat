from __future__ import annotations

import pytest

from app.services.p111_benchmark_guard import (
    P111BenchmarkGuardError,
    benchmark_role,
    create_freeze_manifest,
    validate_frozen_run,
)


def _packets() -> list[dict[str, object]]:
    return [{"case_id": "a", "evidence": []}, {"case_id": "b", "evidence": []}]


def _manifest() -> dict[str, object]:
    return create_freeze_manifest(
        selected_on_repetition=2,
        model="model",
        prompt_schema_version="p111.prompt.v1",
        decoding_config={"temperature": 0},
        implementation_hash="sha256:impl",
        official_source_hash="sha256:source",
        candidate_packets=_packets(),
    )


def test_roles_are_explicit() -> None:
    assert [benchmark_role(index) for index in range(1, 6)] == [
        "development", "validation", "blind", "reserve", "contaminated_baseline"
    ]


def test_manifest_allows_frozen_blind_run() -> None:
    role = validate_frozen_run(
        _manifest(),
        target_repetition=3,
        model="model",
        prompt_schema_version="p111.prompt.v1",
        decoding_config={"temperature": 0},
        implementation_hash="sha256:impl",
        official_source_hash="sha256:source",
        candidate_packets=_packets(),
    )
    assert role == "blind"


@pytest.mark.parametrize("selection", [3, 4, 5])
def test_protected_sets_cannot_select_configuration(selection: int) -> None:
    with pytest.raises(P111BenchmarkGuardError, match="selection_on_protected_role"):
        create_freeze_manifest(
            selected_on_repetition=selection,
            model="model",
            prompt_schema_version="prompt",
            decoding_config={},
            implementation_hash="impl",
            official_source_hash="sha256:source",
            candidate_packets=_packets(),
        )


def test_tampered_or_changed_configuration_fails_closed() -> None:
    manifest = _manifest()
    manifest["model"] = "changed"
    with pytest.raises(P111BenchmarkGuardError, match="freeze_manifest_tampered"):
        validate_frozen_run(
            manifest,
            target_repetition=3,
            model="changed",
            prompt_schema_version="p111.prompt.v1",
            decoding_config={"temperature": 0},
            implementation_hash="sha256:impl",
            official_source_hash="sha256:source",
            candidate_packets=_packets(),
        )


def test_reserve_requires_separate_promotion() -> None:
    with pytest.raises(P111BenchmarkGuardError, match="reserve_set"):
        validate_frozen_run(
            _manifest(),
            target_repetition=4,
            model="model",
            prompt_schema_version="p111.prompt.v1",
            decoding_config={"temperature": 0},
            implementation_hash="sha256:impl",
            official_source_hash="sha256:source",
            candidate_packets=_packets(),
        )
