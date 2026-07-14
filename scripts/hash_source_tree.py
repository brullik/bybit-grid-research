#!/usr/bin/env python
from __future__ import annotations
import argparse
import json
from pathlib import Path
from bybit_grid.common.source_tree import build_source_tree_manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    a = p.parse_args()
    try:
        print(
            json.dumps(
                build_source_tree_manifest(Path(a.root)), sort_keys=True, separators=(",", ":")
            )
        )
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
