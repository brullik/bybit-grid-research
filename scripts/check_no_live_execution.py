from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.common.source_safety_audit import audit_source_tree

if __name__ == "__main__":
    result = audit_source_tree(Path(__file__).resolve().parents[1])
    print(json.dumps(result.__dict__, indent=2, sort_keys=True))
    raise SystemExit(0 if result.ok else 1)
