from __future__ import annotations

import shutil
from pathlib import Path

from scripts.verify_p122_docs import DOCS, ROOT, ROOT_DOCS, verify_docs


def test_p122_docs_links_schema_examples_and_troubleshooting_are_verifiable() -> None:
    report = verify_docs()
    assert report["valid"] is True
    assert len(report["checked_docs"]) > 7
    assert set(report["checked_docs"]) == {str(path) for path in DOCS}
    assert {str(path) for path in ROOT_DOCS}.issubset(report["checked_docs"])
    assert {
        "README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CHANGELOG.md",
        "docs/release-notes-0.2.0.md",
        "docs/security-threat-model.md",
        "docs/threat-model.md",
        "docs/supply-chain.md",
    }.issubset(report["checked_docs"])
    assert set(report["document_hashes"]) == set(report["checked_docs"])
    assert all(value.startswith("sha256:") for value in report["document_hashes"].values())
    assert set(report["link_checked_docs"]) == set(report["checked_docs"])
    assert set(report["claim_checked_docs"]) == set(report["checked_docs"])
    assert set(report["schema_checked_docs"]) == set(report["checked_docs"])
    assert set(report["example_checked_docs"]) == set(report["checked_docs"])
    assert all(report["schema_markers"][doc] for doc in report["checked_docs"] if doc in report["core_docs"])
    assert report["broken_links"] == []
    assert report["missing_troubleshooting"] == []
    assert report["missing_schema"] == []
    assert report["missing_examples"] == []
    assert report["invalid_json_examples"] == []
    assert report["stale_script_examples"] == []
    assert report["malformed_schema_references"] == []
    assert report["unbounded_claims"] == []
    assert report["missing_required_claims"] == []


def test_docs_verifier_rejects_broken_claim_link_schema_and_examples(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "docs", tmp_path / "docs")
    shutil.copytree(ROOT / "scripts", tmp_path / "scripts")
    for doc in ROOT_DOCS:
        shutil.copy2(ROOT / doc, tmp_path / doc)
    readme = tmp_path / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + """

[Missing document](docs/does-not-exist.md)

`p122.invalid.vnext`

```json
{"missing": }
```

```bash
python scripts/does-not-exist.py
```

This package is production-ready.
""",
        encoding="utf-8",
    )

    report = verify_docs(root=tmp_path)

    assert any("README.md:docs/does-not-exist.md:missing" in issue for issue in report["broken_links"])
    assert any("README.md:p122.invalid.vnext" in issue for issue in report["malformed_schema_references"])
    assert "README.md:json-block-1" in report["invalid_json_examples"]
    assert "README.md:scripts/does-not-exist.py" in report["stale_script_examples"]
    assert any("README.md" in issue and "production-ready" in issue for issue in report["unbounded_claims"])
    assert report["valid"] is False
