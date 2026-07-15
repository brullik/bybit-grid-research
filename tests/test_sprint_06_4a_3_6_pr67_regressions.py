from __future__ import annotations

import json
from pathlib import Path

from bybit_grid.common.pytest_coverage_map import verify_required_behavior_json


def _manifest(tmp_path: Path, source: str, *, behavior_id: str = "DECIMAL-MAX-BOUNDARY") -> tuple[Path, str]:
    test_path = tmp_path / "test_bad_pr67_pattern.py"
    test_path.write_text(source, encoding="utf-8")
    nodeid = f"{test_path}::test_bad"
    manifest = tmp_path / "behaviors.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "sprint_06_4a_3_required_behaviors_v1",
                "behaviors": [
                    {
                        "behavior_id": behavior_id,
                        "nodeid": nodeid,
                        "production_symbols": ["ensure_decimal128_38_18"],
                        "fixture": "Decimal('1.000000000000000000') value is passed to schema helper",
                        "mutation": "PR67 pattern checks only the returned type name",
                        "expected": "MarketStoreError decimal_rounding_required",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest, nodeid


def test_pr67_type_name_decimal_padding_rejected(tmp_path):
    manifest, nodeid = _manifest(
        tmp_path,
        """
from decimal import Decimal
from bybit_grid.data.market_store.schemas import ensure_decimal128_38_18

def test_bad():
    result = ensure_decimal128_38_18(Decimal('1.000000000000000000'))
    assert type(result).__name__ == 'Decimal'
""",
    )
    errors = verify_required_behavior_json(manifest, [nodeid])
    assert any("missing_exact_expected_literal" in e for e in errors)


def test_pr67_any_exception_observations_and_empty_fixture_rejected(tmp_path):
    manifest, nodeid = _manifest(
        tmp_path,
        """
from bybit_grid.data.market_store.planner import partition_validated_rows

def test_bad():
    observations = []
    try:
        partition_validated_rows('trade_kline_1m', [])
    except Exception as exc:
        observations.append(type(exc).__name__)
    assert observations
""",
        behavior_id="PLAN-KLINE-CROSS-MONTH",
    )
    errors = verify_required_behavior_json(manifest, [nodeid])
    joined = "\n".join(errors)
    assert "forbidden_any_exception_capture" in joined
    assert "forbidden_observations_pattern" in joined
    assert "forbidden_empty_fixture" in joined


def test_pr67_object_evidence_rejected(tmp_path):
    manifest, nodeid = _manifest(
        tmp_path,
        """
from bybit_grid.data.market_store.transaction import build_import_preflight_plan

def test_bad(tmp_path):
    result = build_import_preflight_plan(object(), tmp_path / 'store')
    assert result is not None
""",
        behavior_id="PREFLIGHT-INVALID-ROW-ZERO-WRITES",
    )
    errors = verify_required_behavior_json(manifest, [nodeid])
    assert any("forbidden_object_evidence" in e for e in errors)


def test_pr67_missing_store_and_python_version_rejected(tmp_path):
    manifest, nodeid = _manifest(
        tmp_path,
        """
import subprocess
from bybit_grid.data.market_store.audit import audit_market_store

def test_bad(tmp_path):
    audit_market_store(tmp_path / 'missing')
    cp = subprocess.run(['python', '--version'])
    assert cp.returncode == 0
""",
        behavior_id="CLI-FULL-LIFECYCLE-BYBIT-HOST",
    )
    errors = verify_required_behavior_json(manifest, [nodeid])
    joined = "\n".join(errors)
    assert "forbidden_missing_store_fixture" in joined
    assert "forbidden_python_version_lifecycle" in joined


def test_pr67_duplicate_bodies_changed_constants_rejected(tmp_path):
    source = tmp_path / "test_dupes.py"
    source.write_text(
        """
def test_bad():
    assert 17 >= 1

def test_bad_two():
    assert 42 >= 9
""",
        encoding="utf-8",
    )
    rows = []
    for behavior_id, name in [("DECIMAL-MAX-BOUNDARY", "test_bad"), ("DECIMAL-MIN-BOUNDARY", "test_bad_two")]:
        rows.append(
            {
                "behavior_id": behavior_id,
                "nodeid": f"{source}::{name}",
                "production_symbols": ["ensure_decimal128_38_18"],
                "fixture": "constant comparison body copied from rejected PR67",
                "mutation": "only integer literals differ between two tests",
                "expected": "MarketStoreError decimal_rounding_required",
            }
        )
    manifest = tmp_path / "behaviors.json"
    manifest.write_text(json.dumps({"schema": "sprint_06_4a_3_required_behaviors_v1", "behaviors": rows}), encoding="utf-8")
    errors = verify_required_behavior_json(manifest, [r["nodeid"] for r in rows])
    joined = "\n".join(errors)
    assert "duplicate_normalized_test_body" in joined
    assert "constant_only_assertion" in joined
