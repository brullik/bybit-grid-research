#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                {"ok": True, "script": Path(__file__).name},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except Exception as exc:
        if args.debug:
            traceback.print_exc()
        print(
            json.dumps(
                {"ok": False, "error": str(exc)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
