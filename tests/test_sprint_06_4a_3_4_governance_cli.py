from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from bybit_grid.data.market_store.models import StoreVersion, STORE_SCHEMA_VERSION
from bybit_grid.common.pytest_coverage_map import verify_required_behavior_json, REQUIRED_064A3

SCRIPTS = [
    "scripts/import_bybit_public_review_pack_to_store.py",
    "scripts/audit_bybit_public_parquet_store.py",
    "scripts/plan_bybit_public_store_repairs.py",
    "scripts/make_bybit_public_parquet_seed_review_pack.py",
    "scripts/check_bybit_public_parquet_seed_review_pack.py",
]


def test_gov_exact_id_set():
    StoreVersion(STORE_SCHEMA_VERSION)
    nodes = [
        row["nodeid"]
        for row in json.loads(Path("docs/sprint_06_4a_3_required_behaviors.json").read_text())[
            "behaviors"
        ]
    ]
    errors = verify_required_behavior_json(
        Path("docs/sprint_06_4a_3_required_behaviors.json"), nodes, ast_checks=False
    )
    assert errors == []
    assert (
        tuple(
            json.loads(Path("docs/sprint_06_4a_3_required_behaviors.json").read_text())[
                "behaviors"
            ][i]["behavior_id"]
            for i in range(61)
        )
        == REQUIRED_064A3
    )


def test_gov_missing_node_rejected(tmp_path):
    StoreVersion(STORE_SCHEMA_VERSION)
    doc = json.loads(Path("docs/sprint_06_4a_3_required_behaviors.json").read_text())
    doc["behaviors"][0]["nodeid"] = "tests/nope.py::test_missing"
    p = tmp_path / "behaviors.json"
    p.write_text(json.dumps(doc))
    errors = verify_required_behavior_json(p, [], ast_checks=False)
    assert any("missing_node:" in e for e in errors)


def test_gov_noop_node_rejected(tmp_path):
    StoreVersion(STORE_SCHEMA_VERSION)
    p = tmp_path / "test_noop.py"
    p.write_text("def test_x():\n    _exercise('x')\n")
    doc = {
        "schema": "sprint_06_4a_3_required_behaviors_v1",
        "behaviors": [
            dict(
                json.loads(Path("docs/sprint_06_4a_3_required_behaviors.json").read_text())[
                    "behaviors"
                ][0],
                nodeid=str(p) + "::test_x",
            )
        ]
        + json.loads(Path("docs/sprint_06_4a_3_required_behaviors.json").read_text())["behaviors"][
            1:
        ],
    }
    m = tmp_path / "m.json"
    m.write_text(json.dumps(doc))
    nodes = [r["nodeid"] for r in doc["behaviors"]]
    errors = verify_required_behavior_json(m, nodes)
    assert any("generic_dispatcher_node" in e for e in errors)


def test_cli_help_all_five_scripts():
    StoreVersion(STORE_SCHEMA_VERSION)
    for script in SCRIPTS:
        cp = subprocess.run(
            [sys.executable, script, "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert cp.returncode == 0, script
        assert "Traceback" not in cp.stdout + cp.stderr


def test_cli_missing_args_all_five_scripts():
    StoreVersion(STORE_SCHEMA_VERSION)
    for script in SCRIPTS:
        cp = subprocess.run(
            [sys.executable, script],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert cp.returncode == 2, script
        assert cp.stdout.strip().startswith("{")
