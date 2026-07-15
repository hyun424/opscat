from __future__ import annotations

import json
from pathlib import Path

from tests.fixtures.p146.builders import build_known_conformance_corpus


def test_cli_writes_portable_bounded_episode_artifacts(tmp_path: Path, capsys) -> None:
    from app.p146_live_shadow_cli import main

    profile = tmp_path / "profile.json"
    output = tmp_path / "episode"
    profile.write_text(json.dumps({"schema_version": "p146.release_profile.v1", "corpus": build_known_conformance_corpus()}, default=sorted), encoding="utf-8")
    assert main(["run", "--profile", str(profile), "--output", str(output), "--case", "p146-case-01"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "p146.cli_episode_receipt.v1"
    assert payload["artifact_root"] == "episode"
    assert payload["authority_counters"]["credential_read_count"] == 0
    assert payload["authority_counters"]["external_http_count"] == 0
    assert "://" not in json.dumps(payload, sort_keys=True)
    assert str(tmp_path) not in json.dumps(payload, sort_keys=True)
    assert (output / "prediction.json").is_file()
    assert (output / "receipts.json").is_file()
