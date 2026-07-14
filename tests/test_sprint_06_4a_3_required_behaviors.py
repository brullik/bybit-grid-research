from __future__ import annotations

from pathlib import Path
import json

import pytest

REQ = json.loads(Path("docs/sprint_06_4a_3_required_behaviors.json").read_text())["behaviors"]
IDS = tuple(row["behavior_id"] for row in REQ)


@pytest.mark.parametrize("behavior_id", IDS, ids=IDS)
def test_required_behavior_material(behavior_id):
    row = next(r for r in REQ if r["behavior_id"] == behavior_id)
    assert row["nodeid"].endswith(f"[{behavior_id}]")
    assert "stable fail-closed result" in row["expected"]
    assert "placeholder" not in row["material"].lower()
