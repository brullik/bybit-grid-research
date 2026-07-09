from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    if args.run_id in {"latest", "auto", ""}:
        raise SystemExit("explicit concrete --run-id required")
    path = Path("data/processed/range_runs") / args.run_id
    if path.exists():
        shutil.rmtree(path)
        print(f"purged {args.run_id}")
    else:
        print(f"not_found {args.run_id}")


if __name__ == "__main__":
    main()
