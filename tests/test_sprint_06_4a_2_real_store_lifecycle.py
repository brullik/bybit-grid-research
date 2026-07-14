from pathlib import Path
from bybit_grid.common.pytest_coverage_map import verify_maps


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "map.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_governance_verifier_rejects_noop_material_nodes(tmp_path):
    p = _write(tmp_path, "| Behavior | Node | Material setup | Production mutation/assertion | Expected |\n|---|---|---|---|---|\n| B | `tests/test_sprint_06_behavior_coverage_material_nodes.py::test_x_material_contract` | fixture = {\"id\": \"B\"} | validates collected closure row | B |\n")
    r = verify_maps(((str(p), 1),), {"tests/test_sprint_06_behavior_coverage_material_nodes.py::test_x_material_contract"})
    assert not r.ok
    assert any("forbidden_noop_node" in e for e in r.errors)
    assert any("expected_repeats_behavior_id" in e for e in r.errors)


def test_governance_verifier_rejects_duplicate_material_mapping(tmp_path):
    p = _write(tmp_path, "| Behavior | Node | Material setup | Production mutation/assertion | Expected |\n|---|---|---|---|---|\n| A | `tests/t.py::test_a` | real setup | mutates production cli | exact_error |\n| B | `tests/t.py::test_b` | real setup | mutates production cli | exact_error |\n")
    r = verify_maps(((str(p), 2),), {"tests/t.py::test_a", "tests/t.py::test_b"})
    assert not r.ok
    assert any("duplicate_material_mapping" in e for e in r.errors)
