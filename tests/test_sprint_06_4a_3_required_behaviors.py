from __future__ import annotations

import json
from pathlib import Path

from bybit_grid.common.pytest_coverage_map import REQUIRED_064A3


def test_required_behavior_manifest_schema():
    raw = json.loads(Path("docs/sprint_06_4a_3_required_behaviors.json").read_text())
    assert raw["schema"] == "sprint_06_4a_3_required_behaviors_v1"
    assert tuple(row["behavior_id"] for row in raw["behaviors"]) == REQUIRED_064A3
