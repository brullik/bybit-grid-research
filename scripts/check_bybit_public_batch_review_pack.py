#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bybit_grid.data.public_batch.evidence import validate_review_pack


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        out = validate_review_pack(Path(args.zip), args.run_id)
        print(json.dumps(out, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "exception_type": type(exc).__name__, "exception_message": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    sys.exit(main())
