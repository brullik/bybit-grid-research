#!/usr/bin/env python
from __future__ import annotations
import argparse
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.common.pytest_coverage_map import collect_nodes, verify_maps


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect-command", required=True)
    ns = ap.parse_args(argv)
    try:
        nodes = collect_nodes(ns.collect_command)
        res = verify_maps(
            (
                ("docs/sprint_06_3b_3_2_behavior_coverage.md", 72),
                ("docs/sprint_06_4a_behavior_coverage.md", 82),
            ),
            nodes,
        )
        print(res.to_json())
        return 0 if res.ok else 1
    except Exception as e:
        print('{"errors":["' + str(e).replace('"', "_") + '"],"ok":false}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
