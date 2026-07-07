"""Golden eval coverage taxonomy gates for P4."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path("evals/golden")
TAXONOMY_PATH = Path("docs/eval-taxonomy.json")


def _goldens() -> list[dict[str, Any]]:
    return [json.loads(path.read_text()) for path in sorted(GOLDEN_DIR.glob("*.json"))]


def test_eval_taxonomy_exists_and_classifies_all_golden_scenarios() -> None:
    assert TAXONOMY_PATH.exists()
    taxonomy: dict[str, Any] = json.loads(TAXONOMY_PATH.read_text())
    goldens = _goldens()
    categories = taxonomy["categories"]
    routes = taxonomy["routes"]
    safety_focus = taxonomy["safety_focus"]

    assert taxonomy["minimum_total_scenarios"] >= 23
    assert len(goldens) >= taxonomy["minimum_total_scenarios"]
    assert taxonomy["high_signal_over_volume"] is True

    category_counts = Counter(golden["category"] for golden in goldens)
    route_counts = Counter(golden["expected"]["expected_route"] for golden in goldens)
    focus_counts = Counter(focus for golden in goldens for focus in golden["safety_focus"])

    assert set(category_counts).issubset(categories)
    assert set(route_counts).issubset(routes)
    assert set(focus_counts).issubset(safety_focus)

    for category, rule in categories.items():
        assert category_counts[category] >= rule["min_scenarios"]
    for route, rule in routes.items():
        assert route_counts[route] >= rule["min_scenarios"]
    for focus, rule in safety_focus.items():
        assert focus_counts[focus] >= rule["min_scenarios"]


def test_eval_report_links_taxonomy_and_gap_policy() -> None:
    report = Path("docs/eval-report.md").read_text()

    assert "docs/eval-taxonomy.json" in report
    assert "high-signal scenarios over artificial volume" in report
